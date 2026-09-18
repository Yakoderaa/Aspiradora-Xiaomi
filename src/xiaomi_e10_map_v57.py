import io
import json
import math
import time
from collections import Counter, deque
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image

from xiaomi_e10_ijai_map import IjaiMapSnapshot
from xiaomi_e10_map_v56 import XiaomiE10MapV56


class XiaomiE10MapV57(XiaomiE10MapV56):
    """V57: mapa vivo por eventos de upload + mapa final por clean-end/record-map-url.

    Objetivos funcionales:
    - No renderizar como mapa un payload espacialmente incoherente (cuadrados aislados).
    - Tras pedir realtime, observar 10/2 global-push, 10/4 upload-verify y
      10/6 test-upload-map, además del blob, durante una ventana suficiente.
    - Al terminar una limpieza, consultar 7/1 clean-end, extraer piid 30
      record-map-url, resolverlo por las APIs FDS usadas por Xiaomi y decodificar
      ese archivo con todos los parsers ya disponibles.
    """

    LIVE_EVENT_KEYS = ("10.2", "10.4", "10.6")
    CLEAN_END_KEY = "7.1"
    LIVE_WAIT_SECONDS = 9.0
    LIVE_POLL_SECONDS = 1.0
    HISTORY_LOOKBACK_SECONDS = 6 * 60 * 60
    HISTORY_LIMIT = 80

    def __init__(self, *args, **kwargs):
        self.last_v57_diagnostics: dict[str, Any] = {}
        self._v57_session_started_at = time.time()
        self._v57_last_record_signature = None
        self._v57_last_record_snapshot = None
        super().__init__(*args, **kwargs)

    # ---------------------------------------------------------- JSON/history
    @staticmethod
    def _decode_json_response(response: Any):
        if isinstance(response, (bytes, bytearray, memoryview)):
            response = bytes(response).decode("utf-8-sig", errors="replace")
        if isinstance(response, str):
            text = response.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            response = json.loads(text)
        if not isinstance(response, dict):
            raise RuntimeError(f"respuesta Cloud inesperada: {type(response).__name__}")
        code = response.get("code", 0)
        if code not in (0, "0", None):
            raise RuntimeError(
                f"Cloud code={code}: "
                + str(response.get("message") or response.get("msg") or "sin detalle")
            )
        result = response.get("result")
        return result if result is not None else []

    @staticmethod
    def _record_time(record: Any):
        if not isinstance(record, dict):
            return None
        for key in ("time", "timestamp", "createTime", "updateTime", "create_time"):
            value = record.get(key)
            try:
                number = float(value)
            except Exception:
                continue
            if not math.isfinite(number) or number <= 0:
                continue
            if number > 100_000_000_000:
                number /= 1000.0
            return number
        return None

    @classmethod
    def _unwrap_json(cls, value: Any):
        current = value
        for _ in range(6):
            if isinstance(current, str):
                text = current.strip()
                if not text:
                    break
                try:
                    parsed = json.loads(text)
                except Exception:
                    break
                if parsed == current:
                    break
                current = parsed
                continue
            if isinstance(current, list) and len(current) == 1:
                current = current[0]
                continue
            break
        return current

    @classmethod
    def _walk(cls, value: Any):
        value = cls._unwrap_json(value)
        yield value
        if isinstance(value, dict):
            for nested in value.values():
                yield from cls._walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from cls._walk(nested)

    @classmethod
    def _piid_values(cls, record: Any):
        found = []
        for node in cls._walk(record):
            if not isinstance(node, dict):
                continue
            if "piid" not in node or "value" not in node:
                continue
            try:
                piid = int(node.get("piid"))
            except Exception:
                continue
            found.append((piid, cls._unwrap_json(node.get("value"))))
        return found

    @classmethod
    def _event_meta(cls, record: Any):
        values = dict(cls._piid_values(record))
        result = {
            "map_id": values.get(6),
            "map_type": values.get(7),
            "timestamp": values.get(18),
            "renew_map": values.get(21),
            "record_map_url": values.get(30),
            "record_start_time": values.get(27),
            "record_use_time": values.get(28),
            "record_area": values.get(29),
            "charge_pose": values.get(49),
        }
        return result

    def _history_request(self, endpoint: str, payload: dict[str, Any]):
        cloud = self._cloud()
        response = cloud.request_country(
            endpoint,
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        result = self._decode_json_response(response)
        if isinstance(result, list):
            return [x for x in result if isinstance(x, dict)]
        if isinstance(result, dict):
            for key in ("list", "records", "data"):
                value = result.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
        return []

    def _query_key(self, key: str, start: int, end: int):
        uid = str(self.session_data.get("user_id") or "")
        common = {
            "uid": uid,
            "did": self.did,
            "key": str(key),
            "time_start": int(start),
            "time_end": int(end),
            "limit": self.HISTORY_LIMIT,
        }
        results = []
        diagnostics = []

        variants = (
            ("/user/get_user_device_data", {**common, "type": "event"}, "history:event"),
            ("/v2/user/get_device_data_raw", {**common, "type": "store"}, "raw:store"),
            ("/v2/user/get_device_data_raw", {**common, "type": "event"}, "raw:event"),
        )
        for endpoint, payload, label in variants:
            try:
                records = self._history_request(endpoint, payload)
                diagnostics.append({"label": label, "ok": True, "records": len(records)})
                for record in records:
                    results.append((label, record))
            except Exception as exc:
                diagnostics.append({
                    "label": label,
                    "ok": False,
                    "records": 0,
                    "error": self._safe_http_error(exc),
                })
        return results, diagnostics

    def _query_device_log(self, start: int, end: int):
        uid = str(self.session_data.get("user_id") or "")
        payload = {
            "uid": uid,
            "did": self.did,
            "time_start": int(start),
            "time_end": int(end),
            "limit": 50,
        }
        try:
            records = self._history_request("/v2/user/get_user_device_log", payload)
            return records, {"ok": True, "records": len(records)}
        except Exception as exc:
            return [], {"ok": False, "records": 0, "error": self._safe_http_error(exc)}

    @staticmethod
    def _record_key(record: dict[str, Any]):
        for key in ("key", "event", "event_key", "name"):
            value = record.get(key)
            if value is not None:
                return str(value)
        return ""

    # --------------------------------------------------------- action output
    @classmethod
    def _action_metadata(cls, response: Any):
        result = {
            "response_type": type(response).__name__,
            "code": None,
            "map_id": None,
            "map_type": None,
            "timestamp": None,
            "renew_map": None,
        }

        candidates = []
        for node in cls._walk(response):
            if isinstance(node, dict):
                candidates.append(node)

        for node in candidates:
            if result["code"] is None and "code" in node:
                result["code"] = node.get("code")
            out = node.get("out")
            if not isinstance(out, list):
                continue
            for item in out:
                if not isinstance(item, dict):
                    continue
                try:
                    piid = int(item.get("piid"))
                except Exception:
                    continue
                value = item.get("value")
                if piid == 6:
                    result["map_id"] = value
                elif piid == 7:
                    result["map_type"] = value
                elif piid == 18:
                    result["timestamp"] = value
                elif piid == 21:
                    result["renew_map"] = value
        return result

    # ------------------------------------------------------------- FDS refs
    @staticmethod
    def _looks_http(value: Any):
        if not isinstance(value, str):
            return False
        parsed = urlparse(value.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    @staticmethod
    def _extract_url_any(response: Any):
        try:
            decoded = XiaomiE10MapV57._decode_json_response(response)
        except Exception:
            return None
        for node in XiaomiE10MapV57._walk(decoded):
            if isinstance(node, dict):
                for key in ("url", "file_url", "download_url"):
                    value = node.get(key)
                    if XiaomiE10MapV57._looks_http(value):
                        return str(value)
            elif XiaomiE10MapV57._looks_http(node):
                return str(node)
        return None

    def _resolve_file_ref(self, reference: str):
        ref = str(reference or "").strip()
        if not ref:
            raise RuntimeError("record-map-url vacío")
        if self._looks_http(ref):
            return ref, "direct"

        cloud = self._cloud()
        user_id = str(self.session_data.get("user_id") or "")
        clean = ref.lstrip("/")
        basename = clean.rstrip("/").split("/")[-1]
        candidates = []
        for value in (
            clean,
            ref,
            f"{user_id}/{self.did}/{clean}",
            f"{user_id}/{self.did}/{basename}",
            basename,
        ):
            value = str(value or "").strip()
            if value and value not in candidates:
                candidates.append(value)

        endpoints = (
            "/home/getfileurl",
            "/home/getmapfileurl",
            "/v2/home/get_interim_file_url",
            "/v2/home/get_interim_file_url_pro",
        )
        errors = []
        for obj_name in candidates:
            params = {"data": json.dumps({"obj_name": obj_name}, separators=(",", ":"))}
            for endpoint in endpoints:
                try:
                    response = cloud.request_country(endpoint, self.region, dict(params))
                    url = self._extract_url_any(response)
                    if url:
                        return url, endpoint.rsplit("/", 1)[-1]
                except Exception as exc:
                    errors.append(
                        f"{endpoint.rsplit('/',1)[-1]}:{type(exc).__name__}"
                    )
        raise RuntimeError("no se pudo resolver record-map-url · " + " | ".join(errors[-6:]))

    @staticmethod
    def _download_url(url: str):
        response = requests.get(url, timeout=30)
        raw = bytes(response.content or b"")
        response.raise_for_status()
        return raw, int(response.status_code)

    # ----------------------------------------------------------- decoders
    def _decode_any_map(self, raw: bytes, label: str, endpoint: str):
        decoder_diag = []

        # 0) Algunos record-map-url ya apuntan a una imagen renderizada.
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                rgba = image.convert("RGBA")
            decoder_diag.append({
                "name": "image",
                "ok": True,
                "format": getattr(image, "format", None),
                "size": list(rgba.size),
            })
            return IjaiMapSnapshot(
                image=rgba,
                map_name=str(label),
                crypto_mode="record-map-image",
                raw_size=len(raw),
                envelope_version="image",
                raw_robot=None,
                raw_base=None,
                raw_path=[],
                slot=str(label),
                endpoint=str(endpoint),
                decrypted_size=len(raw),
                raw_prefix_hex=bytes(raw[:16]).hex(),
            ), decoder_diag
        except Exception:
            decoder_diag.append({"name": "image", "ok": False})

        # 1) B112 exact/grid
        try:
            candidate = self._decode_b112_payload(raw)
            if candidate is not None and candidate.get("exact_b112_grid"):
                snapshot = self._snapshot_from_grid(label, endpoint, raw, candidate)
                if self._grid_is_spatially_coherent(snapshot.grid_cells):
                    decoder_diag.append({"name": "b112-grid", "ok": True})
                    return snapshot, decoder_diag
                decoder_diag.append({"name": "b112-grid", "ok": False, "reason": "grid incoherente"})
        except Exception as exc:
            decoder_diag.append({"name": "b112-grid", "ok": False, "error": type(exc).__name__})

        # 2) IJAI exacto, todas las combinaciones conocidas
        try:
            wifi, owners, dids, macs = self._ordered_key_material()
            snapshot, diag = self._probe_known_ijai(
                raw, wifi, owners, dids, macs, label, endpoint
            )
            decoder_diag.append({
                "name": "ijai",
                "ok": snapshot is not None,
                "attempts": sum(int(v.get("attempts", 0) or 0) for v in (diag.get("modes") or {}).values()),
            })
            if snapshot is not None:
                return snapshot, decoder_diag
        except Exception as exc:
            decoder_diag.append({"name": "ijai", "ok": False, "error": type(exc).__name__})

        # 3) Xiaomi JSON AES-CBC
        try:
            snapshot, diag = self._decode_xiaomi(raw, label, endpoint)
            decoder_diag.append({
                "name": "xiaomi-json",
                "ok": snapshot is not None,
                "attempts": int(diag.get("attempts", 0) or 0),
            })
            if snapshot is not None:
                return snapshot, decoder_diag
        except Exception as exc:
            decoder_diag.append({"name": "xiaomi-json", "ok": False, "error": type(exc).__name__})

        return None, decoder_diag

    # -------------------------------------------------- spatial validation
    @classmethod
    def _grid_metrics(cls, cells):
        side = cls.GRID_SIDE
        if not cells or len(cells) != side * side:
            return {
                "valid": False,
                "nonzero": 0,
                "components": 0,
                "largest": 0,
                "largest_ratio": 0.0,
                "adjacency_ratio": 0.0,
            }

        occupied = {idx for idx, value in enumerate(cells) if int(value) != 0}
        nonzero = len(occupied)
        if not occupied:
            return {
                "valid": False,
                "nonzero": 0,
                "components": 0,
                "largest": 0,
                "largest_ratio": 0.0,
                "adjacency_ratio": 0.0,
            }

        visited = set()
        component_sizes = []
        neighbor_links = 0
        for idx in occupied:
            x = idx % side
            y = idx // side
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < side and 0 <= ny < side and (ny * side + nx) in occupied:
                    neighbor_links += 1

            if idx in visited:
                continue
            queue = deque([idx])
            visited.add(idx)
            size = 0
            while queue:
                current = queue.popleft()
                size += 1
                cx = current % side
                cy = current // side
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = cx + dx, cy + dy
                    nidx = ny * side + nx
                    if 0 <= nx < side and 0 <= ny < side and nidx in occupied and nidx not in visited:
                        visited.add(nidx)
                        queue.append(nidx)
            component_sizes.append(size)

        largest = max(component_sizes, default=0)
        largest_ratio = largest / nonzero if nonzero else 0.0
        adjacency_ratio = neighbor_links / nonzero if nonzero else 0.0

        # Evita exactamente el falso mapa de V56: 85 celdas y 56 islotes.
        valid = bool(
            nonzero >= 180
            and largest >= 120
            and largest_ratio >= 0.55
            and adjacency_ratio >= 0.60
        )
        return {
            "valid": valid,
            "nonzero": nonzero,
            "components": len(component_sizes),
            "largest": largest,
            "largest_ratio": round(largest_ratio, 4),
            "adjacency_ratio": round(adjacency_ratio, 4),
        }

    @classmethod
    def _grid_is_spatially_coherent(cls, cells):
        return bool(cls._grid_metrics(cells).get("valid"))

    # ----------------------------------------------------------- event maps
    def _latest_clean_end(self):
        end = int(time.time()) + 30
        start = max(
            0,
            end - self.HISTORY_LOOKBACK_SECONDS,
            int(float(getattr(self, "_v57_session_started_at", 0.0) or 0.0)) - 120,
        )
        records, diag = self._query_key(self.CLEAN_END_KEY, start, end)
        log_records, log_diag = self._query_device_log(start, end)

        candidates = []
        for source, record in records:
            meta = self._event_meta(record)
            ref = meta.get("record_map_url")
            if ref:
                candidates.append((self._record_time(record) or 0.0, source, record, meta))

        for record in log_records:
            key = self._record_key(record)
            if key and key not in (self.CLEAN_END_KEY, "clean-end", "7.1"):
                continue
            meta = self._event_meta(record)
            ref = meta.get("record_map_url")
            if ref:
                candidates.append((self._record_time(record) or 0.0, "device-log", record, meta))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0] if candidates else None, {
            "queries": diag,
            "device_log": log_diag,
            "candidate_count": len(candidates),
        }

    def _load_record_map(self):
        latest, hist_diag = self._latest_clean_end()
        diag = {
            "history": hist_diag,
            "found": latest is not None,
            "success": False,
            "source": None,
            "record_time": None,
            "reference_kind": None,
            "resolve_endpoint": None,
            "download_bytes": 0,
            "download_sha12": None,
            "decoders": [],
        }
        if latest is None:
            return None, diag

        record_time, source, _record, meta = latest
        ref = meta.get("record_map_url")
        signature = (round(float(record_time or 0.0), 3), str(ref))
        if signature == self._v57_last_record_signature and self._v57_last_record_snapshot is not None:
            diag.update({
                "success": True,
                "source": source,
                "record_time": record_time,
                "reference_kind": "cache",
            })
            return self._v57_last_record_snapshot, diag

        url, resolver = self._resolve_file_ref(str(ref))
        raw, status = self._download_url(url)
        snapshot, decoders = self._decode_any_map(raw, "clean-end", resolver)
        diag.update({
            "source": source,
            "record_time": record_time,
            "reference_kind": "http" if self._looks_http(ref) else "fds-ref",
            "resolve_endpoint": resolver,
            "http": status,
            "download_bytes": len(raw),
            "download_sha12": self._sha12(raw),
            "decoders": decoders,
            "success": snapshot is not None,
        })
        if snapshot is not None:
            self._v57_last_record_signature = signature
            self._v57_last_record_snapshot = snapshot
        return snapshot, diag

    # ------------------------------------------------------- realtime events
    def _recent_live_events(self, since: int):
        end = int(time.time()) + 30
        result = []
        diagnostics = {}
        for key in self.LIVE_EVENT_KEYS:
            records, diag = self._query_key(key, since, end)
            diagnostics[key] = diag
            for source, record in records:
                meta = self._event_meta(record)
                result.append({
                    "key": key,
                    "source": source,
                    "time": self._record_time(record),
                    **meta,
                })
        result.sort(key=lambda item: float(item.get("time") or 0.0), reverse=True)
        return result, diagnostics

    def request_fresh_upload(self):
        # Ejecuta una vez cada acción oficial, luego espera de verdad la
        # propagación Cloud/evento en lugar de asumir que 750 ms alcanzan.
        privacy_before = None
        try:
            privacy_before = self.map_privacy_state()
            if privacy_before == 1:
                self.enable_map_upload_temporarily()
        except Exception:
            pass

        try:
            baseline_raw, _ep, _status = self._download_slot("0")
            baseline_hash = self._sha12(baseline_raw)
        except Exception:
            baseline_hash = None

        started = int(time.time()) - 2
        attempts = []
        winner = None
        final_hash = baseline_hash
        live_events = []
        event_queries = {}

        for aiid, params, label in (
            (18, [], "upmapdata"),
            (15, [0], "upload-by-maptype-ii · Realtime"),
            (6, [0], "upload-by-maptype · Realtime"),
        ):
            item = self._call_realtime_upload(aiid, params, label)
            item["hash_before"] = final_hash
            attempts.append(item)
            if not item.get("ok"):
                continue

            deadline = time.monotonic() + self.LIVE_WAIT_SECONDS
            while time.monotonic() < deadline:
                time.sleep(self.LIVE_POLL_SECONDS)
                try:
                    raw, endpoint, status = self._download_slot("0")
                    current = self._sha12(raw)
                    item["hash_after"] = current
                    item["http"] = status
                    item["endpoint"] = endpoint
                    item["bytes"] = len(raw)
                    if final_hash and current and current != final_hash:
                        item["changed"] = True
                        final_hash = current
                        winner = item["action"]
                        break
                    final_hash = current or final_hash
                except Exception as exc:
                    item["download_error"] = self._safe_http_error(exc)

                try:
                    live_events, event_queries = self._recent_live_events(started)
                except Exception:
                    pass
                if live_events:
                    item["event_seen"] = live_events[0].get("key")
                    # El evento global-push/upload-verify confirma que el
                    # firmware ya publicó; hacemos una última descarga inmediata.
                    try:
                        raw, endpoint, status = self._download_slot("0")
                        current = self._sha12(raw)
                        item["hash_after"] = current
                        item["http"] = status
                        item["endpoint"] = endpoint
                        item["bytes"] = len(raw)
                        if final_hash and current and current != final_hash:
                            item["changed"] = True
                            final_hash = current
                            winner = item["action"]
                            break
                    except Exception:
                        pass
            if winner:
                break

        self.last_v57_diagnostics["live_refresh"] = {
            "privacy_before": privacy_before,
            "baseline_hash": baseline_hash,
            "hash_after": final_hash,
            "changed": bool(winner),
            "winner": winner,
            "attempts": attempts,
            "events": live_events[:8],
            "event_queries": event_queries,
        }
        info = {
            "official_actions": True,
            "privacy_before": privacy_before,
            "baseline_hash": baseline_hash,
            "attempts": attempts,
            "winner": winner,
            "hash_after": final_hash,
            "changed": bool(winner),
            "ok": any(bool(x.get("ok")) for x in attempts),
            "map_id": next(
                (x.get("map_id") for x in reversed(attempts) if x.get("map_id") is not None),
                0,
            ),
        }
        self.last_v56_upload_diagnostics = dict(info)
        self.last_upload_diagnostics = dict(info)
        return info

    # --------------------------------------------------------------- load
    def load(self):
        diagnostics = dict(getattr(self, "last_v57_diagnostics", {}) or {})

        # 1) Preferimos el clean-end real si existe: es el archivo que Xiaomi
        # Home guarda como registro de esa limpieza.
        try:
            record_snapshot, record_diag = self._load_record_map()
            diagnostics["record_map"] = record_diag
            if record_snapshot is not None:
                diagnostics.update({
                    "route": "clean-end 7/1 -> record-map-url -> decoder",
                    "success": True,
                    "source": "record-map-url",
                })
                self.last_v57_diagnostics = diagnostics
                return record_snapshot
        except Exception as exc:
            diagnostics["record_map"] = {
                "success": False,
                "error": self._safe_http_error(exc),
            }

        # 2) Realtime V56, pero jamás devolvemos la rejilla falsa de cuadrados.
        snapshot = super().load()
        if hasattr(snapshot, "grid_cells"):
            metrics = self._grid_metrics(getattr(snapshot, "grid_cells", []) or [])
            diagnostics["live_grid_metrics"] = metrics
            if not metrics.get("valid"):
                # No entregamos walls/image falsos. Conservamos sólo base/robot
                # como telemetría estática, sin trayectoria.
                snapshot.grid_cells = []
                snapshot.grid_walls = []
                snapshot.raw_path = []
                snapshot.image = None
                snapshot.parser_error = "V57: grid rechazado por incoherencia espacial"
                diagnostics.update({
                    "route": "realtime descifrado pero grid rechazado",
                    "success": False,
                    "source": "none",
                })
            else:
                diagnostics.update({
                    "route": "realtime V56 validado espacialmente",
                    "success": True,
                    "source": "live-grid",
                })
        self.last_v57_diagnostics = diagnostics
        return snapshot

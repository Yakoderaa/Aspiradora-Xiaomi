import json
import time
from typing import Any

import requests

from xiaomi_e10_map_v57 import XiaomiE10MapV57


class XiaomiE10MapV58(XiaomiE10MapV57):
    """V58: refresh realtime por LAN + Xiaomi Cloud + eventos sin UID.

    Corrige dos limitaciones de V57:
    - get_user_device_data se consulta también SIN uid, que es la forma usada
      por implementaciones MIoT actuales.
    - las acciones de mapa se ejecutan también por /miotspec/action cuando la
      respuesta LAN no expone outputs útiles, para capturar map-id/timestamp y
      cualquier referencia FDS que Xiaomi Home reciba por Cloud.
    """

    CLOUD_EVENT_ENDPOINTS = (
        "/user/get_user_device_data",
        "/v2/user/get_user_device_data",
        "/v2/user/get_device_data_raw",
    )
    CLOUD_ACTION_ENDPOINTS = (
        "/miotspec/action",
        "/v2/miotspec/action",
    )
    CANDIDATE_SETTLE_SECONDS = 1.2

    def __init__(self, *args, **kwargs):
        self.last_v58_diagnostics: dict[str, Any] = {}
        self._v58_fresh_snapshot = None
        self._v58_fresh_meta: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _sanitize_error(exc: Exception):
        text = str(exc).strip() or type(exc).__name__
        return text[:220]

    @classmethod
    def _extract_result_any(cls, response: Any):
        current = response
        if isinstance(current, (bytes, bytearray, memoryview)):
            try:
                current = bytes(current).decode("utf-8-sig")
            except Exception:
                return current
        if isinstance(current, str):
            text = current.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            try:
                current = json.loads(text)
            except Exception:
                return current
        return current

    @classmethod
    def _response_code(cls, response: Any):
        node = cls._extract_result_any(response)
        if isinstance(node, dict):
            code = node.get("code")
            if code not in (None, 0, "0"):
                return code
            result = node.get("result")
            if isinstance(result, dict):
                return result.get("code", code)
        return None

    @classmethod
    def _object_refs_from_response(cls, response: Any):
        refs = []
        seen = set()
        interesting_keys = {
            "obj_name", "object_name", "objectName", "file", "filename",
            "file_name", "map_url", "mapUrl", "record_map_url", "url",
            "file_url", "download_url", "map", "map_name",
        }

        def add(value, source):
            if not isinstance(value, str):
                return
            text = value.strip()
            if not text or len(text) > 1200:
                return
            sig = (source, text)
            if sig in seen:
                return
            seen.add(sig)
            refs.append((source, text))

        for node in cls._walk(cls._extract_result_any(response)):
            if isinstance(node, dict):
                for key, value in node.items():
                    if str(key) in interesting_keys:
                        add(value, str(key))
        return refs[:24]

    # ----------------------------------------------------- historial Cloud
    def _history_request_variant(
        self,
        endpoint: str,
        key: str,
        typ: str,
        start: int,
        end: int,
        include_uid: bool,
    ):
        payload = {
            "did": self.did,
            "time_end": int(end),
            "time_start": max(0, int(start)),
            "limit": self.HISTORY_LIMIT,
            "key": str(key),
            "type": str(typ),
        }
        if include_uid:
            payload["uid"] = str(self.session_data.get("user_id") or "")

        cloud = self._cloud()
        response = cloud.request_country(
            endpoint,
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        decoded = self._extract_result_any(response)
        code = decoded.get("code", 0) if isinstance(decoded, dict) else None
        result = decoded.get("result") if isinstance(decoded, dict) else None

        records = []
        if isinstance(result, list):
            records = [x for x in result if isinstance(x, dict)]
        elif isinstance(result, dict):
            for name in ("list", "records", "data"):
                value = result.get(name)
                if isinstance(value, list):
                    records = [x for x in value if isinstance(x, dict)]
                    break

        if code not in (0, "0", None):
            raise RuntimeError(
                f"code={code} · "
                + str(
                    (decoded or {}).get("message")
                    or (decoded or {}).get("msg")
                    or "sin detalle"
                )
            )
        return records, {
            "endpoint": endpoint.rsplit("/", 1)[-1],
            "uid": bool(include_uid),
            "type": typ,
            "code": code,
            "records": len(records),
        }

    def _query_key(self, key: str, start: int, end: int):
        results = []
        diagnostics = []
        variants = []
        for endpoint in self.CLOUD_EVENT_ENDPOINTS:
            # get_device_data_raw suele usar store/event; las otras aceptan event.
            types = ("event", "store") if endpoint.endswith("get_device_data_raw") else ("event",)
            for typ in types:
                variants.append((endpoint, typ, False))
                variants.append((endpoint, typ, True))

        for endpoint, typ, include_uid in variants:
            label = (
                endpoint.rsplit("/", 1)[-1]
                + f":{typ}:"
                + ("uid" if include_uid else "no-uid")
            )
            try:
                records, detail = self._history_request_variant(
                    endpoint, key, typ, start, end, include_uid
                )
                diagnostics.append({"label": label, "ok": True, **detail})
                for record in records:
                    results.append((label, record))
            except Exception as exc:
                diagnostics.append({
                    "label": label,
                    "ok": False,
                    "endpoint": endpoint.rsplit("/", 1)[-1],
                    "uid": bool(include_uid),
                    "type": typ,
                    "code": None,
                    "records": 0,
                    "error": self._sanitize_error(exc),
                })
        return results, diagnostics

    # --------------------------------------------------------- Cloud action
    def _call_cloud_action(self, aiid: int, params: list[int], label: str):
        item = {
            "transport": "cloud",
            "action": f"10/{aiid}",
            "label": label,
            "ok": False,
            "endpoint": None,
            "code": None,
            "map_id": None,
            "map_type": None,
            "timestamp": None,
            "renew_map": None,
            "refs": [],
        }
        body = {
            "params": {
                "did": str(self.did),
                "siid": 10,
                "aiid": int(aiid),
                "in": list(params),
            }
        }
        cloud = self._cloud()
        errors = []
        for endpoint in self.CLOUD_ACTION_ENDPOINTS:
            try:
                response = cloud.request_country(
                    endpoint,
                    self.region,
                    {"data": json.dumps(body, separators=(",", ":"))},
                )
                normalized = self._extract_result_any(response)
                meta = self._action_metadata(normalized)
                code = self._response_code(normalized)
                item.update(meta)
                item["code"] = code if code is not None else meta.get("code")
                item["endpoint"] = endpoint.rsplit("/", 1)[-1]
                item["refs"] = [
                    {"source": source, "kind": "url" if self._looks_http(value) else "object"}
                    for source, value in self._object_refs_from_response(normalized)
                ]
                item["_ref_values"] = self._object_refs_from_response(normalized)
                if item["code"] not in (None, 0, "0"):
                    raise RuntimeError(f"code={item['code']}")
                item["ok"] = True
                return item
            except Exception as exc:
                errors.append(
                    f"{endpoint.rsplit('/',1)[-1]}:{self._sanitize_error(exc)}"
                )
        item["error"] = " | ".join(errors[-2:])
        return item

    # --------------------------------------------------------- FDS probing
    def _identifier_candidates(self, *items):
        candidates = []
        seen = set()

        def add(value, source):
            if value is None:
                return
            text = str(value).strip()
            if not text or text in ("0", "None"):
                return
            key = (source, text)
            if key in seen:
                return
            seen.add(key)
            candidates.append((source, text))

        for item in items:
            if not isinstance(item, dict):
                continue
            add(item.get("map_id"), "map-id")
            add(item.get("timestamp"), "timestamp")
            mid = item.get("map_id")
            ts = item.get("timestamp")
            if mid not in (None, 0, "0") and ts not in (None, 0, "0"):
                add(f"{mid}_{ts}", "map-id_timestamp")
                add(f"{ts}_{mid}", "timestamp_map-id")
            for source, value in item.get("_ref_values") or []:
                add(value, f"response:{source}")

        return candidates[:20]

    def _download_candidate_reference(self, source: str, reference: str):
        # URL/path explícita: usa el resolver general V57.
        if self._looks_http(reference) or "/" in reference or "\\" in reference:
            url, endpoint = self._resolve_file_ref(reference)
            response = requests.get(url, timeout=25)
            raw = bytes(response.content or b"")
            response.raise_for_status()
            return raw, endpoint, int(response.status_code)

        # Identificador corto: primero como slot IJAI, después como referencia FDS.
        errors = []
        try:
            raw, endpoint, status = self._download_slot(reference)
            return raw, endpoint, status
        except Exception as exc:
            errors.append(f"slot:{self._sanitize_error(exc)}")
        try:
            url, endpoint = self._resolve_file_ref(reference)
            response = requests.get(url, timeout=25)
            raw = bytes(response.content or b"")
            response.raise_for_status()
            return raw, endpoint, int(response.status_code)
        except Exception as exc:
            errors.append(f"fds:{self._sanitize_error(exc)}")
        raise RuntimeError(" | ".join(errors))

    def _probe_action_candidates(self, baseline_hash: str | None, *items):
        diagnostics = []
        for source, reference in self._identifier_candidates(*items):
            entry = {
                "source": source,
                "reference_kind": (
                    "url" if self._looks_http(reference)
                    else "path" if "/" in reference
                    else "id"
                ),
                "ok": False,
                "bytes": 0,
                "sha12": None,
                "changed": False,
                "decoder": None,
            }
            try:
                raw, endpoint, status = self._download_candidate_reference(source, reference)
                sha = self._sha12(raw)
                entry.update({
                    "http": status,
                    "endpoint": endpoint,
                    "bytes": len(raw),
                    "sha12": sha,
                    "changed": bool(sha and sha != baseline_hash),
                })
                if not raw or (baseline_hash and sha == baseline_hash):
                    diagnostics.append(entry)
                    continue

                snapshot, decoders = self._decode_any_map(
                    raw, f"v58-{source}", endpoint
                )
                entry["decoders"] = decoders
                if snapshot is not None:
                    entry["ok"] = True
                    entry["decoder"] = next(
                        (
                            d.get("name")
                            for d in decoders
                            if isinstance(d, dict) and d.get("ok")
                        ),
                        "unknown",
                    )
                    self._v58_fresh_snapshot = snapshot
                    self._v58_fresh_meta = {
                        "source": source,
                        "endpoint": endpoint,
                        "sha12": sha,
                        "bytes": len(raw),
                        "decoder": entry["decoder"],
                    }
                    diagnostics.append(entry)
                    return snapshot, diagnostics
            except Exception as exc:
                entry["error"] = self._sanitize_error(exc)
            diagnostics.append(entry)
        return None, diagnostics

    # --------------------------------------------------------- refresh total
    def request_fresh_upload(self):
        privacy_before = None
        try:
            privacy_before = self.map_privacy_state()
            if privacy_before == 1:
                self.enable_map_upload_temporarily()
        except Exception:
            pass

        try:
            baseline_raw, _endpoint, _status = self._download_slot("0")
            baseline_hash = self._sha12(baseline_raw)
        except Exception as exc:
            baseline_hash = None
            baseline_error = self._sanitize_error(exc)
        else:
            baseline_error = None

        started = int(time.time()) - 3
        attempts = []
        event_queries = {}
        events = []
        candidate_probes = []
        winner = None
        final_hash = baseline_hash

        sequence = (
            (18, [], "upmapdata"),
            (15, [0], "upload-by-maptype-ii · Realtime"),
            (6, [0], "upload-by-maptype · Realtime"),
        )

        for aiid, params, label in sequence:
            lan = self._call_realtime_upload(aiid, params, label)
            lan["transport"] = "lan"
            attempts.append(lan)

            # El Cloud action es la vía que usa Mi Home. Sólo repetimos la misma
            # acción documentada; no añadimos acciones distintas.
            cloud_item = self._call_cloud_action(aiid, params, label)
            attempts.append(cloud_item)

            time.sleep(self.CANDIDATE_SETTLE_SECONDS)

            # 1) outputs directos de LAN/Cloud pueden contener map-id/timestamp/ref.
            snapshot, probes = self._probe_action_candidates(
                baseline_hash, lan, cloud_item
            )
            candidate_probes.extend(probes)
            if snapshot is not None:
                winner = f"{cloud_item.get('action')}:{self._v58_fresh_meta.get('source')}"
                final_hash = self._v58_fresh_meta.get("sha12")
                break

            # 2) consulta eventos con/sin uid usando todos los endpoints conocidos.
            try:
                events, event_queries = self._recent_live_events(started)
            except Exception as exc:
                event_queries = {
                    "error": self._sanitize_error(exc)
                }

            event_items = []
            for event in events[:12]:
                event_items.append({
                    "map_id": event.get("map_id"),
                    "timestamp": event.get("timestamp"),
                    "map_type": event.get("map_type"),
                    "renew_map": event.get("renew_map"),
                    "_ref_values": [],
                })
            snapshot, probes = self._probe_action_candidates(
                baseline_hash, *event_items
            )
            candidate_probes.extend(probes)
            if snapshot is not None:
                winner = f"event:{self._v58_fresh_meta.get('source')}"
                final_hash = self._v58_fresh_meta.get("sha12")
                break

            # 3) último fallback: slot 0 por si cambió sin evento.
            try:
                raw, endpoint, status = self._download_slot("0")
                current = self._sha12(raw)
                final_hash = current or final_hash
                if baseline_hash and current and current != baseline_hash:
                    snapshot, decoders = self._decode_any_map(raw, "slot0-fresh", endpoint)
                    candidate_probes.append({
                        "source": "slot0",
                        "reference_kind": "slot",
                        "ok": snapshot is not None,
                        "http": status,
                        "bytes": len(raw),
                        "sha12": current,
                        "changed": True,
                        "decoders": decoders,
                    })
                    if snapshot is not None:
                        self._v58_fresh_snapshot = snapshot
                        self._v58_fresh_meta = {
                            "source": "slot0",
                            "endpoint": endpoint,
                            "sha12": current,
                            "bytes": len(raw),
                            "decoder": next(
                                (
                                    d.get("name")
                                    for d in decoders
                                    if isinstance(d, dict) and d.get("ok")
                                ),
                                "unknown",
                            ),
                        }
                        winner = f"slot0:{aiid}"
                        break
            except Exception:
                pass

        clean_diag = None
        try:
            latest, clean_diag = self._latest_clean_end()
            if latest is not None:
                _ts, _src, _rec, meta = latest
                snapshot, probes = self._probe_action_candidates(
                    baseline_hash,
                    {
                        "map_id": meta.get("map_id"),
                        "timestamp": meta.get("record_start_time"),
                        "_ref_values": (
                            [("record-map-url", str(meta.get("record_map_url")))]
                            if meta.get("record_map_url")
                            else []
                        ),
                    },
                )
                candidate_probes.extend(probes)
                if snapshot is not None and winner is None:
                    winner = "clean-end:record-map-url"
                    final_hash = self._v58_fresh_meta.get("sha12")
        except Exception as exc:
            clean_diag = {"error": self._sanitize_error(exc)}

        self.last_v58_diagnostics = {
            "baseline_hash": baseline_hash,
            "baseline_error": baseline_error,
            "hash_after": final_hash,
            "winner": winner,
            "attempts": attempts,
            "events": events[:12],
            "event_queries": event_queries,
            "candidate_probes": candidate_probes[-40:],
            "clean_end": clean_diag,
            "fresh_meta": dict(self._v58_fresh_meta or {}),
        }

        info = {
            "official_actions": True,
            "privacy_before": privacy_before,
            "baseline_hash": baseline_hash,
            "attempts": attempts,
            "winner": winner,
            "hash_after": final_hash,
            "changed": bool(winner and final_hash and final_hash != baseline_hash),
            "ok": any(bool(x.get("ok")) for x in attempts),
            "map_id": next(
                (
                    x.get("map_id")
                    for x in reversed(attempts)
                    if x.get("map_id") is not None
                ),
                0,
            ),
        }
        self.last_v56_upload_diagnostics = dict(info)
        self.last_upload_diagnostics = dict(info)
        return info

    # --------------------------------------------------------------- load
    def load(self):
        if self._v58_fresh_snapshot is not None:
            snapshot = self._v58_fresh_snapshot
            self._v58_fresh_snapshot = None
            self.last_v57_diagnostics = {
                **dict(getattr(self, "last_v57_diagnostics", {}) or {}),
                "route": "V58 realtime Cloud/FDS",
                "success": True,
                "source": "v58-fresh",
            }
            return snapshot
        return super().load()

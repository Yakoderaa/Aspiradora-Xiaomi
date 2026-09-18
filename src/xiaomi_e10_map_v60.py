import concurrent.futures
import json
import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

from xiaomi_e10_map_v57 import XiaomiE10MapV57
from xiaomi_e10_map_v59 import XiaomiE10MapV59


class XiaomiE10MapV60(XiaomiE10MapV59):
    """V60: B112 estructurado, LAN serial y FDS sin falsos candidatos."""

    STALE_SLOT0_SHA12 = "0a0ad83e5049"
    LAN_SETTLE_SECONDS = 0.7
    FDS_WORKERS = 3
    MAX_FDS_CANDIDATES = 28

    STRUCTURED_PROPS = (
        ("record_map_url", 7, 30),
        ("clean_current_map", 7, 33),
        ("record_task_status", 7, 37),
        ("cur_map_id", 10, 2),
        ("map_num", 10, 3),
        ("map_list", 10, 4),
        ("has_new_map", 10, 19),
    )

    def __init__(self, *args, **kwargs):
        self.last_v60_diagnostics: dict[str, Any] = {}
        self._v60_lan_lock = threading.RLock()
        self._v60_last_cycle_monotonic = 0.0
        self._v60_slot0_hash = None
        super().__init__(*args, **kwargs)

    # ----------------------------------------------------------- sanitizado
    @staticmethod
    def _redact_error_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "error sin detalle"

        # Nunca sacar URLs firmadas / rutas FDS al diagnóstico.
        def replace_url(match):
            raw = match.group(0)
            try:
                parsed = urlparse(raw)
                if parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}/<redacted>"
            except Exception:
                pass
            return "<signed-url-redacted>"

        text = re.sub(r"https?://[^\s'\"]+", replace_url, text)
        text = re.sub(r"(?i)(GalaxyAccessKeyId|Signature|Expires)=[^&\s]+", r"\1=<redacted>", text)
        return text[:260]

    @classmethod
    def _sanitize_error(cls, exc: Exception):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            return f"HTTP {status} · URL FDS saneada"
        return cls._redact_error_text(exc)

    # -------------------------------------------------------------- helpers
    @classmethod
    def _out_values(cls, response: Any) -> dict[int, Any]:
        """Extrae EXCLUSIVAMENTE valores de items out[{piid,value}]."""
        values: dict[int, Any] = {}
        decoded = cls._extract_result_any(response)
        for node in cls._walk(decoded):
            if not isinstance(node, dict):
                continue
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
                if "value" in item:
                    values[piid] = item.get("value")
        return values

    @staticmethod
    def _int_value(value):
        try:
            if isinstance(value, bool):
                return None
            parsed = int(float(value))
            return parsed
        except Exception:
            return None

    @staticmethod
    def _value_shape(value):
        if value is None:
            return {"kind": "none"}
        if isinstance(value, str):
            stripped = value.strip()
            return {
                "kind": "str",
                "len": len(stripped),
                "jsonish": stripped.startswith(("[", "{")),
                "http": stripped.startswith(("http://", "https://")),
                "path": "/" in stripped,
                "placeholder": stripped.lower() in ("hello", "retry", "none", "null"),
            }
        if isinstance(value, list):
            return {"kind": "list", "len": len(value)}
        if isinstance(value, dict):
            return {"kind": "dict", "keys": sorted(str(k) for k in value.keys())[:10]}
        return {"kind": type(value).__name__, "value": value if isinstance(value, (int, float, bool)) else None}

    @classmethod
    def _parse_map_list_value(cls, value):
        raw = value
        if isinstance(raw, str):
            text = raw.strip()
            if not text or text.lower() in ("hello", "retry", "none", "null"):
                return [], {"shape": cls._value_shape(raw), "json": False}
            try:
                raw = json.loads(text)
            except Exception:
                return [], {"shape": cls._value_shape(value), "json": False}

        if isinstance(raw, dict):
            for key in ("list", "maps", "data", "result"):
                candidate = raw.get(key)
                if isinstance(candidate, list):
                    raw = candidate
                    break

        if not isinstance(raw, list):
            return [], {"shape": cls._value_shape(value), "json": isinstance(value, str)}

        maps = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            map_id = cls._int_value(item.get("id", item.get("map_id")))
            if map_id is None or map_id <= 0:
                continue
            maps.append({
                "id": map_id,
                "cur": bool(item.get("cur", item.get("current", False))),
                "name_present": bool(item.get("name")),
            })
        return maps, {
            "shape": cls._value_shape(value),
            "json": True,
            "items": len(raw),
            "valid_maps": len(maps),
        }

    @classmethod
    def _action_meta_exact(cls, response: Any):
        out = cls._out_values(response)
        return {
            "code": cls._response_code(response),
            "out_piids": sorted(out.keys()),
            "map_id": cls._int_value(out.get(6)),
            "map_type": cls._int_value(out.get(7)),
            "timestamp": cls._int_value(out.get(18)),
            "renew_map": cls._int_value(out.get(21)),
        }

    @classmethod
    def _known_refs_only(cls, response: Any):
        refs = []
        seen = set()
        for source, value in cls._object_refs_from_response(response):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text or text.lower() in ("hello", "retry", "none", "null", "cloud"):
                continue
            sig = (str(source), text)
            if sig in seen:
                continue
            seen.add(sig)
            refs.append(sig)
        return refs

    def _record_v60(self, method, started, **data):
        item = {
            "method": method,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "ok": bool(data.pop("ok", False)),
        }
        item["status"] = data.pop("status", "OK" if item["ok"] else "FAIL")
        item.update(data)
        self.last_v60_diagnostics.setdefault("methods", []).append(item)
        return item

    # --------------------------------------------------------- props exactas
    def _props_lan_structured(self):
        started = time.monotonic()
        method = "B112 props LAN aisladas"
        try:
            payload = [
                {"did": f"v60-{siid}-{piid}", "siid": siid, "piid": piid}
                for _name, siid, piid in self.STRUCTURED_PROPS
            ]
            with self._v60_lan_lock:
                rows = self.vacuum.device.send("get_properties", payload)
            if isinstance(rows, dict):
                rows = rows.get("result") or rows.get("data") or rows.get("out") or []
            values = {}
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or row.get("code", 0) not in (0, None):
                    continue
                try:
                    key = (int(row.get("siid")), int(row.get("piid")))
                except Exception:
                    continue
                values[key] = row.get("value")
            named = {
                name: values.get((siid, piid))
                for name, siid, piid in self.STRUCTURED_PROPS
            }
            ids, refs, maps = self._structured_refs_from_named(named, "LAN")
            self._record_v60(
                method, started, ok=True,
                map_ids=ids,
                map_count=len(maps),
                props={k: self._value_shape(v) for k, v in named.items()},
                refs=len(refs),
            )
            return ids, refs, named
        except Exception as exc:
            self._record_v60(method, started, error=self._sanitize_error(exc))
            return [], [], {}

    def _props_cloud_structured(self, datasource):
        started = time.monotonic()
        method = f"B112 props Cloud datasource={datasource}"
        try:
            payload = {
                "params": [
                    {"did": self.did, "siid": siid, "piid": piid}
                    for _name, siid, piid in self.STRUCTURED_PROPS
                ],
                "datasource": int(datasource),
            }
            response = self._cloud().request_country(
                "/miotspec/prop/get",
                self.region,
                {"data": json.dumps(payload, separators=(",", ":"))},
            )
            decoded = self._extract_result_any(response)
            values = {}
            if isinstance(decoded, dict):
                for row in decoded.get("result") or []:
                    if not isinstance(row, dict) or row.get("code", 0) not in (0, None):
                        continue
                    try:
                        values[(int(row.get("siid")), int(row.get("piid")))] = row.get("value")
                    except Exception:
                        continue
            named = {
                name: values.get((siid, piid))
                for name, siid, piid in self.STRUCTURED_PROPS
            }
            ids, refs, maps = self._structured_refs_from_named(named, f"Cloud{datasource}")
            self._record_v60(
                method, started, ok=True,
                map_ids=ids,
                map_count=len(maps),
                props={k: self._value_shape(v) for k, v in named.items()},
                refs=len(refs),
            )
            return ids, refs, named
        except Exception as exc:
            self._record_v60(method, started, error=self._sanitize_error(exc))
            return [], [], {}

    def _structured_refs_from_named(self, named, source):
        refs = []
        ids = []
        maps = []

        direct = named.get("record_map_url")
        if isinstance(direct, str):
            text = direct.strip()
            if text and text.lower() not in ("hello", "retry", "none", "null"):
                refs.append((f"{source}:7/30", text, 0))

        for key in ("clean_current_map", "cur_map_id"):
            map_id = self._int_value(named.get(key))
            if map_id is not None and map_id > 0:
                ids.append(map_id)

        parsed_maps, _diag = self._parse_map_list_value(named.get("map_list"))
        maps.extend(parsed_maps)
        ids.extend(item["id"] for item in parsed_maps)

        return sorted(set(ids)), refs, maps

    # -------------------------------------------------------- actions exactas
    def _call_lan_action_exact(self, aiid, params, label):
        started = time.monotonic()
        method = f"LAN 10/{aiid} {label}"
        try:
            with self._v60_lan_lock:
                response = self.vacuum.device.call_action_by(10, int(aiid), list(params))
            meta = self._action_meta_exact(response)
            refs = self._known_refs_only(response)
            code = meta.get("code")
            ok = code in (None, 0, "0")
            item = self._record_v60(
                method, started, ok=ok,
                code=code,
                out_piids=meta.get("out_piids"),
                map_id=meta.get("map_id"),
                map_type=meta.get("map_type"),
                timestamp=meta.get("timestamp"),
                renew_map=meta.get("renew_map"),
                refs=len(refs),
            )
            return item, refs, response
        except Exception as exc:
            item = self._record_v60(method, started, error=self._sanitize_error(exc))
            return item, [], None

    def _call_cloud_action_exact(self, aiid, params, label):
        started = time.monotonic()
        method = f"Cloud 10/{aiid} {label}"
        body = {
            "params": {
                "did": str(self.did),
                "siid": 10,
                "aiid": int(aiid),
                "in": list(params),
            }
        }
        errors = []
        for endpoint in self.CLOUD_ACTION_ENDPOINTS:
            try:
                response = self._cloud().request_country(
                    endpoint,
                    self.region,
                    {"data": json.dumps(body, separators=(",", ":"))},
                )
                meta = self._action_meta_exact(response)
                refs = self._known_refs_only(response)
                code = meta.get("code")
                if code not in (None, 0, "0"):
                    raise RuntimeError(f"code={code}")
                item = self._record_v60(
                    method, started, ok=True,
                    endpoint=endpoint.rsplit("/", 1)[-1],
                    code=code,
                    out_piids=meta.get("out_piids"),
                    map_id=meta.get("map_id"),
                    map_type=meta.get("map_type"),
                    timestamp=meta.get("timestamp"),
                    renew_map=meta.get("renew_map"),
                    refs=len(refs),
                )
                return item, refs, response
            except Exception as exc:
                errors.append(
                    f"{endpoint.rsplit('/', 1)[-1]}:{self._sanitize_error(exc)}"
                )
        item = self._record_v60(method, started, error=" | ".join(errors[-2:]))
        return item, [], None

    def _map_list_exact(self):
        ids = []
        refs = []
        details = []
        for transport in ("lan", "cloud"):
            started = time.monotonic()
            method = f"10/1 get-map-list {transport} aislado"
            response = None
            try:
                if transport == "lan":
                    with self._v60_lan_lock:
                        response = self.vacuum.device.call_action_by(10, 1, [])
                else:
                    body = {
                        "params": {
                            "did": str(self.did),
                            "siid": 10,
                            "aiid": 1,
                            "in": [],
                        }
                    }
                    last_error = None
                    for endpoint in self.CLOUD_ACTION_ENDPOINTS:
                        try:
                            candidate = self._cloud().request_country(
                                endpoint, self.region,
                                {"data": json.dumps(body, separators=(",", ":"))},
                            )
                            code = self._response_code(candidate)
                            if code not in (None, 0, "0"):
                                raise RuntimeError(f"code={code}")
                            response = candidate
                            break
                        except Exception as exc:
                            last_error = exc
                    if response is None and last_error is not None:
                        raise last_error

                out = self._out_values(response)
                value = out.get(4)
                maps, parse_diag = self._parse_map_list_value(value)
                local_ids = [m["id"] for m in maps]
                ids.extend(local_ids)
                refs.extend(
                    (f"10/1:{transport}:{src}", ref, 1)
                    for src, ref in self._known_refs_only(response)
                )
                details.append({
                    "transport": transport,
                    "out_piids": sorted(out.keys()),
                    "piid4": parse_diag,
                    "map_ids": local_ids,
                })
                self._record_v60(
                    method, started, ok=True,
                    out_piids=sorted(out.keys()),
                    piid4=parse_diag,
                    map_ids=local_ids,
                    map_count=len(maps),
                    refs=len(self._known_refs_only(response)),
                )
            except Exception as exc:
                details.append({"transport": transport, "error": self._sanitize_error(exc)})
                self._record_v60(method, started, error=self._sanitize_error(exc))
            time.sleep(0.15)
        return sorted(set(ids)), refs, details

    # -------------------------------------------------------- candidatos FDS
    @staticmethod
    def _plausible_timestamp(value):
        try:
            value = int(value)
            return 1_500_000_000 <= value <= 4_294_967_295
        except Exception:
            return False

    def _refs_from_action_item(self, item, explicit_refs, source):
        refs = []
        for ref_source, ref in explicit_refs:
            refs.append((f"{source}:explicit:{ref_source}", str(ref), 0))

        mid = self._int_value(item.get("map_id"))
        mtype = self._int_value(item.get("map_type"))
        ts = self._int_value(item.get("timestamp"))
        renew = self._int_value(item.get("renew_map"))

        if mid is not None and mid > 0:
            refs.append((f"{source}:map-id", str(mid), 3))
        if self._plausible_timestamp(ts):
            refs.append((f"{source}:timestamp", str(ts), 4))
        if mid is not None and mid > 0 and self._plausible_timestamp(ts):
            patterns = [
                (f"{mid}_{ts}", "mapid_timestamp"),
                (f"{ts}_{mid}", "timestamp_mapid"),
            ]
            if mtype is not None and 0 <= mtype <= 3:
                patterns.extend([
                    (f"{mid}_{mtype}_{ts}", "mapid_type_timestamp"),
                    (f"{mid}-{mtype}-{ts}", "mapid-type-timestamp"),
                ])
            # El bucket es *.record: algunas generaciones añaden extensión.
            patterns.extend([
                (f"{mid}_{ts}.record", "mapid_timestamp.record"),
                (f"{ts}_{mid}.record", "timestamp_mapid.record"),
            ])
            priority = 1 if renew == 1 else 5
            for value, label in patterns:
                refs.append((f"{source}:{label}", value, priority))
        return refs

    @staticmethod
    def _dedupe_refs(refs):
        seen = set()
        out = []
        for source, ref, priority in refs:
            text = str(ref or "").strip()
            if not text or text.lower() in ("0", "hello", "retry", "none", "null", "cloud"):
                continue
            sig = text
            if sig in seen:
                continue
            seen.add(sig)
            out.append((source, text, int(priority)))
        out.sort(key=lambda x: (x[2], len(x[1])))
        return out

    def _probe_one_ref(self, source, ref, baseline_hash):
        started = time.monotonic()
        method = f"FDS {source}"
        try:
            raw, endpoint, status = self._download_candidate_reference(source, ref)
            sha = self._sha12(raw)
            if not raw:
                return self._record_v60(
                    method, started, status="FAIL", http=status,
                    endpoint=endpoint, bytes=0, sha12=sha,
                ), None
            if baseline_hash and sha == baseline_hash:
                return self._record_v60(
                    method, started, status="STALE", http=status,
                    endpoint=endpoint, bytes=len(raw), sha12=sha,
                ), None

            snapshot, decoders = self._decode_any_map(raw, f"v60-{source}", endpoint)
            ok = snapshot is not None
            item = self._record_v60(
                method, started, ok=ok,
                http=status, endpoint=endpoint,
                bytes=len(raw), sha12=sha,
                decoders=decoders,
            )
            return item, snapshot
        except Exception as exc:
            return self._record_v60(
                method, started, error=self._sanitize_error(exc)
            ), None

    def _probe_refs(self, refs, baseline_hash):
        refs = self._dedupe_refs(refs)[:self.MAX_FDS_CANDIDATES]
        self.last_v60_diagnostics["candidate_refs"] = len(refs)
        if not refs:
            return None

        # Sólo Cloud/FDS aquí: ninguna llamada LAN en paralelo.
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.FDS_WORKERS)
        futures = {
            executor.submit(self._probe_one_ref, source, ref, baseline_hash): (source, ref)
            for source, ref, _priority in refs
        }
        winner = None
        try:
            for fut in concurrent.futures.as_completed(futures):
                try:
                    item, snapshot = fut.result()
                except Exception:
                    continue
                if snapshot is not None and winner is None:
                    winner = snapshot
                    self._accept_snapshot(item.get("method", "V60 FDS"), snapshot, item)
                    break
        finally:
            for fut in futures:
                if not fut.done():
                    fut.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        return winner

    # -------------------------------------------------------- clean-end corto
    def _clean_end_quick(self):
        started = time.monotonic()
        method = "Cloud clean-end 7.1 rápido"
        end = int(time.time()) + 30
        start = max(
            0,
            end - 24 * 3600,
            int(float(getattr(self, "_v57_session_started_at", 0.0) or 0.0)) - 120,
        )
        variants = (
            ("/v2/user/get_user_device_data", "event", False),
            ("/user/get_user_device_data", "event", False),
            ("/v2/user/get_device_data_raw", "store", False),
        )
        diagnostics = []
        candidates = []
        for endpoint, typ, include_uid in variants:
            try:
                records, detail = self._history_request_variant(
                    endpoint, self.CLEAN_END_KEY, typ, start, end, include_uid
                )
                diagnostics.append({"ok": True, **detail})
                for record in records:
                    meta = self._event_meta(record)
                    ref = meta.get("record_map_url")
                    if ref:
                        candidates.append((
                            self._record_time(record) or 0.0,
                            endpoint.rsplit("/", 1)[-1],
                            str(ref),
                        ))
                if candidates:
                    break
            except Exception as exc:
                diagnostics.append({
                    "ok": False,
                    "endpoint": endpoint.rsplit("/", 1)[-1],
                    "error": self._sanitize_error(exc),
                })

        candidates.sort(key=lambda x: x[0], reverse=True)
        refs = [
            (f"clean-end:{source}", ref, 0)
            for _when, source, ref in candidates[:3]
        ]
        self._record_v60(
            method, started, ok=True,
            records=sum(int(x.get("records", 0) or 0) for x in diagnostics if isinstance(x, dict)),
            refs=len(refs),
            queries=diagnostics,
        )
        return refs

    # ---------------------------------------------------------- slot 0 corto
    def _slot0_baseline(self):
        started = time.monotonic()
        method = "slot 0 baseline"
        try:
            raw, endpoint, status = self._download_slot("0")
            sha = self._sha12(raw)
            previous = self._v60_slot0_hash
            self._v60_slot0_hash = sha or previous
            changed = bool(previous and sha and previous != sha)
            stale_known = sha == self.STALE_SLOT0_SHA12
            item = self._record_v60(
                method, started, ok=True, http=status, endpoint=endpoint,
                bytes=len(raw), sha12=sha, changed=changed,
                known_stale=stale_known,
            )
            if raw and (changed or not stale_known):
                snapshot, decoders = self._decode_any_map(raw, "v60-slot0", endpoint)
                item["decoders"] = decoders
                if snapshot is not None:
                    self._accept_snapshot(method, snapshot, item)
                    return sha, snapshot
            return sha, None
        except Exception as exc:
            self._record_v60(method, started, error=self._sanitize_error(exc))
            return None, None

    # --------------------------------------------------------------- ciclo
    def _run_v60_cycle(self):
        self._v60_last_cycle_monotonic = time.monotonic()
        self._v59_last_race_monotonic = self._v60_last_cycle_monotonic
        self._v59_stop.clear()
        self._v59_cached_snapshot = None
        self._v59_cached_winner = None
        self.last_v60_diagnostics = {
            "started_at": time.time(),
            "finished_at": None,
            "phase": "structured",
            "winner": None,
            "winner_meta": {},
            "methods": [],
            "candidate_refs": 0,
            "map_ids": [],
            "false_v59_mapid4_fixed": True,
            "lan_serialized": True,
        }

        refs = []
        ids = []

        baseline_hash, baseline_snapshot = self._slot0_baseline()
        if baseline_snapshot is not None:
            self.last_v60_diagnostics["winner"] = self._v59_cached_winner
            self.last_v60_diagnostics["winner_meta"] = self.last_v59_diagnostics.get("winner_meta", {})
            self.last_v60_diagnostics["phase"] = "done"
            self.last_v60_diagnostics["finished_at"] = time.time()
            return baseline_snapshot

        # Props LAN aisladas: ya no compiten con legacy calls.
        local_ids, local_refs, _ = self._props_lan_structured()
        ids.extend(local_ids)
        refs.extend(local_refs)

        # Cloud datasource 1/2: pueden aportar record-map-url/map-id sin tocar LAN.
        for datasource in (1, 2):
            cloud_ids, cloud_refs, _ = self._props_cloud_structured(datasource)
            ids.extend(cloud_ids)
            refs.extend(cloud_refs)

        # 10/1 se ejecuta aislado y sólo PIID 4 puede originar map IDs.
        list_ids, list_refs, map_list_detail = self._map_list_exact()
        ids.extend(list_ids)
        refs.extend(list_refs)
        self.last_v60_diagnostics["map_list"] = map_list_detail

        ids = sorted(set(i for i in ids if isinstance(i, int) and i > 0))
        self.last_v60_diagnostics["map_ids"] = ids

        # Si existe un ID REAL, consultar exactamente los outputs documentados.
        for map_id in ids[:5]:
            for aiid, label in ((14, "upload-by-mapid-ii"), (2, "upload-by-mapid")):
                lan_item, lan_refs, _ = self._call_lan_action_exact(aiid, [map_id], label)
                refs.extend(self._refs_from_action_item(lan_item, lan_refs, f"LAN10/{aiid}"))
                time.sleep(self.LAN_SETTLE_SECONDS)

                cloud_item, cloud_refs, _ = self._call_cloud_action_exact(aiid, [map_id], label)
                refs.extend(self._refs_from_action_item(cloud_item, cloud_refs, f"Cloud10/{aiid}"))

        # Realtime documentado, serial en LAN para evitar -30012 busy.
        for aiid, params, label in (
            (18, [], "upmapdata"),
            (15, [0], "upload-by-maptype-ii realtime"),
            (6, [0], "upload-by-maptype realtime"),
        ):
            lan_item, lan_refs, _ = self._call_lan_action_exact(aiid, params, label)
            refs.extend(self._refs_from_action_item(lan_item, lan_refs, f"LAN10/{aiid}"))
            time.sleep(self.LAN_SETTLE_SECONDS)

            cloud_item, cloud_refs, _ = self._call_cloud_action_exact(aiid, params, label)
            refs.extend(self._refs_from_action_item(cloud_item, cloud_refs, f"Cloud10/{aiid}"))

        # 7.1: sólo tres variantes probables, sin matriz exhaustiva de 50 s.
        refs.extend(self._clean_end_quick())

        self.last_v60_diagnostics["phase"] = "fds"
        winner = self._probe_refs(refs, baseline_hash)
        if winner is not None:
            self.last_v60_diagnostics["winner"] = self._v59_cached_winner
            self.last_v60_diagnostics["winner_meta"] = dict(
                self.last_v59_diagnostics.get("winner_meta", {}) or {}
            )

        self.last_v60_diagnostics["phase"] = "done"
        self.last_v60_diagnostics["finished_at"] = time.time()
        return winner

    # ------------------------------------------------------------- public API
    def request_fresh_upload(self):
        started = time.monotonic()
        snapshot = self._run_v60_cycle()
        return {
            "official_actions": True,
            "structured_b112": True,
            "ok": snapshot is not None,
            "winner": self._v59_cached_winner,
            "changed": snapshot is not None,
            "map_id": (
                (self.last_v60_diagnostics.get("map_ids") or [None])[0]
                if self.last_v60_diagnostics.get("map_ids") else None
            ),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    def load(self):
        if self._v59_cached_snapshot is not None:
            return self._v59_cached_snapshot

        # No relanzar el ciclo inmediatamente si el UI acaba de pedir refresh.
        if time.monotonic() - float(self._v60_last_cycle_monotonic or 0.0) >= 8.0:
            snapshot = self._run_v60_cycle()
            if snapshot is not None:
                return snapshot

        # Saltamos V59 para no volver a disparar los legacy concurrentes.
        return XiaomiE10MapV57.load(self)

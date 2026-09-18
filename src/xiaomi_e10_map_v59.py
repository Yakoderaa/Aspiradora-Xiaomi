import concurrent.futures
import json
import threading
import time
from typing import Any

from xiaomi_e10_map_v58 import XiaomiE10MapV58


class XiaomiE10MapV59(XiaomiE10MapV58):
    """V59: competencia multi-ruta para obtener el mapa real del B112."""

    QUICK_TIMEOUT = 5.0
    LEGACY_TIMEOUT = 3.0
    MAX_WORKERS = 10
    MAP_NAME_RETRIES = 5

    PROP_SPECS = (
        ("start_time", 7, 27),
        ("use_time", 7, 28),
        ("clean_area", 7, 29),
        ("map_url", 7, 30),
        ("clean_mode", 7, 31),
        ("clean_way", 7, 32),
        ("current_map", 7, 33),
        ("task_status", 7, 37),
        ("cur_map_id", 10, 2),
        ("map_list_prop", 10, 4),
    )

    LEGACY_COMMANDS = (
        ("get_map_v1", []),
        ("get_map_v2", []),
        ("get_map", []),
        ("get_fresh_map", []),
        ("get_fresh_map_v2", []),
        ("get_persist_map", []),
        ("get_persist_map_v2", []),
        ("get_multi_map", []),
        ("get_recover_maps", []),
        ("get_clean_summary", []),
        ("get_clean_record", []),
        ("get_clean_record_map", []),
        ("get_clean_record_map_v2", []),
    )

    def __init__(self, *args, **kwargs):
        self.last_v59_diagnostics: dict[str, Any] = {}
        self._v59_cached_snapshot = None
        self._v59_cached_winner = None
        self._v59_lock = threading.Lock()
        self._v59_stop = threading.Event()
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _safe_value(value: Any):
        if value is None:
            return None
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            text = value.strip()
            return {
                "type": "str",
                "len": len(text),
                "http": text.startswith(("http://", "https://")),
                "path": "/" in text,
                "percent": "%" in text,
                "numeric": text.isdigit(),
            }
        if isinstance(value, list):
            return {"type": "list", "len": len(value)}
        if isinstance(value, dict):
            return {"type": "dict", "keys": sorted(str(k) for k in value.keys())[:12]}
        return {"type": type(value).__name__}

    @staticmethod
    def _flatten_refs(value: Any):
        out = []
        seen = set()

        def add(source, item):
            if item is None:
                return
            if isinstance(item, (int, float)):
                text = str(int(item)) if isinstance(item, float) and item.is_integer() else str(item)
            elif isinstance(item, str):
                text = item.strip()
            else:
                return
            if not text or text.lower() in ("none", "null", "retry", "0"):
                return
            key = (source, text)
            if key not in seen:
                seen.add(key)
                out.append(key)

        def walk(node, source="value"):
            if isinstance(node, dict):
                for key, val in node.items():
                    walk(val, str(key))
            elif isinstance(node, list):
                for idx, val in enumerate(node):
                    walk(val, f"{source}[{idx}]")
            else:
                add(source, node)

        walk(value)
        return out

    def _record_result(self, name, started, *, ok=False, status="FAIL", **extra):
        item = {
            "method": name,
            "status": status,
            "ok": bool(ok),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        item.update(extra)
        with self._v59_lock:
            rows = self.last_v59_diagnostics.setdefault("methods", [])
            rows.append(item)
        return item

    def _accept_snapshot(self, method, snapshot, meta=None):
        if snapshot is None:
            return False
        with self._v59_lock:
            if self._v59_cached_snapshot is not None:
                return False
            self._v59_cached_snapshot = snapshot
            self._v59_cached_winner = method
            self.last_v59_diagnostics["winner"] = method
            self.last_v59_diagnostics["winner_meta"] = dict(meta or {})
            self._v59_stop.set()
        return True

    # --------------------------------------------------------- direct props
    def _lan_props_all(self):
        started = time.monotonic()
        try:
            payload = [
                {"did": f"v59-{siid}-{piid}", "siid": siid, "piid": piid}
                for _name, siid, piid in self.PROP_SPECS
            ]
            rows = self.vacuum.device.send("get_properties", payload)
            if isinstance(rows, dict):
                rows = rows.get("result") or rows.get("data") or rows.get("out") or []
            values = {}
            if isinstance(rows, list):
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    try:
                        siid = int(item.get("siid"))
                        piid = int(item.get("piid"))
                    except Exception:
                        continue
                    if item.get("code", 0) not in (0, None):
                        continue
                    values[(siid, piid)] = item.get("value")
            named = {
                name: values.get((siid, piid))
                for name, siid, piid in self.PROP_SPECS
            }
            refs = []
            for key in ("map_url", "current_map", "cur_map_id", "map_list_prop"):
                refs.extend((f"LAN:{key}:{src}", ref) for src, ref in self._flatten_refs(named.get(key)))
            self._record_result(
                "MIoT props LAN 7/30+7/33+10/2+10/4",
                started, ok=True, status="OK",
                values={k: self._safe_value(v) for k, v in named.items()},
                refs=len(refs),
            )
            return refs
        except Exception as exc:
            self._record_result(
                "MIoT props LAN 7/30+7/33+10/2+10/4",
                started, error=self._sanitize_error(exc),
            )
            return []

    def _cloud_props_all(self, datasource):
        started = time.monotonic()
        name = f"MIoT props Cloud datasource={datasource}"
        try:
            payload = {
                "params": [
                    {"did": self.did, "siid": siid, "piid": piid}
                    for _n, siid, piid in self.PROP_SPECS
                ],
                "datasource": datasource,
            }
            response = self._cloud().request_country(
                "/miotspec/prop/get",
                self.region,
                {"data": json.dumps(payload, separators=(",", ":"))},
            )
            decoded = self._decode_cloud_json(response)
            values = {}
            for item in decoded.get("result") or []:
                if not isinstance(item, dict) or item.get("code", 0) not in (0, None):
                    continue
                try:
                    values[(int(item.get("siid")), int(item.get("piid")))] = item.get("value")
                except Exception:
                    continue
            named = {
                n: values.get((s, p))
                for n, s, p in self.PROP_SPECS
            }
            refs = []
            for key in ("map_url", "current_map", "cur_map_id", "map_list_prop"):
                refs.extend((f"Cloud{datasource}:{key}:{src}", ref) for src, ref in self._flatten_refs(named.get(key)))
            self._record_result(
                name, started, ok=True, status="OK",
                values={k: self._safe_value(v) for k, v in named.items()},
                refs=len(refs),
            )
            return refs
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))
            return []

    # -------------------------------------------------------- legacy MiIO
    def _legacy_command(self, command, params):
        started = time.monotonic()
        name = f"MiIO legacy {command}"
        try:
            response = self.vacuum.device.send(command, list(params))
            refs = self._flatten_refs(response)
            self._record_result(
                name, started, ok=True, status="OK",
                response=self._safe_value(response),
                refs=len(refs),
            )
            return [(f"legacy:{command}:{src}", ref) for src, ref in refs]
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))
            return []

    def _legacy_map_pointer(self):
        """Reintento corto de get_map_v1 como usan extractores Xiaomi clásicos."""
        started = time.monotonic()
        name = "MiIO get_map_v1 pointer retry"
        attempts = []
        refs = []
        for idx in range(self.MAP_NAME_RETRIES):
            if self._v59_stop.is_set():
                break
            try:
                response = self.vacuum.device.send("get_map_v1", [])
                attempts.append(self._safe_value(response))
                for src, ref in self._flatten_refs(response):
                    if ref.lower() == "retry":
                        continue
                    refs.append((f"map_v1_retry{idx+1}:{src}", ref))
                if refs:
                    break
            except Exception as exc:
                attempts.append({"error": self._sanitize_error(exc)})
            time.sleep(0.3 * (idx + 1))
        self._record_result(
            name, started,
            ok=bool(refs),
            status="OK" if refs else "FAIL",
            attempts=len(attempts),
            refs=len(refs),
        )
        return refs

    # --------------------------------------------------------- map-list action
    def _map_list_action(self):
        started = time.monotonic()
        name = "MIoT 10/1 get-map-list"
        refs = []
        ids = []
        try:
            for transport in ("lan", "cloud"):
                try:
                    if transport == "lan":
                        response = self.vacuum.device.call_action_by(10, 1, [])
                    else:
                        response = self._call_cloud_action(1, [], "get-map-list")
                    for src, ref in self._flatten_refs(response):
                        refs.append((f"10/1:{transport}:{src}", ref))
                        if str(ref).isdigit() and int(ref) > 0:
                            ids.append(int(ref))
                except Exception:
                    continue
            self._record_result(
                name, started, ok=bool(refs or ids),
                status="OK" if (refs or ids) else "FAIL",
                refs=len(refs), map_ids=sorted(set(ids))[:20],
            )
            return refs, sorted(set(ids))
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))
            return [], []

    def _upload_by_mapid(self, map_id):
        started = time.monotonic()
        name = f"MIoT upload map-id {map_id}"
        refs = []
        try:
            for aiid in (14, 2):
                for transport in ("lan", "cloud"):
                    try:
                        if transport == "lan":
                            response = self.vacuum.device.call_action_by(10, aiid, [int(map_id)])
                        else:
                            response = self._call_cloud_action(aiid, [int(map_id)], f"upload-mapid-{map_id}")
                        for src, ref in self._flatten_refs(response):
                            refs.append((f"10/{aiid}:{transport}:{src}", ref))
                    except Exception:
                        continue
            self._record_result(
                name, started, ok=bool(refs),
                status="OK" if refs else "FAIL",
                refs=len(refs),
            )
            return refs
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))
            return []

    # ----------------------------------------------------- history / events
    def _history_refs(self):
        started = time.monotonic()
        name = "Cloud history 7.1 + events 10.2/10.4/10.6 + device-log"
        refs = []
        try:
            end = int(time.time()) + 30
            start = end - 24 * 3600

            latest, _diag = self._latest_clean_end()
            if latest is not None:
                _ts, _source, _record, meta = latest
                refs.extend(
                    (f"clean-end:{src}", ref)
                    for src, ref in self._flatten_refs(meta)
                )

            events, _event_diag = self._recent_live_events(start)
            for event in events[:30]:
                refs.extend(
                    (f"event:{event.get('key')}:{src}", ref)
                    for src, ref in self._flatten_refs(event)
                )

            logs, _log_diag = self._query_device_log(start, end)
            for record in logs[:50]:
                refs.extend(
                    (f"device-log:{src}", ref)
                    for src, ref in self._flatten_refs(record)
                )

            self._record_result(
                name, started, ok=True, status="OK",
                refs=len(refs),
            )
            return refs
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))
            return []

    # ------------------------------------------------------ slot/classic
    def _slot0_candidate(self):
        started = time.monotonic()
        name = "Cloud slot 0 clásico"
        try:
            raw, endpoint, status = self._download_slot("0")
            snapshot, decoders = self._decode_any_map(raw, "v59-slot0", endpoint)
            valid = snapshot is not None and not (
                getattr(snapshot, "parser_error", None) in (
                    "V57: grid rechazado por incoherencia espacial",
                    "V58: grid rechazado por incoherencia espacial",
                )
            )
            item = self._record_result(
                name, started, ok=valid,
                status="OK" if valid else "FAIL",
                http=status, bytes=len(raw), sha12=self._sha12(raw),
                decoders=decoders,
            )
            if valid:
                self._accept_snapshot(name, snapshot, item)
            return
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))

    # ------------------------------------------------------ FDS resolution
    def _expanded_refs(self, refs):
        user_id = str(self.session_data.get("user_id") or "")
        did = str(self.did or "")
        out = []
        seen = set()

        def add(source, value):
            text = str(value or "").strip()
            if not text or text in ("0", "None"):
                return
            for candidate in (
                text,
                f"{user_id}/{did}/{text}" if user_id and did else "",
                f"{user_id}/{did}/{text.split('/')[-1]}" if user_id and did else "",
            ):
                candidate = candidate.strip("/")
                if not candidate:
                    continue
                key = (source, candidate)
                if key not in seen:
                    seen.add(key)
                    out.append(key)

        for source, ref in refs:
            add(source, ref)
            if "%" in str(ref):
                add(source + ":percent-pointer", ref)
        return out

    def _try_reference(self, source, ref):
        if self._v59_stop.is_set():
            return
        started = time.monotonic()
        name = f"FDS {source}"
        try:
            raw, endpoint, status = self._download_candidate_reference(source, str(ref))
            snapshot, decoders = self._decode_any_map(raw, f"v59-{source}", endpoint)
            valid = snapshot is not None and not (
                getattr(snapshot, "parser_error", None) in (
                    "V57: grid rechazado por incoherencia espacial",
                    "V58: grid rechazado por incoherencia espacial",
                )
            )
            item = self._record_result(
                name, started, ok=valid,
                status="OK" if valid else "FAIL",
                reference_kind=("url" if self._looks_http(str(ref)) else "ref"),
                endpoint=endpoint, http=status,
                bytes=len(raw), sha12=self._sha12(raw),
                decoders=decoders,
            )
            if valid:
                self._accept_snapshot(name, snapshot, item)
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))

    # ----------------------------------------------------- active V58 method
    def _active_v58(self):
        if self._v59_stop.is_set():
            return
        started = time.monotonic()
        name = "V58 active realtime LAN+Cloud+events+FDS"
        try:
            info = super().request_fresh_upload()
            snapshot = getattr(self, "_v58_fresh_snapshot", None)
            valid = snapshot is not None
            item = self._record_result(
                name, started, ok=valid,
                status="OK" if valid else "FAIL",
                winner=(info or {}).get("winner"),
                changed=(info or {}).get("changed"),
                map_id=(info or {}).get("map_id"),
            )
            if valid:
                self._accept_snapshot(name, snapshot, item)
        except Exception as exc:
            self._record_result(name, started, error=self._sanitize_error(exc))

    # ------------------------------------------------------------- race
    def _run_race(self):
        self._v59_stop.clear()
        self.last_v59_diagnostics = {
            "started_at": time.time(),
            "winner": None,
            "winner_meta": {},
            "methods": [],
            "phase": "quick",
        }

        refs = []
        map_ids = []

        # quick source discovery
        quick_jobs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            quick_jobs.extend([
                pool.submit(self._lan_props_all),
                pool.submit(self._cloud_props_all, 1),
                pool.submit(self._cloud_props_all, 2),
                pool.submit(self._legacy_map_pointer),
                pool.submit(self._history_refs),
                pool.submit(self._map_list_action),
                pool.submit(self._slot0_candidate),
            ])
            for command, params in self.LEGACY_COMMANDS:
                quick_jobs.append(pool.submit(self._legacy_command, command, params))

            deadline = time.monotonic() + self.QUICK_TIMEOUT
            for fut in quick_jobs:
                if self._v59_stop.is_set():
                    break
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    result = fut.result(timeout=remaining)
                    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
                        local_refs, local_ids = result
                        refs.extend(local_refs or [])
                        map_ids.extend(local_ids or [])
                    elif isinstance(result, list):
                        refs.extend(result)
                except Exception:
                    continue

        if self._v59_stop.is_set():
            return self._v59_cached_snapshot

        # Map-id uploads discovered from properties / map-list / legacy refs.
        for _source, ref in list(refs):
            text = str(ref)
            if text.isdigit():
                try:
                    val = int(text)
                    if val > 0:
                        map_ids.append(val)
                except Exception:
                    pass
        map_ids = sorted(set(map_ids))[:12]

        self.last_v59_diagnostics["phase"] = "fds+active"
        for map_id in map_ids:
            refs.extend(self._upload_by_mapid(map_id))

        refs = self._expanded_refs(refs)
        self.last_v59_diagnostics["candidate_refs"] = len(refs)
        self.last_v59_diagnostics["map_ids"] = map_ids

        # FDS candidates and full V58 active path race each other.
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            futures = [
                pool.submit(self._try_reference, source, ref)
                for source, ref in refs[:80]
            ]
            futures.append(pool.submit(self._active_v58))
            deadline = time.monotonic() + 12.0
            while futures and time.monotonic() < deadline and not self._v59_stop.is_set():
                done, pending = concurrent.futures.wait(
                    futures,
                    timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                futures = list(pending)
                if self._v59_stop.is_set():
                    break

        self.last_v59_diagnostics["phase"] = "done"
        self.last_v59_diagnostics["finished_at"] = time.time()
        return self._v59_cached_snapshot

    # ------------------------------------------------------------- public
    def request_fresh_upload(self):
        started = time.monotonic()
        snapshot = self._run_race()
        return {
            "official_actions": True,
            "ok": snapshot is not None,
            "winner": self._v59_cached_winner,
            "changed": snapshot is not None,
            "map_id": 0,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    def load(self):
        if self._v59_cached_snapshot is not None:
            return self._v59_cached_snapshot
        snapshot = self._run_race()
        if snapshot is not None:
            return snapshot
        return super().load()

import json
import math
import time
from typing import Any

from xiaomi_e10_map_v57 import XiaomiE10MapV57


class XiaomiE10MapV58(XiaomiE10MapV57):
    """V58: lee el mapa final directamente desde las props 7/27..7/37.

    El perfil oficial del B112 expone record-map-url como propiedad 7/30.
    V58 intenta primero LAN, luego MIoT Cloud; el historial 7/1 queda como
    fallback y deja de ser la ruta primaria/bloqueante.
    """

    RECORD_PROPS = (
        ("start_time", 27),
        ("use_time", 28),
        ("clean_area", 29),
        ("record_map_url", 30),
        ("clean_mode", 31),
        ("clean_way", 32),
        ("current_map", 33),
        ("task_status", 37),
    )
    DIRECT_FRESH_SECONDS = 15 * 60
    HISTORY_FALLBACK_INTERVAL = 25.0

    def __init__(self, *args, **kwargs):
        self.last_v58_diagnostics: dict[str, Any] = {}
        self._v58_record_baseline = None
        self._v58_session_started_at = time.time()
        self._v58_last_history_at = 0.0
        super().__init__(*args, **kwargs)

    # ----------------------------------------------------------- direct props
    @staticmethod
    def _normalize_prop_rows(rows: Any):
        if isinstance(rows, dict):
            for key in ("result", "data", "out"):
                nested = rows.get(key)
                if isinstance(nested, list):
                    rows = nested
                    break
        return rows if isinstance(rows, list) else []

    @classmethod
    def _record_from_rows(cls, rows: Any):
        by_piid = {}
        errors = {}
        for item in cls._normalize_prop_rows(rows):
            if not isinstance(item, dict):
                continue
            try:
                piid = int(item.get("piid"))
            except Exception:
                continue
            code = item.get("code", 0)
            if code not in (0, "0", None):
                errors[piid] = code
                continue
            by_piid[piid] = item.get("value")

        record = {name: by_piid.get(piid) for name, piid in cls.RECORD_PROPS}
        return record, errors

    def _read_record_props_lan(self):
        vacuum = getattr(self, "vacuum", None)
        device = getattr(vacuum, "device", None)
        if device is None:
            raise RuntimeError("vacuum/device LAN no disponible")
        payload = [
            {"did": f"v58-7-{piid}", "siid": 7, "piid": piid}
            for _name, piid in self.RECORD_PROPS
        ]
        rows = device.send("get_properties", payload)
        record, errors = self._record_from_rows(rows)
        return record, {
            "ok": True,
            "source": "LAN",
            "errors": errors,
            "nonempty": sum(v not in (None, "", []) for v in record.values()),
        }

    def _read_record_props_cloud(self):
        cloud = self._cloud()
        payload = {
            "params": [
                {"did": self.did, "siid": 7, "piid": piid}
                for _name, piid in self.RECORD_PROPS
            ],
            "datasource": 2,
        }
        response = cloud.request_country(
            "/miotspec/prop/get",
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        if isinstance(response, (bytes, bytearray, memoryview)):
            response = bytes(response).decode("utf-8-sig")
        if isinstance(response, str):
            text = response.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            response = json.loads(text)
        if not isinstance(response, dict):
            raise RuntimeError(f"Cloud prop/get inesperado: {type(response).__name__}")
        code = response.get("code", 0)
        if code not in (0, "0", None):
            raise RuntimeError(
                f"Cloud prop/get code={code}: "
                + str(response.get("message") or response.get("msg") or "sin detalle")
            )
        record, errors = self._record_from_rows(response.get("result"))
        return record, {
            "ok": True,
            "source": "Cloud",
            "errors": errors,
            "nonempty": sum(v not in (None, "", []) for v in record.values()),
        }

    @staticmethod
    def _numeric_epoch(value):
        try:
            number = float(value)
        except Exception:
            return None
        if not math.isfinite(number) or number <= 0:
            return None
        if number > 100_000_000_000:
            number /= 1000.0
        return number

    @classmethod
    def _record_signature(cls, record):
        if not isinstance(record, dict):
            return None
        ref = str(record.get("record_map_url") or "").strip()
        start = cls._numeric_epoch(record.get("start_time"))
        if not ref:
            return None
        return (round(float(start or 0.0), 3), ref)

    def reset_record_baseline(self):
        """Marca el registro actual como viejo antes de una nueva limpieza."""
        diag = {}
        candidates = []
        for label, reader in (
            ("lan", self._read_record_props_lan),
            ("cloud", self._read_record_props_cloud),
        ):
            try:
                record, info = reader()
                diag[label] = {**info, "record": self._safe_record_diag(record)}
                sig = self._record_signature(record)
                if sig:
                    candidates.append((label, sig, record))
            except Exception as exc:
                diag[label] = {"ok": False, "error": self._safe_http_error(exc)}
        self._v58_record_baseline = candidates[0][1] if candidates else None
        self._v58_session_started_at = time.time()
        self.last_v58_diagnostics["baseline"] = {
            "signature_present": bool(self._v58_record_baseline),
            "sources": diag,
        }
        return self._v58_record_baseline

    @staticmethod
    def _safe_record_diag(record):
        if not isinstance(record, dict):
            return {}
        ref = str(record.get("record_map_url") or "").strip()
        return {
            "start_time": record.get("start_time"),
            "use_time": record.get("use_time"),
            "clean_area": record.get("clean_area"),
            "current_map": record.get("current_map"),
            "task_status": record.get("task_status"),
            "map_ref_present": bool(ref),
            "map_ref_kind": (
                "http" if ref.startswith(("http://", "https://"))
                else ("path/ref" if ref else "empty")
            ),
            "map_ref_len": len(ref),
        }

    def _record_is_current(self, record):
        sig = self._record_signature(record)
        if sig is None:
            return False, "sin record-map-url"
        if self._v58_record_baseline is not None and sig != self._v58_record_baseline:
            return True, "cambió respecto del baseline"

        start = self._numeric_epoch(record.get("start_time"))
        if start is not None:
            age = time.time() - start
            if -120 <= age <= self.DIRECT_FRESH_SECONDS:
                # Si no había baseline (por ejemplo app abierta después de la
                # limpieza), un registro reciente puede aceptarse directamente.
                if self._v58_record_baseline is None:
                    return True, "registro reciente sin baseline"
                # Si coincide con baseline, no lo aceptamos durante la misma
                # sesión aunque sea reciente: puede ser la limpieza anterior.
        return False, "registro igual al baseline/viejo"

    def _load_direct_record_map(self):
        diag = {
            "success": False,
            "winner": None,
            "sources": {},
            "resolve_endpoint": None,
            "download_bytes": 0,
            "download_sha12": None,
            "decoders": [],
        }

        best = None
        for label, reader in (
            ("LAN", self._read_record_props_lan),
            ("Cloud", self._read_record_props_cloud),
        ):
            try:
                record, info = reader()
                current, reason = self._record_is_current(record)
                diag["sources"][label] = {
                    **info,
                    "record": self._safe_record_diag(record),
                    "current": current,
                    "reason": reason,
                }
                if current and best is None:
                    best = (label, record)
            except Exception as exc:
                diag["sources"][label] = {
                    "ok": False,
                    "error": self._safe_http_error(exc),
                }

        if best is None:
            return None, diag

        source, record = best
        ref = str(record.get("record_map_url") or "").strip()
        url, resolver = self._resolve_file_ref(ref)
        raw, status = self._download_url(url)
        snapshot, decoders = self._decode_any_map(raw, "record-prop-7/30", resolver)
        diag.update({
            "winner": source,
            "reference_kind": "http" if self._looks_http(ref) else "fds-ref",
            "resolve_endpoint": resolver,
            "http": status,
            "download_bytes": len(raw),
            "download_sha12": self._sha12(raw),
            "decoders": decoders,
            "success": snapshot is not None,
        })
        return snapshot, diag

    # --------------------------------------------------------- history backup
    def _history_fallback_due(self):
        now = time.monotonic()
        if now - float(self._v58_last_history_at or 0.0) < self.HISTORY_FALLBACK_INTERVAL:
            return False
        self._v58_last_history_at = now
        return True

    # --------------------------------------------------------------- realtime
    def request_fresh_upload(self):
        """No bloquea 27 s esperando eventos que este B112 no publica.

        Ejecuta las tres acciones y hace una comprobación corta del blob.
        La ruta primaria V58 es 7/30 directo, no el evento realtime.
        """
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

        attempts = []
        final_hash = baseline_hash
        winner = None
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
            time.sleep(0.8)
            try:
                raw, endpoint, status = self._download_slot("0")
                current = self._sha12(raw)
                item.update({
                    "hash_after": current,
                    "http": status,
                    "endpoint": endpoint,
                    "bytes": len(raw),
                    "changed": bool(final_hash and current and current != final_hash),
                })
                if item["changed"]:
                    final_hash = current
                    winner = item["action"]
                    break
                final_hash = current or final_hash
            except Exception as exc:
                item["download_error"] = self._safe_http_error(exc)

        diag = {
            "privacy_before": privacy_before,
            "baseline_hash": baseline_hash,
            "hash_after": final_hash,
            "changed": bool(winner),
            "winner": winner,
            "attempts": attempts,
            "strategy": "acciones oficiales + check corto; mapa primario por 7/30",
        }
        self.last_v58_diagnostics["live_refresh"] = diag
        self.last_v57_diagnostics["live_refresh"] = diag

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

    # ------------------------------------------------------------------ load
    def load(self):
        diagnostics = dict(getattr(self, "last_v58_diagnostics", {}) or {})

        # 1) Ruta primaria: propiedades 7/27..7/37 directas.
        try:
            snapshot, direct_diag = self._load_direct_record_map()
            diagnostics["direct_record"] = direct_diag
            if snapshot is not None:
                diagnostics.update({
                    "route": "prop 7/30 directa -> record-map-url -> decoder",
                    "success": True,
                    "source": f"7/30 {direct_diag.get('winner') or ''}".strip(),
                })
                self.last_v58_diagnostics = diagnostics
                self.last_v57_diagnostics.update(diagnostics)
                return snapshot
        except Exception as exc:
            diagnostics["direct_record"] = {
                "success": False,
                "error": self._safe_http_error(exc),
            }

        # 2) Historial 7/1 sólo cada ~25 s para no bloquear el mapa.
        if self._history_fallback_due():
            try:
                snapshot, hist_diag = self._load_record_map()
                diagnostics["history_record"] = hist_diag
                if snapshot is not None:
                    diagnostics.update({
                        "route": "fallback clean-end 7/1 -> record-map-url",
                        "success": True,
                        "source": "7.1 history",
                    })
                    self.last_v58_diagnostics = diagnostics
                    self.last_v57_diagnostics.update(diagnostics)
                    return snapshot
            except Exception as exc:
                diagnostics["history_record"] = {
                    "success": False,
                    "error": self._safe_http_error(exc),
                }

        # 3) Realtime heredado V57/V56, con rechazo del grid falso intacto.
        snapshot = super().load()
        diagnostics["v57_route"] = dict(getattr(self, "last_v57_diagnostics", {}) or {})
        if hasattr(snapshot, "grid_cells"):
            metrics = self._grid_metrics(getattr(snapshot, "grid_cells", []) or [])
            diagnostics["live_grid_metrics"] = metrics
            if not metrics.get("valid"):
                snapshot.grid_cells = []
                snapshot.grid_walls = []
                snapshot.raw_path = []
                snapshot.image = None
                snapshot.parser_error = "V58: grid rechazado por incoherencia espacial"
                diagnostics.update({
                    "route": "sin mapa real todavía; grid falso descartado",
                    "success": False,
                    "source": "none",
                })
        self.last_v58_diagnostics = diagnostics
        return snapshot

import time
from typing import Any

from xiaomi_e10_ijai_map import IjaiMapSnapshot
from xiaomi_e10_map_v60 import XiaomiE10MapV60


class XiaomiE10MapV61(XiaomiE10MapV60):
    """V61: entiende el estado de persistencia del mapa antes de buscar FDS.

    El hallazgo clave del B112 es que 10/1 es remember-state. Si vale 0, el
    robot puede recorrer/limpiar sin conservar un mapa administrable, por lo
    que map-num y cur-map-id siguen en cero. V61 no inventa IDs ni fuerza
    uploads en ese estado.
    """

    STATE_PROPS = (
        ("remember_state", 10, 1),
        ("cur_map_id", 10, 2),
        ("map_num", 10, 3),
        ("build_map", 10, 14),
        ("has_new_map", 10, 19),
        ("map_uploads", 10, 23),
    )
    STATE_CACHE_SECONDS = 2.0

    def __init__(self, vacuum, settings):
        self.last_v61_diagnostics: dict[str, Any] = {}
        self._v61_last_state_monotonic = 0.0
        self._v61_state: dict[str, Any] = {}
        super().__init__(vacuum, settings)

    @staticmethod
    def _result_rows(raw):
        """Normaliza respuestas MIoT a una lista de diccionarios."""
        if raw is None:
            return []
        if isinstance(raw, (bytes, bytearray, memoryview)):
            try:
                raw = bytes(raw).decode("utf-8-sig")
            except Exception:
                return []
        if isinstance(raw, str):
            try:
                raw = __import__("json").loads(raw.lstrip("\ufeff"))
            except Exception:
                return []
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if not isinstance(raw, dict):
            return []
        if "siid" in raw and "piid" in raw:
            return [raw]
        for key in ("result", "data", "out"):
            rows = XiaomiE10MapV61._result_rows(raw.get(key))
            if rows:
                return rows
        return []

    @staticmethod
    def _as_int(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(float(value))
        except Exception:
            return None

    @classmethod
    def _classify_state(cls, values: dict[str, Any]) -> dict[str, Any]:
        remember = cls._as_int(values.get("remember_state"))
        cur_map_id = cls._as_int(values.get("cur_map_id"))
        map_num = cls._as_int(values.get("map_num"))
        build_map = cls._as_int(values.get("build_map"))
        has_new_map = cls._as_int(values.get("has_new_map"))
        map_uploads = cls._as_int(values.get("map_uploads"))

        saved = bool((cur_map_id or 0) > 0 or (map_num or 0) > 0)
        pending = bool((has_new_map or 0) == 1)
        building = bool((build_map or 0) in (1, 2))

        if saved:
            status = "saved_map_available"
        elif pending:
            status = "new_map_waiting_to_save"
        elif building:
            status = "firmware_building_map"
        elif remember == 0 and cur_map_id == 0 and map_num == 0 and has_new_map == 0:
            status = "no_saved_map_remember_off"
        elif remember == 1 and cur_map_id == 0 and map_num == 0 and has_new_map == 0:
            status = "recording_waiting_for_first_map"
        else:
            status = "unknown"

        return {
            "status": status,
            "remember_state": remember,
            "remember_enabled": remember == 1,
            "cur_map_id": cur_map_id,
            "map_num": map_num,
            "build_map": build_map,
            "has_new_map": has_new_map,
            "map_uploads": map_uploads,
            "uploads_enabled": True if map_uploads == 0 else False if map_uploads == 1 else None,
            "saved_map": saved,
            "pending_map": pending,
            "building": building,
            # Sin ID/mapa guardado, los upload-by-mapid/maptype no tienen una
            # referencia fiable. Seguimos buscando clean-end, que sí puede
            # aparecer al finalizar el recorrido.
            "allow_realtime_upload": bool(saved or pending),
        }

    def _read_state_lan(self) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = [
            {"did": name, "siid": siid, "piid": piid}
            for name, siid, piid in self.STATE_PROPS
        ]
        started = time.monotonic()
        raw = None
        error = None
        try:
            with self._v60_lan_lock:
                raw = self.vacuum.device.send("get_properties", payload)
        except Exception as exc:
            error = self._sanitize_error(exc)

        rows = self._result_rows(raw)
        values: dict[str, Any] = {}
        by_pair = {(siid, piid): name for name, siid, piid in self.STATE_PROPS}
        ok_count = 0
        for row in rows:
            try:
                pair = (int(row.get("siid")), int(row.get("piid")))
            except Exception:
                continue
            name = by_pair.get(pair)
            if not name:
                continue
            code = self._as_int(row.get("code"))
            if code in (None, 0):
                values[name] = row.get("value")
                ok_count += 1

        return values, {
            "source": "lan",
            "ok": bool(ok_count),
            "count": ok_count,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": error,
        }

    def _read_state_cloud(self) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        error = None
        decoded = None
        try:
            payload = {
                "params": [
                    {"did": self.did, "siid": siid, "piid": piid}
                    for _name, siid, piid in self.STATE_PROPS
                ],
                "datasource": 1,
            }
            response = self._cloud().request_country(
                "/miotspec/prop/get",
                self.region,
                {"data": __import__("json").dumps(payload, separators=(",", ":"))},
            )
            decoded = self._extract_result_any(response)
        except Exception as exc:
            error = self._sanitize_error(exc)

        rows = []
        if isinstance(decoded, dict):
            rows = decoded.get("result") or decoded.get("data") or []
        elif isinstance(decoded, list):
            rows = decoded

        values: dict[str, Any] = {}
        by_pair = {(siid, piid): name for name, siid, piid in self.STATE_PROPS}
        ok_count = 0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            try:
                pair = (int(row.get("siid")), int(row.get("piid")))
            except Exception:
                continue
            name = by_pair.get(pair)
            if not name:
                continue
            code = self._as_int(row.get("code"))
            if code in (None, 0):
                values[name] = row.get("value")
                ok_count += 1

        return values, {
            "source": "cloud",
            "ok": bool(ok_count),
            "count": ok_count,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": error,
        }

    def _probe_state(self, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force
            and self._v61_state
            and now - float(self._v61_last_state_monotonic or 0.0)
            < self.STATE_CACHE_SECONDS
        ):
            return dict(self._v61_state)

        started = time.time()
        values, transport = self._read_state_lan()
        transports = [transport]
        if not values:
            values, cloud_transport = self._read_state_cloud()
            transports.append(cloud_transport)

        state = self._classify_state(values)
        diag = {
            "started_at": started,
            "finished_at": time.time(),
            "state": state,
            "state_values_present": sorted(values.keys()),
            "transports": transports,
            "remember_state_fixed_semantics": True,
            "map_uploads_fixed_semantics": True,
            "skip_realtime_upload": not bool(state.get("allow_realtime_upload")),
            "skip_reason": (
                "sin mapa guardado/pendiente; se espera el primer mapa o clean-end"
                if not state.get("allow_realtime_upload")
                else ""
            ),
        }
        self._v61_state = dict(state)
        self._v61_last_state_monotonic = now
        self.last_v61_diagnostics = diag
        return dict(state)

    def _run_v60_cycle(self):
        state = self._probe_state(force=False)
        if not state.get("allow_realtime_upload"):
            self._v60_last_cycle_monotonic = time.monotonic()
            self.last_v60_diagnostics = {}
            return None

        snapshot = super()._run_v60_cycle()
        diag = dict(self.last_v61_diagnostics or {})
        diag["v60_winner"] = (self.last_v60_diagnostics or {}).get("winner")
        diag["v60_candidate_refs"] = int(
            (self.last_v60_diagnostics or {}).get("candidate_refs", 0) or 0
        )
        self.last_v61_diagnostics = diag
        return snapshot

    def request_fresh_upload(self) -> dict[str, Any]:
        state = self._probe_state(force=True)
        if not state.get("allow_realtime_upload"):
            info = {
                "official_actions": False,
                "ok": True,
                "changed": False,
                "winner": None,
                "map_id": int(state.get("cur_map_id") or 0),
                "skipped": True,
                "reason": (self.last_v61_diagnostics or {}).get("skip_reason"),
                "state": state.get("status"),
            }
            self.last_upload_diagnostics = dict(info)
            return info
        return super().request_fresh_upload()

    def load(self):
        state = self._probe_state(force=False)

        if not state.get("allow_realtime_upload"):
            # Aunque todavía no haya mapa persistente, al finalizar una limpieza
            # Xiaomi puede publicar record-map-url mediante clean-end. Consultamos
            # sólo esa ruta final; evitamos slot 0 + uploads repetitivos sin ID.
            try:
                snapshot, record_diag = self._load_record_map()
                diag = dict(self.last_v61_diagnostics or {})
                diag["record_map"] = record_diag
                if snapshot is not None:
                    diag["winner"] = "clean-end record-map-url"
                    self.last_v61_diagnostics = diag
                    return snapshot
                self.last_v61_diagnostics = diag
            except Exception as exc:
                diag = dict(self.last_v61_diagnostics or {})
                diag["record_map_error"] = self._sanitize_error(exc)
                self.last_v61_diagnostics = diag

            return IjaiMapSnapshot(
                parser_error=(
                    "V61: esperando primer mapa persistente "
                    f"({state.get('status')})"
                )
            )

        return super().load()

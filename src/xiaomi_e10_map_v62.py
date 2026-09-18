import json
from typing import Any

from xiaomi_e10_map_v61 import XiaomiE10MapV61


class XiaomiE10MapV62(XiaomiE10MapV61):
    """V62: corrige el parser de respuestas de estado y expone persistencia."""

    @staticmethod
    def _result_rows(raw) -> list[dict[str, Any]]:
        """Normaliza respuestas MIoT LAN/Cloud a una lista de filas.

        V61 llamó a este helper sin implementarlo. Aceptamos las formas que ya
        aparecen en el proyecto: lista directa y wrappers result/data/out.
        """
        if raw is None:
            return []
        if isinstance(raw, (bytes, bytearray, memoryview)):
            try:
                raw = bytes(raw).decode("utf-8-sig")
            except Exception:
                return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw.lstrip("\ufeff"))
            except Exception:
                return []
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if not isinstance(raw, dict):
            return []

        if "siid" in raw and "piid" in raw:
            return [raw]

        for key in ("result", "data", "out"):
            value = raw.get(key)
            rows = XiaomiE10MapV62._result_rows(value)
            if rows:
                return rows
        return []

    def _probe_state(self, force: bool = False) -> dict[str, Any]:
        state = super()._probe_state(force=force)
        diag = dict(getattr(self, "last_v61_diagnostics", {}) or {})
        persistence = dict(
            getattr(getattr(self, "vacuum", None), "last_map_persistence_diag", {}) or {}
        )
        diag["persistence_write"] = persistence
        diag["v62_result_rows_fixed"] = True
        diag["consistency"] = {
            "mapping_persistence_verified": bool(persistence.get("success")),
            "readback_matches": (
                persistence.get("after") == persistence.get("desired")
                if persistence else None
            ),
        }
        self.last_v61_diagnostics = diag
        self.last_v62_diagnostics = dict(diag)
        return state

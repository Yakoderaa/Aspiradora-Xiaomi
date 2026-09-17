import time
from typing import Any

from xiaomi_e10_live import XiaomiE10Live


class XiaomiE10Probe(XiaomiE10Live):
    """Telemetría de diagnóstico para descubrir qué propiedades cambian en el E10.

    El B112 del usuario devuelve 10/5='hello', 10/12=None y mantiene 10/24
    estático durante EDGE. Para no seguir suponiendo, sondeamos periódicamente
    las propiedades documentadas como legibles del servicio 10 y registramos
    cuáles cambian realmente mientras el robot se mueve.
    """

    MAP_READABLE_PIIDS = (1, 2, 3, 5, 14, 19, 22, 23, 24)
    MAP_PROPERTY_NAMES = {
        1: "remember-state",
        2: "cur-map-id",
        3: "map-num",
        5: "cur-cleaning-path",
        14: "build-map",
        19: "has-new-map",
        22: "chargingbase",
        23: "map-privacy",
        24: "robot-location",
    }
    PROBE_INTERVAL = 0.9

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._map_probe_last_at = 0.0
        self._map_probe_values = {}
        self._map_probe_changes = {}
        self._map_probe_errors = {}

    def _probe_service10_once(self):
        payload = [
            {"did": f"p{piid}", "siid": 10, "piid": int(piid)}
            for piid in self.MAP_READABLE_PIIDS
        ]
        current = {}
        errors = {}
        try:
            result = self.device.send("get_properties", payload)
        except Exception as exc:
            return {}, {"request": str(exc)}

        for item in result or []:
            if not isinstance(item, dict):
                continue
            did = str(item.get("did") or "")
            if not did.startswith("p"):
                continue
            try:
                piid = int(did[1:])
            except Exception:
                continue
            code = int(item.get("code", 0) or 0)
            if code == 0:
                current[piid] = item.get("value")
            else:
                errors[piid] = code
        return current, errors

    def _refresh_map_probe(self):
        now = time.monotonic()
        if now - float(getattr(self, "_map_probe_last_at", 0.0) or 0.0) < self.PROBE_INTERVAL:
            return
        self._map_probe_last_at = now

        previous = dict(getattr(self, "_map_probe_values", {}) or {})
        current, errors = self._probe_service10_once()
        if current:
            changes = dict(getattr(self, "_map_probe_changes", {}) or {})
            for piid, value in current.items():
                if piid in previous and repr(previous.get(piid)) != repr(value):
                    changes[piid] = int(changes.get(piid, 0) or 0) + 1
            self._map_probe_values = current
            self._map_probe_changes = changes
        self._map_probe_errors = errors

    def service10_probe_snapshot(self) -> dict[str, Any]:
        self._refresh_map_probe()
        values = dict(getattr(self, "_map_probe_values", {}) or {})
        changes = dict(getattr(self, "_map_probe_changes", {}) or {})
        errors = dict(getattr(self, "_map_probe_errors", {}) or {})
        return {
            "values": values,
            "changes": changes,
            "errors": errors,
            "names": dict(self.MAP_PROPERTY_NAMES),
        }

    def local_map_state(self) -> dict[str, Any]:
        state = super().local_map_state()
        self._refresh_map_probe()
        state["service10_probe"] = {
            "values": dict(getattr(self, "_map_probe_values", {}) or {}),
            "changes": dict(getattr(self, "_map_probe_changes", {}) or {}),
            "errors": dict(getattr(self, "_map_probe_errors", {}) or {}),
            "names": dict(self.MAP_PROPERTY_NAMES),
        }
        return state

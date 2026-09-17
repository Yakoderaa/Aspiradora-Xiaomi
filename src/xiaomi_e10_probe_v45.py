import math
from typing import Any

from xiaomi_e10_probe import XiaomiE10Probe


class XiaomiE10ProbeV45(XiaomiE10Probe):
    """v45: usa los límites documentados 10/15 y 10/16 para 10/12.

    También trata 10/22=255_255 (y sentinelas equivalentes) como "base no
    disponible". La base queda anclada a la primera lectura válida de la sesión,
    por lo que un cambio del campo chargingbase nunca se interpreta como
    desplazamiento del robot.
    """

    MAP_READABLE_PIIDS = (1, 2, 3, 5, 14, 15, 16, 19, 22, 23, 24)
    MAP_PROPERTY_NAMES = {
        **XiaomiE10Probe.MAP_PROPERTY_NAMES,
        15: "start-cleaning-point",
        16: "end-cleaning-point",
    }

    BASE_SENTINELS = {-1, 255, 65535, 4294967295}

    def __init__(self, *args, **kwargs):
        self._v45_bound_start_raw = None
        self._v45_bound_end_raw = None
        self._v45_bound_range = None
        self._v45_bound_source = "probe heredado"
        self._v45_bound_action_code = None
        self._v45_bound_action_raw = None
        self._v45_bound_action_points = 0
        self._v45_base_anchor = None
        self._v45_base_sentinels_ignored = 0
        self._v45_base_changes_ignored = 0
        super().__init__(*args, **kwargs)

    def reset_live_path_session(self):
        super().reset_live_path_session()
        self._v45_bound_start_raw = None
        self._v45_bound_end_raw = None
        self._v45_bound_range = None
        self._v45_bound_source = "probe heredado"
        self._v45_bound_action_code = None
        self._v45_bound_action_raw = None
        self._v45_bound_action_points = 0
        self._v45_base_anchor = None
        self._v45_base_sentinels_ignored = 0
        self._v45_base_changes_ignored = 0

    @staticmethod
    def _coerce_pose_bound(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = int(float(value))
        except Exception:
            return None
        if 0 <= number <= 4294967295:
            return number
        return None

    def _read_documented_path_bounds(self):
        try:
            values = self._get_many([
                ("start", 10, 15),
                ("end", 10, 16),
            ])
        except Exception:
            values = {}
        start_raw = values.get("start")
        end_raw = values.get("end")
        self._v45_bound_start_raw = start_raw
        self._v45_bound_end_raw = end_raw
        start = self._coerce_pose_bound(start_raw)
        end = self._coerce_pose_bound(end_raw)
        if start is None or end is None:
            return None
        # [0,0] no aporta historia. El firmware puede usar start==end para una
        # pose puntual, por lo que sólo descartamos el cero doble.
        if start == 0 and end == 0:
            return None
        if end < start:
            start, end = end, start
        return int(start), int(end)

    def _get_path_by_action(self, direct_path, header_pose_id=None):
        documented = self._read_documented_path_bounds()
        if documented is None:
            self._v45_bound_source = "probe heredado (10/15-10/16 no útiles)"
            return super()._get_path_by_action(direct_path, header_pose_id)

        start, end = documented
        self._v45_bound_range = (start, end)
        self._v45_bound_source = "10/15 → 10/16 documentado"
        self._last_action_probe_range = (start, end)
        try:
            response = self.device.call_action_by(10, 12, [int(start), int(end)])
            code = None
            if isinstance(response, dict) and response.get("code") is not None:
                try:
                    code = int(response.get("code"))
                except Exception:
                    code = response.get("code")
            self._v45_bound_action_code = code
            if isinstance(code, int) and code != 0:
                raise RuntimeError(f"10/12 rechazó el rango documentado con code={code}")
            raw = self._extract_action_output(response, 5)
            self._v45_bound_action_raw = raw
            self._last_action_raw = raw
            path = self.parse_trajectory(raw)
            self._v45_bound_action_points = len(path)
            return raw, path, None, (start, end)
        except Exception as exc:
            self._last_action_raw = None
            self._v45_bound_action_points = 0
            return None, [], str(exc), (start, end)

    @classmethod
    def _is_base_sentinel(cls, position: Any) -> bool:
        if not isinstance(position, dict):
            return False
        try:
            x = float(position["x"])
            y = float(position["y"])
        except Exception:
            return False
        if not (math.isfinite(x) and math.isfinite(y)):
            return True
        xi = int(round(x))
        yi = int(round(y))
        return abs(x - xi) < 1e-9 and abs(y - yi) < 1e-9 and xi == yi and xi in cls.BASE_SENTINELS

    @staticmethod
    def _same_xy(a, b):
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        try:
            return abs(float(a["x"]) - float(b["x"])) < 1e-9 and abs(float(a["y"]) - float(b["y"])) < 1e-9
        except Exception:
            return False

    def _sanitize_base(self, state):
        current = state.get("charging_base")
        if self._is_base_sentinel(current):
            self._v45_base_sentinels_ignored += 1
            state["base_sentinel_ignored"] = True
            state["charging_base"] = dict(self._v45_base_anchor) if self._v45_base_anchor else None
            return

        if isinstance(current, dict):
            if self._v45_base_anchor is None:
                self._v45_base_anchor = dict(current)
            elif not self._same_xy(current, self._v45_base_anchor):
                # La base física no se desplaza durante una sesión de mapeo. Un
                # cambio de 10/22 no puede convertirse en movimiento del robot.
                self._v45_base_changes_ignored += 1
                state["base_change_ignored"] = True
            state["charging_base"] = dict(self._v45_base_anchor)

    def local_map_state(self) -> dict[str, Any]:
        state = super().local_map_state()
        self._sanitize_base(state)
        state.update({
            "path_bound_start_raw": self._v45_bound_start_raw,
            "path_bound_end_raw": self._v45_bound_end_raw,
            "path_bound_range": self._v45_bound_range,
            "path_bound_source": self._v45_bound_source,
            "path_bound_action_code": self._v45_bound_action_code,
            "path_bound_action_raw": self._v45_bound_action_raw,
            "path_bound_action_points": self._v45_bound_action_points,
            "base_anchor": dict(self._v45_base_anchor) if self._v45_base_anchor else None,
            "base_sentinels_ignored": self._v45_base_sentinels_ignored,
            "base_changes_ignored": self._v45_base_changes_ignored,
        })
        return state

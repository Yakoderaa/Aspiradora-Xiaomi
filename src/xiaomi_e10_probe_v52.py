from typing import Any

from xiaomi_e10_probe_v45 import XiaomiE10ProbeV45


class XiaomiE10ProbeV52(XiaomiE10ProbeV45):
    """V52: prueba una vez el rango uint32 completo documentado de get-cur-path.

    El spec MIoT del B112 define 10/12 (get-cur-path) con dos entradas uint32:
    start-cleaning-point 0..4294967295 y end-cleaning-point 1..4294967295.
    Cuando 10/15 y 10/16 no son legibles, las versiones anteriores caían a una
    lista histórica de rangos pequeños y nunca llegaban al máximo documentado.

    V52 realiza una única consulta [0, 0xFFFFFFFF] por sesión. Sólo acepta el
    resultado como trayectoria si contiene al menos dos coordenadas X/Y distintas.
    Si está vacío, falla o es una muestra aislada, conserva íntegro el fallback
    V45/V31 existente. No modifica propiedades, privacidad ni acciones de upload.
    """

    FULL_RANGE = (0, 4294967295)
    MIN_DISTINCT_XY = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def reset_live_path_session(self):
        super().reset_live_path_session()
        self._v52_full_done = False
        self._v52_full_attempts = 0
        self._v52_full_code = None
        self._v52_full_output_kind = None
        self._v52_full_output_length = 0
        self._v52_full_points = 0
        self._v52_full_distinct_xy = 0
        self._v52_full_accepted = False
        self._v52_full_error = None
        self._v52_fallback_used = False
        self._v52_fallback_range = None

    @staticmethod
    def _safe_output_shape(value: Any):
        if value is None:
            return "NoneType", 0
        if isinstance(value, str):
            return "str", len(value)
        if isinstance(value, (bytes, bytearray, memoryview)):
            return type(value).__name__, len(value)
        if isinstance(value, (list, tuple, dict)):
            return type(value).__name__, len(value)
        return type(value).__name__, 1

    @staticmethod
    def _action_code(response: Any):
        if not isinstance(response, dict) or response.get("code") is None:
            return None
        try:
            return int(response.get("code"))
        except Exception:
            return response.get("code")

    @staticmethod
    def _distinct_xy(path):
        seen = set()
        for point in path or []:
            try:
                seen.add((round(float(point["x"]), 6), round(float(point["y"]), 6)))
            except Exception:
                continue
        return len(seen)

    def _probe_full_documented_range(self):
        start, end = self.FULL_RANGE
        self._v52_full_done = True
        self._v52_full_attempts += 1
        self._last_action_probe_range = (start, end)

        try:
            response = self.device.call_action_by(10, 12, [int(start), int(end)])
            code = self._action_code(response)
            self._v52_full_code = code
            if isinstance(code, int) and code != 0:
                raise RuntimeError(f"10/12 rango uint32 completo rechazado con code={code}")

            raw = self._extract_action_output(response, 5)
            kind, length = self._safe_output_shape(raw)
            self._v52_full_output_kind = kind
            self._v52_full_output_length = int(length)

            path = self.parse_trajectory(raw)
            distinct = self._distinct_xy(path)
            self._v52_full_points = len(path)
            self._v52_full_distinct_xy = int(distinct)
            self._v52_full_accepted = bool(len(path) >= 2 and distinct >= self.MIN_DISTINCT_XY)

            if self._v52_full_accepted:
                self._last_action_raw = raw
                # Mantiene coherente el diagnóstico heredado V45.
                self._v45_bound_range = (start, end)
                self._v45_bound_source = "V52 · 10/12 rango uint32 oficial"
                self._v45_bound_action_code = code
                self._v45_bound_action_raw = raw
                self._v45_bound_action_points = len(path)
                return raw, path, None, (start, end)

            if raw is None:
                self._v52_full_error = "10/12 no devolvió salida para el rango uint32 completo"
            elif not path:
                self._v52_full_error = "10/12 devolvió salida pero no una trayectoria interpretable"
            else:
                self._v52_full_error = "10/12 sólo devolvió una muestra/posición sin movimiento distinto"
        except Exception as exc:
            self._v52_full_error = str(exc).strip() or type(exc).__name__
            self._v52_full_accepted = False

        return None

    def _get_path_by_action(self, direct_path, header_pose_id=None):
        if not bool(getattr(self, "_v52_full_done", False)):
            full_result = self._probe_full_documented_range()
            if full_result is not None:
                return full_result

        self._v52_fallback_used = True
        result = super()._get_path_by_action(direct_path, header_pose_id)
        try:
            self._v52_fallback_range = tuple(result[3]) if result[3] is not None else None
        except Exception:
            self._v52_fallback_range = None
        return result

    def local_map_state(self) -> dict[str, Any]:
        state = super().local_map_state()
        state["v52_full_range_probe"] = {
            "attempted": bool(getattr(self, "_v52_full_done", False)),
            "attempts": int(getattr(self, "_v52_full_attempts", 0) or 0),
            "range": tuple(self.FULL_RANGE),
            "code": getattr(self, "_v52_full_code", None),
            "output_kind": getattr(self, "_v52_full_output_kind", None),
            "output_length": int(getattr(self, "_v52_full_output_length", 0) or 0),
            "points": int(getattr(self, "_v52_full_points", 0) or 0),
            "distinct_xy": int(getattr(self, "_v52_full_distinct_xy", 0) or 0),
            "accepted": bool(getattr(self, "_v52_full_accepted", False)),
            "error": getattr(self, "_v52_full_error", None),
            "fallback_used": bool(getattr(self, "_v52_fallback_used", False)),
            "fallback_range": getattr(self, "_v52_fallback_range", None),
        }
        return state

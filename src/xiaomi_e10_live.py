"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria MIoT real del B112.

    Heredamos de XiaomiE10Edge para conservar el arranque de perímetro que ya
    evita rearmados/pitidos, y encima agregamos únicamente la telemetría del mapa.

    El perfil del E10 expone:
      10/5  current-path
      10/15 start-cleaning-point
      10/16 end-cleaning-point
      10/12 get-current-path(start, end) -> 10/5

    No usamos 10/22 ni 10/24 como base/robot porque no forman parte del mapa
    declarado para xiaomi.vacuum.b112. La posición visual se deriva del camino:
    primer punto = origen del recorrido, último punto = posición actual.
    """

    @classmethod
    def _extract_action_output(cls, value: Any, target_piid: int = 5):
        if value is None:
            return None
        if isinstance(value, dict):
            out = value.get("out")
            if isinstance(out, list):
                for item in out:
                    if isinstance(item, dict):
                        try:
                            piid = int(item.get("piid", target_piid) or target_piid)
                        except Exception:
                            piid = target_piid
                        if piid == target_piid and "value" in item:
                            return item.get("value")
                for item in out:
                    found = cls._extract_action_output(item, target_piid)
                    if found is not None:
                        return found
            if "value" in value:
                try:
                    piid = int(value.get("piid", target_piid) or target_piid)
                except Exception:
                    piid = target_piid
                if piid == target_piid:
                    return value.get("value")
            for key in ("result", "data", "payload"):
                if key in value:
                    found = cls._extract_action_output(value[key], target_piid)
                    if found is not None:
                        return found
        if isinstance(value, (list, tuple)):
            for item in value:
                found = cls._extract_action_output(item, target_piid)
                if found is not None:
                    return found
        if isinstance(value, (str, bytes)):
            return value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value
        return None

    def local_map_state(self) -> dict[str, Any]:
        values = self._get_many([
            ("path", 10, 5),
            ("path_start", 10, 15),
            ("path_end", 10, 16),
        ])

        direct_raw = values.get("path")
        direct_path = self.parse_trajectory(direct_raw)
        action_raw = None
        action_path = []
        action_error = None

        start = values.get("path_start")
        end = values.get("path_end")
        if start is not None and end is not None:
            try:
                response = self.device.call_action_by(10, 12, [start, end])
                action_raw = self._extract_action_output(response, 5)
                action_path = self.parse_trajectory(action_raw)
            except Exception as exc:
                action_error = str(exc)

        if action_path:
            path = action_path
            source = "get-current-path"
        else:
            path = direct_path
            source = "current-path"

        robot = None
        base = None
        if path:
            first = path[0]
            last = path[-1]
            base = {
                "x": float(first["x"]),
                "y": float(first["y"]),
                "angle": float(first.get("phi", 0) or 0),
            }
            robot = {
                "x": float(last["x"]),
                "y": float(last["y"]),
                "angle": float(last.get("phi", 0) or 0),
            }

        return {
            "path": path,
            "charging_base": base,
            "robot": robot,
            "raw_path": action_raw if action_raw is not None else direct_raw,
            "path_source": source,
            "path_start": start,
            "path_end": end,
            "direct_path_count": len(direct_path),
            "action_path_count": len(action_path),
            "path_action_error": action_error,
        }

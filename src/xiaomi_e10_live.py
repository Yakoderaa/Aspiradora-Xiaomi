"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria/posición MIoT del B112.

    El firmware no siempre devuelve el path dentro de la respuesta de
    get-current-path. Por eso usamos varias fuentes, en este orden:
      1) propiedad 10/5 current-path;
      2) acción 10/12 y relectura inmediata de 10/5;
      3) salida embebida de la acción, si existe;
      4) posición 10/24 como fallback oportunista.

    10/22 y 10/24 no aparecen en todos los perfiles públicos del B112, pero
    algunas revisiones de firmware sí responden. Se consultan de forma opcional
    y nunca hacen fallar el sondeo si el robot las rechaza.
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

    def _optional_value(self, siid: int, piid: int):
        """Lee una propiedad no garantizada sin convertirla en error de mapa."""
        try:
            return self._value(siid, piid)
        except Exception:
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
        reread_raw = None
        reread_path = []
        action_error = None

        start = values.get("path_start")
        end = values.get("path_end")
        if start is not None and end is not None:
            try:
                response = self.device.call_action_by(10, 12, [start, end])
                action_raw = self._extract_action_output(response, 5)
                action_path = self.parse_trajectory(action_raw)

                # Muchos firmwares escriben el resultado en current-path pero
                # la respuesta de la acción no contiene el payload. Releer 10/5
                # inmediatamente es esencial para poder dibujar en vivo.
                reread_raw = self._optional_value(10, 5)
                reread_path = self.parse_trajectory(reread_raw)
            except Exception as exc:
                action_error = str(exc)

        # Preferimos la fuente con más puntos válidos. Si todas tienen el mismo
        # tamaño, priorizamos la relectura post-acción por ser la más reciente.
        candidates = [
            ("current-path post-acción", reread_path, reread_raw),
            ("get-current-path", action_path, action_raw),
            ("current-path", direct_path, direct_raw),
        ]
        source, path, selected_raw = max(candidates, key=lambda item: len(item[1]))
        if not path:
            source = "esperando telemetría"

        # Fallback oportunista: algunas unidades B112 entregan posición/base en
        # 10/24 y 10/22 aun cuando current-path está vacío durante EDGE.
        raw_robot = self._optional_value(10, 24)
        raw_base = self._optional_value(10, 22)
        robot = self.parse_position(raw_robot)
        base = self.parse_position(raw_base)
        position_source = None

        if path:
            first = path[0]
            last = path[-1]
            if base is None:
                base = {
                    "x": float(first["x"]),
                    "y": float(first["y"]),
                    "angle": float(first.get("phi", 0) or 0),
                }
            if robot is None:
                robot = {
                    "x": float(last["x"]),
                    "y": float(last["y"]),
                    "angle": float(last.get("phi", 0) or 0),
                }
            position_source = "trayectoria"
        elif robot is not None:
            source = "posición instantánea 10/24"
            position_source = "10/24"

        return {
            "path": path,
            "charging_base": base,
            "robot": robot,
            "raw_path": selected_raw,
            "path_source": source,
            "position_source": position_source,
            "path_start": start,
            "path_end": end,
            "direct_path_count": len(direct_path),
            "action_path_count": len(action_path),
            "reread_path_count": len(reread_path),
            "instant_robot": robot if not path else None,
            "path_action_error": action_error,
        }

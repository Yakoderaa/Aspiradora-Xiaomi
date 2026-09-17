"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria/posición MIoT del B112.

    El firmware puede entregar el recorrido por 10/5 o sólo la posición 10/24.
    Todas las propiedades dinámicas se leen juntas mediante get_properties para
    evitar valores cacheados en get_property_by durante una limpieza activa.
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

    def _fresh_optional_values(self):
        """Lee base/robot sin caché. Si el firmware las rechaza, devuelve None."""
        try:
            values = self._get_many([
                ("charging_base", 10, 22),
                ("robot", 10, 24),
            ])
            return values.get("charging_base"), values.get("robot")
        except Exception:
            return None, None

    def _fresh_current_path(self):
        try:
            values = self._get_many([("path", 10, 5)])
            return values.get("path")
        except Exception:
            return None

    def local_map_state(self) -> dict[str, Any]:
        values = self._get_many([
            ("path", 10, 5),
            ("path_start", 10, 15),
            ("path_end", 10, 16),
            ("charging_base", 10, 22),
            ("robot", 10, 24),
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
                reread_raw = self._fresh_current_path()
                reread_path = self.parse_trajectory(reread_raw)
            except Exception as exc:
                action_error = str(exc)

        candidates = [
            ("current-path post-acción", reread_path, reread_raw),
            ("get-current-path", action_path, action_raw),
            ("current-path", direct_path, direct_raw),
        ]
        source, path, selected_raw = max(candidates, key=lambda item: len(item[1]))
        if not path:
            source = "esperando telemetría"

        # 10/22 y 10/24 se toman del mismo get_properties fresco que el path.
        # Esto evita la lectura cacheada que dejaba el robot pegado a la base.
        raw_base = values.get("charging_base")
        raw_robot = values.get("robot")
        base = self.parse_position(raw_base)
        robot = self.parse_position(raw_robot)
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
            position_source = "10/24 fresco"

        return {
            "path": path,
            "charging_base": base,
            "robot": robot,
            "raw_path": selected_raw,
            "raw_robot": raw_robot,
            "raw_base": raw_base,
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
"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria/posición MIoT del B112.

    El B112 expone 10/5 (cur-cleaning-path) como propiedad y la acción 10/12
    (get-cur-path) con 10/15 y 10/16 como *parámetros de entrada*. Esos dos
    últimos PIID no son propiedades legibles, por lo que no debemos esperar que
    get_properties nos entregue start/end antes de llamar la acción.

    Durante EDGE algunos firmwares dejan 10/24 (robot-location) congelado aunque
    el robot siga moviéndose. Por eso la fuente preferida es la trayectoria y,
    cuando 10/5 viene vacío, sondeamos 10/12 con ventanas de pose-id crecientes.
    """

    PATH_PROBE_ENDS = (256, 1024, 4096, 16384, 65535, 262143)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._live_path_cursor = None
        self._live_path_probe_index = 0
        self._live_robot_raw_key = None
        self._live_robot_same_reads = 0

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

    @staticmethod
    def _last_pose_id(path):
        if not path:
            return None
        try:
            return max(0, int(path[-1].get("id", 0)))
        except Exception:
            return None

    def _next_path_probe_range(self, direct_path):
        """Genera una ventana válida para get-cur-path sin leer 10/15/10/16."""
        last_direct = self._last_pose_id(direct_path)
        cursor = getattr(self, "_live_path_cursor", None)

        if last_direct is not None:
            start = max(0, last_direct - 8)
            end = min(4294967295, max(start + 1, last_direct + 320))
            return start, end

        if cursor is not None:
            start = max(0, int(cursor) - 8)
            end = min(4294967295, max(start + 1, int(cursor) + 320))
            return start, end

        index = int(getattr(self, "_live_path_probe_index", 0) or 0)
        end = self.PATH_PROBE_ENDS[index % len(self.PATH_PROBE_ENDS)]
        self._live_path_probe_index = index + 1
        return 0, int(end)

    def _get_path_by_action(self, direct_path):
        start, end = self._next_path_probe_range(direct_path)
        try:
            response = self.device.call_action_by(10, 12, [int(start), int(end)])
            raw = self._extract_action_output(response, 5)
            path = self.parse_trajectory(raw)
            last_id = self._last_pose_id(path)
            if last_id is not None:
                self._live_path_cursor = last_id
                self._live_path_probe_index = 0
            return raw, path, None, (start, end)
        except Exception as exc:
            return None, [], str(exc), (start, end)

    def _fresh_current_path(self):
        try:
            values = self._get_many([("path", 10, 5)])
            return values.get("path")
        except Exception:
            return None

    def _fresh_robot_position(self):
        """Lee 10/24 solo, evitando que otro PIID comparta/camise la muestra."""
        try:
            values = self._get_many([("robot", 10, 24)])
            return values.get("robot")
        except Exception:
            return None

    @staticmethod
    def _raw_key(value):
        try:
            return repr(value)
        except Exception:
            return str(type(value))

    def _track_robot_staleness(self, raw_robot):
        key = self._raw_key(raw_robot)
        previous = getattr(self, "_live_robot_raw_key", None)
        if previous is not None and key == previous:
            self._live_robot_same_reads = int(getattr(self, "_live_robot_same_reads", 0) or 0) + 1
        else:
            self._live_robot_same_reads = 0
        self._live_robot_raw_key = key
        return int(self._live_robot_same_reads)

    def local_map_state(self) -> dict[str, Any]:
        # 10/15 y 10/16 NO se leen aquí: son argumentos de 10/12, no telemetría.
        values = self._get_many([
            ("path", 10, 5),
            ("charging_base", 10, 22),
            ("robot", 10, 24),
        ])

        direct_raw = values.get("path")
        direct_path = self.parse_trajectory(direct_raw)

        # La acción 10/12 es de lectura. La llamamos aun cuando 10/5 esté vacío,
        # usando una ventana generada localmente. Esto corrige el caso real en el
        # que directo=0/acción=0 porque antes nunca se invocaba 10/12.
        action_raw, action_path, action_error, probe_range = self._get_path_by_action(direct_path)

        # Algunos firmwares publican el resultado de 10/12 en 10/5 en vez de
        # devolverlo directamente. Releemos una vez después de la acción.
        reread_raw = self._fresh_current_path()
        reread_path = self.parse_trajectory(reread_raw)

        candidates = [
            ("current-path post 10/12", reread_path, reread_raw),
            ("get-cur-path 10/12", action_path, action_raw),
            ("current-path 10/5", direct_path, direct_raw),
        ]
        source, path, selected_raw = max(candidates, key=lambda item: len(item[1]))
        if path:
            last_id = self._last_pose_id(path)
            if last_id is not None:
                self._live_path_cursor = last_id
                self._live_path_probe_index = 0
        else:
            source = "esperando trayectoria"

        raw_base = values.get("charging_base")
        raw_robot = values.get("robot")

        # Si todavía no tenemos path, hacemos una lectura dedicada de 10/24.
        # En firmwares donde esa propiedad sí es dinámica evita compartir una
        # respuesta vieja con las otras propiedades del mapa.
        if not path:
            fresh_robot = self._fresh_robot_position()
            if fresh_robot is not None:
                raw_robot = fresh_robot

        base = self.parse_position(raw_base)
        robot = self.parse_position(raw_robot)
        same_robot_reads = self._track_robot_staleness(raw_robot)
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
            # La trayectoria manda sobre 10/24: si robot-location está congelado,
            # el último pose-id sigue dibujando la posición real en el recorrido.
            robot = {
                "x": float(last["x"]),
                "y": float(last["y"]),
                "angle": float(last.get("phi", 0) or 0),
            }
            position_source = "trayectoria"
        elif robot is not None:
            source = "posición instantánea 10/24"
            position_source = "10/24 dedicado"

        stale = bool(not path and robot is not None and same_robot_reads >= 3)
        note = ""
        if stale:
            note = (
                f"10/24 sin cambios ({same_robot_reads + 1} lecturas); "
                f"sondeando 10/12 rango {probe_range[0]}→{probe_range[1]}"
            )

        return {
            "path": path,
            "charging_base": base,
            "robot": robot,
            "raw_path": selected_raw,
            "raw_robot": raw_robot,
            "raw_base": raw_base,
            "path_source": source,
            "position_source": position_source,
            "path_start": probe_range[0],
            "path_end": probe_range[1],
            "direct_path_count": len(direct_path),
            "action_path_count": len(action_path),
            "reread_path_count": len(reread_path),
            "instant_robot": robot if not path else None,
            "path_action_error": action_error,
            "position_stale": stale,
            "position_same_reads": same_robot_reads,
            "telemetry_note": note,
        }

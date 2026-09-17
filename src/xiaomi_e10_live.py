"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria/posición MIoT del B112.

    La fuente principal durante una limpieza es 10/5 (cur-cleaning-path). El
    firmware puede publicar esa propiedad por fragmentos y, entre dos fragmentos,
    devolver temporalmente una cadena vacía. En esos huecos NO debemos volver a
    10/24 porque varios E10 dejan robot-location congelado sobre la base.

    Por eso esta clase acumula los pose-id recibidos durante la sesión actual y
    mantiene el último punto válido como posición del robot hasta que llegue uno
    nuevo. 10/12 queda como recuperación/fallback para completar fragmentos.
    """

    PATH_PROBE_ENDS = (256, 1024, 4096, 16384, 65535, 262143)
    MAX_CACHED_POSES = 20000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_live_path_session()
        self._live_robot_raw_key = None
        self._live_robot_same_reads = 0

    def reset_live_path_session(self):
        """Empieza una trayectoria lógica nueva sin tocar el mapa guardado."""
        self._live_path_cursor = None
        self._live_path_probe_index = 0
        self._live_path_cache = {}
        self._live_path_last_signature = None
        self._live_path_empty_reads = 0
        self._live_path_source = "esperando trayectoria"

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
            return max(int(point.get("id", 0)) for point in path)
        except Exception:
            return None

    @staticmethod
    def _path_signature(path):
        if not path:
            return None
        try:
            last = path[-1]
            return (
                int(last.get("id", 0)),
                round(float(last.get("x", 0.0)), 6),
                round(float(last.get("y", 0.0)), 6),
                round(float(last.get("phi", 0.0) or 0.0), 6),
                len(path),
            )
        except Exception:
            return None

    def _merge_live_path(self, *paths):
        """Une fragmentos MIoT por pose-id y conserva el recorrido entre polls."""
        cache = getattr(self, "_live_path_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._live_path_cache = cache

        changed = 0
        for path in paths:
            for point in path or []:
                try:
                    pid = int(point.get("id", 0))
                    normalized = {
                        "id": pid,
                        "x": float(point["x"]),
                        "y": float(point["y"]),
                        "phi": float(point.get("phi", 0) or 0),
                        "update": int(point.get("update", 1) or 0),
                    }
                except Exception:
                    continue
                previous = cache.get(pid)
                if previous != normalized:
                    cache[pid] = normalized
                    changed += 1

        if len(cache) > self.MAX_CACHED_POSES:
            ids = sorted(cache)
            for pid in ids[: len(cache) - self.MAX_CACHED_POSES]:
                cache.pop(pid, None)

        ordered = [cache[pid] for pid in sorted(cache)]
        last_id = self._last_pose_id(ordered)
        if last_id is not None:
            self._live_path_cursor = last_id
        return ordered, changed

    def _next_path_probe_range(self, direct_path):
        """Genera una ventana para 10/12 sin leer 10/15/10/16 como propiedades."""
        last_direct = self._last_pose_id(direct_path)
        cursor = getattr(self, "_live_path_cursor", None)

        # Si conocemos el pose-id actual, pedimos una pequeña superposición hacia
        # atrás y algo de margen hacia adelante. La caché elimina duplicados.
        known = last_direct if last_direct is not None else cursor
        if known is not None:
            start = max(0, int(known) - 16)
            end = min(4294967295, max(start + 1, int(known) + 160))
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
            return raw, path, None, (start, end)
        except Exception as exc:
            return None, [], str(exc), (start, end)

    def _fresh_current_path(self):
        """Lee 10/5 de forma dedicada: es la fuente prioritaria en movimiento."""
        try:
            values = self._get_many([("path", 10, 5)])
            return values.get("path")
        except Exception:
            return None

    def _fresh_robot_position(self):
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
        # 10/5 se consulta sola para reducir la posibilidad de recibir una muestra
        # vieja dentro de un get_properties grande.
        direct_raw = self._fresh_current_path()
        direct_path = self.parse_trajectory(direct_raw)
        direct_signature = self._path_signature(direct_path)
        previous_signature = getattr(self, "_live_path_last_signature", None)
        direct_changed = bool(direct_path and direct_signature != previous_signature)

        if direct_path:
            self._live_path_empty_reads = 0
            self._live_path_last_signature = direct_signature
        else:
            self._live_path_empty_reads = int(getattr(self, "_live_path_empty_reads", 0) or 0) + 1

        # Base y 10/24 son secundarios. Se leen juntos, pero nunca pisan una
        # trayectoria ya confirmada en esta sesión.
        try:
            values = self._get_many([
                ("charging_base", 10, 22),
                ("robot", 10, 24),
            ])
        except Exception:
            values = {}

        # 10/12 es fallback. Si 10/5 está avanzando no lo llamamos en cada frame:
        # así reducimos tráfico y evitamos que la acción interfiera con la lectura
        # directa. Lo usamos cuando 10/5 está vacío o dejó de avanzar.
        action_raw = None
        action_path = []
        action_error = None
        probe_range = self._next_path_probe_range(direct_path)
        if not direct_changed or not direct_path:
            action_raw, action_path, action_error, probe_range = self._get_path_by_action(direct_path)

        accumulated, changed_count = self._merge_live_path(direct_path, action_path)

        if direct_changed:
            self._live_path_source = "trayectoria 10/5"
        elif action_path:
            self._live_path_source = "trayectoria 10/12"
        elif accumulated:
            self._live_path_source = "última trayectoria válida"
        else:
            self._live_path_source = "esperando primera coordenada"

        raw_base = values.get("charging_base")
        raw_robot = values.get("robot")
        base = self.parse_position(raw_base)
        robot_1024 = self.parse_position(raw_robot)
        same_robot_reads = self._track_robot_staleness(raw_robot)

        # Regla fundamental de v29: una vez recibimos trayectoria, la posición
        # visual sale SIEMPRE del último pose acumulado. Un frame vacío de 10/5 no
        # puede teletransportar el icono otra vez a la base mediante 10/24.
        if accumulated:
            first = accumulated[0]
            last = accumulated[-1]
            if base is None:
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
            position_source = self._live_path_source
        else:
            # Antes de la primera trayectoria todavía mostramos 10/24, pero queda
            # claramente marcado como fallback para diagnóstico.
            if robot_1024 is None:
                fresh_robot = self._fresh_robot_position()
                raw_robot = fresh_robot if fresh_robot is not None else raw_robot
                robot_1024 = self.parse_position(raw_robot)
                same_robot_reads = self._track_robot_staleness(raw_robot)
            robot = robot_1024
            position_source = "10/24 (esperando trayectoria)" if robot is not None else "sin coordenadas"

        stale_1024 = bool(robot_1024 is not None and same_robot_reads >= 3)
        note = ""
        if not accumulated and stale_1024:
            note = "10/24 permanece sin cambios; esperando 10/5"

        last_pose_id = self._last_pose_id(accumulated)
        return {
            "path": accumulated,
            "charging_base": base,
            "robot": robot,
            "raw_path": direct_raw if direct_raw is not None else action_raw,
            "raw_robot": raw_robot,
            "raw_base": raw_base,
            "path_source": self._live_path_source,
            "position_source": position_source,
            "path_start": accumulated[0]["id"] if accumulated else probe_range[0],
            "path_end": last_pose_id if last_pose_id is not None else probe_range[1],
            "direct_path_count": len(direct_path),
            "action_path_count": len(action_path),
            "accumulated_path_count": len(accumulated),
            "new_path_count": changed_count,
            "last_pose_id": last_pose_id,
            "instant_robot": robot if not accumulated else None,
            "path_action_error": action_error,
            "position_stale": bool(not accumulated and stale_1024),
            "position_same_reads": same_robot_reads,
            "telemetry_note": note,
        }

"""Telemetría de trayectoria en vivo específica para Xiaomi Robot Vacuum E10 (b112)."""

from typing import Any

from xiaomi_e10_edge import XiaomiE10Edge


class XiaomiE10Live(XiaomiE10Edge):
    """EDGE estable + trayectoria/posición MIoT del B112.

    La fuente principal durante una limpieza es 10/5 (cur-cleaning-path). El
    firmware puede publicar esa propiedad por fragmentos y, entre dos fragmentos,
    devolver temporalmente una cadena vacía. En esos huecos NO debemos volver a
    10/24 porque varios E10 dejan robot-location congelado sobre la base.

    Además, 10/5 puede devolver sólo el primer pose-id, sin coordenadas. Ese ID es
    valioso: 10/12 (get-cur-path) espera un rango de pose-id real. Las versiones
    anteriores descartaban ese encabezado y sondeaban rangos cercanos a cero o
    puntos futuros; ahora pedimos historia terminando exactamente en el pose-id
    observado por el robot.
    """

    FALLBACK_PROBE_ENDS = (256, 1024, 4096, 16384, 65535, 262143)
    HISTORY_SPANS = (64, 256, 1024, 4096)
    MAX_CACHED_POSES = 20000
    SYNTHETIC_POSE_BASE = 2_000_000_000

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
        self._live_stream_seq = 0
        self._live_stream_protocol_id = None
        self._live_stream_last = None
        self._live_stream_mode = False
        self._last_action_raw = None
        self._last_action_probe_range = None

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

    @classmethod
    def _header_pose_id(cls, value):
        """Extrae el primer pose-id incluso cuando 10/5 sólo devuelve ``[id]``."""
        try:
            values = cls._numeric_values(value)
            if values:
                candidate = int(values[0])
                if 0 <= candidate <= 4294967295:
                    return candidate
        except Exception:
            pass
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

    @staticmethod
    def _pose_signature(point):
        try:
            return (
                round(float(point.get("x", 0.0)), 6),
                round(float(point.get("y", 0.0)), 6),
                round(float(point.get("phi", 0.0) or 0.0), 6),
            )
        except Exception:
            return None

    def _next_synthetic_pose_id(self):
        self._live_stream_seq = int(getattr(self, "_live_stream_seq", 0) or 0) + 1
        return self.SYNTHETIC_POSE_BASE + self._live_stream_seq

    def _merge_live_path(self, *paths):
        """Une fragmentos MIoT y soporta streams que reutilizan un único pose-id."""
        cache = getattr(self, "_live_path_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._live_path_cache = cache

        changed = 0
        seen_this_merge = set()

        for path in paths:
            incoming = list(path or [])
            single_pose_frame = len(incoming) == 1

            for point in incoming:
                try:
                    protocol_id = int(point.get("id", 0))
                    normalized = {
                        "id": protocol_id,
                        "x": float(point["x"]),
                        "y": float(point["y"]),
                        "phi": float(point.get("phi", 0) or 0),
                        "update": int(point.get("update", 1) or 0),
                    }
                except Exception:
                    continue

                signature = (
                    protocol_id,
                    *self._pose_signature(normalized),
                    normalized["update"],
                )
                if signature in seen_this_merge:
                    continue
                seen_this_merge.add(signature)

                if single_pose_frame:
                    previous_stream = getattr(self, "_live_stream_last", None)
                    previous_protocol_id = getattr(self, "_live_stream_protocol_id", None)

                    if (
                        previous_stream is not None
                        and previous_protocol_id == protocol_id
                        and self._pose_signature(previous_stream) != self._pose_signature(normalized)
                    ):
                        self._live_stream_mode = True
                        synthetic_id = self._next_synthetic_pose_id()
                        sample = dict(normalized)
                        sample["id"] = synthetic_id
                        cache[synthetic_id] = sample
                        self._live_stream_last = dict(normalized)
                        self._live_stream_protocol_id = protocol_id
                        changed += 1
                        continue

                    self._live_stream_last = dict(normalized)
                    self._live_stream_protocol_id = protocol_id

                previous = cache.get(protocol_id)
                if previous != normalized:
                    cache[protocol_id] = normalized
                    changed += 1

        if len(cache) > self.MAX_CACHED_POSES:
            ids = sorted(cache)
            for pid in ids[: len(cache) - self.MAX_CACHED_POSES]:
                cache.pop(pid, None)

        return [cache[pid] for pid in sorted(cache)], changed

    def _next_path_probe_range(self, direct_path, header_pose_id=None):
        """Pide historia *hasta* el último pose-id observado, no puntos futuros."""
        last_direct = self._last_pose_id(direct_path)
        cursor = getattr(self, "_live_path_cursor", None)
        candidates = [value for value in (last_direct, header_pose_id, cursor) if value is not None]
        known = max(candidates) if candidates else None

        index = int(getattr(self, "_live_path_probe_index", 0) or 0)
        self._live_path_probe_index = index + 1

        if known is not None:
            span = self.HISTORY_SPANS[index % len(self.HISTORY_SPANS)]
            end = max(1, min(4294967295, int(known)))
            start = max(0, end - int(span))
            if start >= end:
                start = max(0, end - 1)
            return start, end

        end = self.FALLBACK_PROBE_ENDS[index % len(self.FALLBACK_PROBE_ENDS)]
        return 0, int(end)

    def _get_path_by_action(self, direct_path, header_pose_id=None):
        start, end = self._next_path_probe_range(direct_path, header_pose_id)
        self._last_action_probe_range = (start, end)
        try:
            response = self.device.call_action_by(10, 12, [int(start), int(end)])
            raw = self._extract_action_output(response, 5)
            self._last_action_raw = raw
            path = self.parse_trajectory(raw)
            return raw, path, None, (start, end)
        except Exception as exc:
            self._last_action_raw = None
            return None, [], str(exc), (start, end)

    def _fresh_current_path(self):
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
        direct_raw = self._fresh_current_path()
        direct_header_id = self._header_pose_id(direct_raw)
        direct_path = self.parse_trajectory(direct_raw)
        direct_signature = self._path_signature(direct_path)
        previous_signature = getattr(self, "_live_path_last_signature", None)
        direct_changed = bool(direct_path and direct_signature != previous_signature)

        if direct_path:
            self._live_path_empty_reads = 0
            self._live_path_last_signature = direct_signature
            protocol_last = self._last_pose_id(direct_path)
            if protocol_last is not None:
                self._live_path_cursor = protocol_last
        else:
            self._live_path_empty_reads = int(getattr(self, "_live_path_empty_reads", 0) or 0) + 1
            if direct_header_id is not None:
                # Un frame [pose_id] sigue indicando dónde termina la historia.
                if self._live_path_cursor is None or direct_header_id > self._live_path_cursor:
                    self._live_path_cursor = direct_header_id

        try:
            values = self._get_many([
                ("charging_base", 10, 22),
                ("robot", 10, 24),
            ])
        except Exception:
            values = {}

        action_raw = None
        action_path = []
        action_error = None
        probe_range = self._next_path_probe_range(direct_path, direct_header_id)
        if not direct_changed or len(direct_path) <= 1:
            action_raw, action_path, action_error, probe_range = self._get_path_by_action(
                direct_path,
                direct_header_id,
            )
            action_last = self._last_pose_id(action_path)
            if action_last is not None:
                self._live_path_cursor = max(action_last, self._live_path_cursor or action_last)

        accumulated, changed_count = self._merge_live_path(action_path, direct_path)

        if direct_changed and len(direct_path) > 1:
            self._live_path_source = "trayectoria 10/5"
        elif action_path:
            self._live_path_source = (
                "stream 10/12 · pose-id reutilizado"
                if getattr(self, "_live_stream_mode", False)
                else "historial 10/12"
            )
        elif direct_changed:
            self._live_path_source = (
                "stream 10/5 · pose-id reutilizado"
                if getattr(self, "_live_stream_mode", False)
                else "trayectoria 10/5"
            )
        elif accumulated:
            self._live_path_source = "última trayectoria válida"
        elif direct_header_id is not None:
            self._live_path_source = "pose-id 10/5 · recuperando historial 10/12"
        else:
            self._live_path_source = "esperando primera coordenada"

        raw_base = values.get("charging_base")
        raw_robot = values.get("robot")
        base = self.parse_position(raw_base)
        robot_1024 = self.parse_position(raw_robot)
        same_robot_reads = self._track_robot_staleness(raw_robot)

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
            if direct_header_id is not None:
                note = f"10/24 fijo; recuperando historial desde pose-id {direct_header_id}"
            else:
                note = "10/24 permanece sin cambios; esperando 10/5"

        return {
            "path": accumulated,
            "charging_base": base,
            "robot": robot,
            "raw_path": direct_raw if direct_raw is not None else action_raw,
            "raw_path_direct": direct_raw,
            "raw_path_action": action_raw,
            "raw_robot": raw_robot,
            "raw_base": raw_base,
            "direct_header_id": direct_header_id,
            "path_source": self._live_path_source,
            "position_source": position_source,
            "path_start": accumulated[0]["id"] if accumulated else probe_range[0],
            "path_end": self._live_path_cursor if self._live_path_cursor is not None else probe_range[1],
            "probe_start": probe_range[0],
            "probe_end": probe_range[1],
            "direct_path_count": len(direct_path),
            "action_path_count": len(action_path),
            "accumulated_path_count": len(accumulated),
            "new_path_count": changed_count,
            "last_pose_id": self._live_path_cursor,
            "single_pose_stream": bool(getattr(self, "_live_stream_mode", False)),
            "instant_robot": robot if not accumulated else None,
            "path_action_error": action_error,
            "position_stale": bool(not accumulated and stale_1024),
            "position_same_reads": same_robot_reads,
            "telemetry_note": note,
        }

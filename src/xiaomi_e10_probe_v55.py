import math
from typing import Any

from xiaomi_e10_probe_v52 import XiaomiE10ProbeV52


class XiaomiE10ProbeV55(XiaomiE10ProbeV52):
    """V55: trayectoria viva persistente a partir de cambios temporales reales de 10/24.

    El firmware B112 del usuario no entrega 10/5 ni 10/12 útiles. En cambio 10/24
    sí expone robot-location. Esta clase conserva cada cambio X/Y real de 10/24
    y lo publica como trayectoria normal para que toda la UI existente pueda
    mover el robot y dibujar su recorrido sin depender del blob Cloud.

    Seguridad:
    - La primera muestra aislada nunca confirma movimiento.
    - Sólo un cambio temporal X/Y de 10/24 agrega puntos.
    - Cambios de 10/22 no cuentan como movimiento; V45 sigue anclando la base.
    - 10/12 queda fuera del bucle vivo porque ya fue descartado en V52.
    """

    XY_EPSILON = 1e-9
    MAX_TRACK_POINTS = 12000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def reset_live_path_session(self):
        super().reset_live_path_session()
        self._v55_last_pose = None
        self._v55_track = []
        self._v55_motion_confirmed = False
        self._v55_xy_changes = 0
        self._v55_point_id = 550000
        self._v55_last_added_count = 0
        self._v55_action_reads_skipped = 0

    # ------------------------------------------------------- 10/12 fuera loop
    def _get_path_by_action(self, direct_path, header_pose_id=None):
        self._v55_action_reads_skipped = int(
            getattr(self, "_v55_action_reads_skipped", 0) or 0
        ) + 1
        self._last_action_raw = None
        self._last_action_probe_range = (0, 0)
        return None, [], None, (0, 0)

    # ---------------------------------------------------------- track 10/24
    @staticmethod
    def _pose_tuple(robot: Any):
        if not isinstance(robot, dict):
            return None
        try:
            x = float(robot["x"])
            y = float(robot["y"])
            angle = float(robot.get("angle", 0.0) or 0.0)
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(angle)):
            return None
        return x, y, angle

    @classmethod
    def _xy_changed(cls, a, b):
        if a is None or b is None:
            return False
        return (
            abs(float(a[0]) - float(b[0])) > cls.XY_EPSILON
            or abs(float(a[1]) - float(b[1])) > cls.XY_EPSILON
        )

    def _new_track_point(self, pose):
        self._v55_point_id = int(getattr(self, "_v55_point_id", 550000) or 550000) + 1
        return {
            "id": self._v55_point_id,
            "x": float(pose[0]),
            "y": float(pose[1]),
            "phi": float(pose[2]),
            "update": 1,
        }

    def _ingest_pose(self, robot):
        current = self._pose_tuple(robot)
        if current is None:
            self._v55_last_added_count = 0
            return 0

        previous = getattr(self, "_v55_last_pose", None)
        self._v55_last_pose = current
        if previous is None:
            self._v55_last_added_count = 0
            return 0

        if not self._xy_changed(previous, current):
            self._v55_last_added_count = 0
            return 0

        self._v55_xy_changes = int(getattr(self, "_v55_xy_changes", 0) or 0) + 1
        self._v55_motion_confirmed = True

        track = list(getattr(self, "_v55_track", []) or [])
        added = 0

        # En el primer cambio agregamos también la muestra anterior para que la
        # polilínea empiece exactamente donde se confirmó el movimiento.
        if not track:
            track.append(self._new_track_point(previous))
            added += 1

        track.append(self._new_track_point(current))
        added += 1

        if len(track) > self.MAX_TRACK_POINTS:
            track = track[-self.MAX_TRACK_POINTS:]
        self._v55_track = track
        self._v55_last_added_count = added
        return added

    # ------------------------------------------------------------- estado vivo
    def local_map_state(self) -> dict[str, Any]:
        state = super().local_map_state()

        # V45 ya saneó/ancló charging_base. Usamos robot-location cruda actual
        # en el mismo espacio de coordenadas que la base.
        robot = state.get("robot")
        self._ingest_pose(robot)

        direct_path = list(state.get("path") or [])
        track = list(getattr(self, "_v55_track", []) or [])

        # Si alguna vez aparece una trayectoria firmware real, sigue teniendo
        # prioridad. Mientras no exista, V55 publica el track temporal 10/24.
        if not direct_path and bool(getattr(self, "_v55_motion_confirmed", False)) and len(track) >= 2:
            state["path"] = track
            state["path_source"] = "trayectoria temporal 10/24"
            state["position_source"] = "10/24 temporal confirmado"
            state["accumulated_path_count"] = len(track)
            state["new_path_count"] = int(getattr(self, "_v55_last_added_count", 0) or 0)
            state["path_start"] = int(track[0]["id"])
            state["path_end"] = int(track[-1]["id"])
            state["position_stale"] = False
            state["telemetry_note"] = (
                "V55: recorrido vivo construido sólo con cambios X/Y temporales reales de 10/24"
            )

        state["v55_live_track"] = {
            "motion_confirmed": bool(getattr(self, "_v55_motion_confirmed", False)),
            "xy_changes": int(getattr(self, "_v55_xy_changes", 0) or 0),
            "points": len(track),
            "new_points": int(getattr(self, "_v55_last_added_count", 0) or 0),
            "action_reads_skipped": int(getattr(self, "_v55_action_reads_skipped", 0) or 0),
            "last_pose": tuple(getattr(self, "_v55_last_pose", ())) if getattr(self, "_v55_last_pose", None) else None,
            "source": "10/24 robot-location",
        }
        return state

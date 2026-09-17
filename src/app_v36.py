import math
import threading
import time

import app_v35
from xiaomi_map import XiaomiE10MapClient


class App(app_v35.App):
    """v36: fallback de posición desde el mapa real de Xiaomi Cloud.

    Si la telemetría LAN queda congelada, consulta periódicamente el mapa que usa
    Mi Home. Sólo confirma movimiento cuando vacuum_position cambia entre dos
    muestras cloud; la primera muestra nunca se convierte en trayectoria.
    """

    CLOUD_POLL_SECONDS = 3.0
    CLOUD_MOVE_EPSILON_M = 0.015
    CLOUD_POINT_ID_BASE = 300000

    def __init__(self):
        self._v36_cloud_worker = False
        self._v36_cloud_last_at = 0.0
        self._v36_cloud_last_xy = None
        self._v36_cloud_changes = 0
        self._v36_cloud_error = None
        self._v36_cloud_map_name = None
        self._v36_cloud_raw_robot = None
        self._v36_cloud_raw_base = None
        self._v36_cloud_point_id = self.CLOUD_POINT_ID_BASE
        self._v36_cloud_motion_confirmed = False
        super().__init__()

    # ---------------------------------------------------------- helpers cloud
    @staticmethod
    def _cloud_xy(point):
        if point is None:
            return None
        try:
            return float(point.x), float(point.y)
        except Exception:
            try:
                return float(point[0]), float(point[1])
            except Exception:
                return None

    @staticmethod
    def _cloud_scale(dx, dy):
        """Normaliza las unidades del parser a metros de forma conservadora."""
        magnitude = max(abs(float(dx)), abs(float(dy)))
        if magnitude > 100.0:
            return 0.001   # milímetros
        if magnitude > 20.0:
            return 0.01    # centímetros
        return 1.0         # metros

    @classmethod
    def _cloud_relative(cls, robot_xy, base_xy):
        if robot_xy is None or base_xy is None:
            return None
        dx = float(robot_xy[0]) - float(base_xy[0])
        dy = float(robot_xy[1]) - float(base_xy[1])
        scale = cls._cloud_scale(dx, dy)
        return {"x": dx * scale, "y": dy * scale, "angle": 0.0}

    def _cloud_session_ready(self):
        return bool(
            str((self.settings or {}).get("cloud_session") or "").strip()
            and str((self.settings or {}).get("device_did") or "").strip()
        )

    # ----------------------------------------------------------- polling cloud
    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        self._maybe_poll_cloud_position()
        return result

    def _maybe_poll_cloud_position(self):
        if not self.mapping_active or not self.vacuum:
            return
        if bool(getattr(self, "_v34_motion_confirmed", False)):
            return
        if not self._cloud_session_ready() or self._v36_cloud_worker:
            return
        now = time.monotonic()
        if now - float(self._v36_cloud_last_at or 0.0) < self.CLOUD_POLL_SECONDS:
            return
        self._v36_cloud_last_at = now
        self._v36_cloud_worker = True
        vacuum = self.vacuum
        settings = dict(self.settings or {})

        def worker():
            try:
                snapshot = XiaomiE10MapClient(vacuum, settings).load()
                data = snapshot.map_data
                robot_xy = self._cloud_xy(getattr(data, "vacuum_position", None))
                base_xy = self._cloud_xy(getattr(data, "charger", None))
                self._post_ui("cloud_map_position", snapshot.map_name, robot_xy, base_xy)
            except Exception as exc:
                self._post_ui("cloud_map_error", str(exc).strip() or "No se pudo leer el mapa de Xiaomi Cloud.")

        threading.Thread(target=worker, daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_map_position":
            self._v36_cloud_worker = False
            map_name, robot_xy, base_xy = payload
            self._v36_cloud_map_name = str(map_name)
            self._v36_cloud_raw_robot = robot_xy
            self._v36_cloud_raw_base = base_xy
            self._v36_cloud_error = None
            self._consume_cloud_position(robot_xy, base_xy)
            return
        if kind == "cloud_map_error":
            self._v36_cloud_worker = False
            self._v36_cloud_error = str(payload[0])
            return
        return super()._handle_ui_event(kind, payload)

    def _consume_cloud_position(self, robot_xy, base_xy):
        relative = self._cloud_relative(robot_xy, base_xy)
        if relative is None:
            return

        current = (float(relative["x"]), float(relative["y"]))
        previous = self._v36_cloud_last_xy
        self._v36_cloud_last_xy = current

        if previous is None:
            return

        moved = math.hypot(current[0] - previous[0], current[1] - previous[1])
        if moved < self.CLOUD_MOVE_EPSILON_M:
            return

        self._v36_cloud_changes += 1
        self._v36_cloud_motion_confirmed = True
        self._v34_motion_confirmed = True
        self._v34_position_changes = max(int(getattr(self, "_v34_position_changes", 0) or 0), self._v36_cloud_changes)

        if not self.local_map:
            return

        self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
        self.local_map.set_robot(relative)

        phase = int(self.mapping_phase or 0)
        if phase in (1, 2) and not (phase == 2 and self.mapping_transitioning):
            samples = []
            if self._v36_cloud_changes == 1:
                self._v36_cloud_point_id += 1
                samples.append({
                    "id": self._v36_cloud_point_id,
                    "x": previous[0],
                    "y": previous[1],
                    "phi": 0.0,
                    "update": 1,
                })
            self._v36_cloud_point_id += 1
            samples.append({
                "id": self._v36_cloud_point_id,
                "x": current[0],
                "y": current[1],
                "phi": 0.0,
                "update": 1,
            })
            self.local_map.merge_trajectory(samples, phase=phase)
            if phase == 1:
                self._rebuild_mapped_walls(force=False)

        try:
            self.map_status_label.configure(
                text=(
                    f"Posición Xiaomi Cloud · X {relative['x']:+.3f} m · Y {relative['y']:+.3f} m "
                    f"· cambios cloud {self._v36_cloud_changes}"
                )
            )
            self.mapping_steps_info.configure(
                text="Movimiento confirmado por Xiaomi Cloud · guardando trayectoria real del mapa de Mi Home"
            )
        except Exception:
            pass
        self._render_maps()

    # ------------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V36 ACTIVO · fallback Xiaomi Cloud\n"
            "=============================================\n"
            f"sesión cloud disponible: {self._cloud_session_ready()}\n"
            f"mapa cloud: {self._v36_cloud_map_name or '—'}\n"
            f"vacuum_position cloud crudo: {self._v36_cloud_raw_robot!r}\n"
            f"charger cloud crudo: {self._v36_cloud_raw_base!r}\n"
            f"cambios cloud confirmados: {self._v36_cloud_changes}\n"
            f"movimiento cloud confirmado: {self._v36_cloud_motion_confirmed}\n"
            f"error cloud: {self._v36_cloud_error or '—'}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

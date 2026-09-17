import math
import sys
import threading
import time

import app_v38
from xiaomi_e10 import MODEL
from xiaomi_map import XiaomiE10MapClient


class App(app_v38.App):
    """v39: usa directamente el JSON de mapa de Xiaomi Home.

    La telemetría 10/24 del E10 queda como diagnóstico porque puede permanecer
    congelada tanto por LAN como por Cloud. La fuente principal pasa a ser el
    archivo v2 de Xiaomi Home: posición, base y `paths` se extraen del JSON ya
    descifrado y se convierten de milímetros a metros.
    """

    CLOUD_FILE_POLL_SECONDS = 1.6
    MAP_POINT_ID_BASE = 500_000
    MIN_REAL_MOVE_M = 0.015

    def __init__(self):
        self._v39_crypto_mode = None
        self._v39_envelope_version = None
        self._v39_raw_size = 0
        self._v39_map_id = None
        self._v39_resolution = None
        self._v39_parser_error = None
        self._v39_raw_robot = None
        self._v39_raw_base = None
        self._v39_raw_path_count = 0
        self._v39_distinct_path_count = 0
        self._v39_last_path_signature = None
        self._v39_path_changes = 0
        self._v39_robot_source = "—"
        self._v39_last_robot_raw = None
        self._v39_restore_attempts = 0
        self._v39_started_after_update = "--after-update" in sys.argv
        super().__init__()

        # Una actualización relanza la aplicación muy rápido después del
        # instalador. Reaplicamos la geometría en varias etapas para que ningún
        # Configure tardío de Tk/Windows pueda pisar la posición guardada.
        for delay in (40, 260, 850, 1600):
            self.after(delay, self._v39_restore_saved_window)

    # ------------------------------------------------ ventana post-actualización
    def _v39_restore_saved_window(self):
        restored = self._validated_saved_geometry()
        if not restored:
            return
        try:
            width, height, x, y = restored
            wanted_state = str((self.settings or {}).get("window_state") or "normal")
            self._v39_restore_attempts += 1

            # La geometría normal se aplica siempre antes de maximizar. Así
            # Windows conserva el rectángulo correcto al restaurar desde zoomed.
            try:
                if str(self.state()) == "zoomed":
                    self.state("normal")
            except Exception:
                pass
            self.geometry(f"{width}x{height}+{x}+{y}")
            self._v38_last_normal_geometry = f"{width}x{height}+{x}+{y}"
            self.update_idletasks()
            if wanted_state == "zoomed":
                self.state("zoomed")
        except Exception:
            pass

    # ------------------------------------------------ archivo real Xiaomi Home
    def _v38_maybe_poll_map_file(self):
        """Reemplaza el sondeo v38 y conserva metadatos/paths del mapa v2."""
        if not self.mapping_active or not self.vacuum:
            return
        if not self._cloud_session_ready() or self._v38_map_worker:
            return
        now = time.monotonic()
        if now - float(self._v38_map_last_at or 0.0) < self.CLOUD_FILE_POLL_SECONDS:
            return
        self._v38_map_last_at = now
        self._v38_map_worker = True
        vacuum = self.vacuum
        settings = dict(self.settings or {})

        def worker():
            try:
                snapshot = XiaomiE10MapClient(vacuum, settings).load()
                self._post_ui("cloud_file_map_state_v39", snapshot)
            except Exception as exc:
                self._post_ui(
                    "cloud_file_map_error_v39",
                    str(exc).strip() or "No se pudo descargar/leer el mapa real de Xiaomi Cloud.",
                )

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _v39_relative_mm(point, base):
        if point is None or base is None:
            return None
        try:
            return {
                "x": (float(point[0]) - float(base[0])) * 0.001,
                "y": (float(point[1]) - float(base[1])) * 0.001,
                "angle": 0.0,
            }
        except Exception:
            return None

    @classmethod
    def _v39_local_path(cls, raw_path, base):
        if not raw_path or base is None:
            return []
        result = []
        previous = None
        for raw in raw_path:
            point = cls._v39_relative_mm(raw, base)
            if point is None:
                continue
            current = (float(point["x"]), float(point["y"]))
            # Descarta duplicados consecutivos y coordenadas físicamente absurdas.
            if max(abs(current[0]), abs(current[1])) > 150.0:
                continue
            if previous is not None and math.hypot(current[0] - previous[0], current[1] - previous[1]) < 0.001:
                continue
            result.append(point)
            previous = current
        return result

    @staticmethod
    def _v39_path_has_motion(points):
        if len(points) < 2:
            return False
        previous = points[0]
        for point in points[1:]:
            if math.hypot(
                float(point["x"]) - float(previous["x"]),
                float(point["y"]) - float(previous["y"]),
            ) >= App.MIN_REAL_MOVE_M:
                return True
            previous = point
        return False

    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_file_map_state_v39":
            self._v38_map_worker = False
            snapshot = payload[0] if payload else None
            if snapshot is not None:
                self._v39_consume_snapshot(snapshot)
            return
        if kind == "cloud_file_map_error_v39":
            self._v38_map_worker = False
            message = str(payload[0]) if payload else "Error de mapa Xiaomi Home"
            self._v38_map_error = message
            return
        return super()._handle_ui_event(kind, payload)

    def _v39_consume_snapshot(self, snapshot):
        self._v38_map_reads += 1
        self._v38_map_name = str(snapshot.map_name)
        self._v38_map_error = None
        self._v39_crypto_mode = snapshot.crypto_mode
        self._v39_envelope_version = snapshot.envelope_version
        self._v39_raw_size = int(snapshot.raw_size or 0)
        self._v39_map_id = snapshot.map_id
        self._v39_resolution = snapshot.resolution
        self._v39_parser_error = snapshot.parser_error
        self._v39_raw_robot = snapshot.raw_robot
        self._v39_raw_base = snapshot.raw_base
        raw_path = list(snapshot.raw_path or [])
        self._v39_raw_path_count = len(raw_path)

        base = snapshot.raw_base
        local_path = self._v39_local_path(raw_path, base)
        self._v39_distinct_path_count = len(local_path)

        robot_raw = snapshot.raw_robot
        path_signature = None
        if raw_path:
            last = raw_path[-1]
            path_signature = (len(raw_path), round(float(last[0]), 3), round(float(last[1]), 3))
        if path_signature is not None and path_signature != self._v39_last_path_signature:
            if self._v39_last_path_signature is not None:
                self._v39_path_changes += 1
            self._v39_last_path_signature = path_signature

        # Si `position` queda clavada pero el path crece, el último punto del
        # recorrido es una fuente mejor para el icono actual del robot.
        if raw_path:
            if robot_raw is None:
                robot_raw = raw_path[-1]
                self._v39_robot_source = "último punto de paths"
            elif self._v39_last_robot_raw is not None and tuple(robot_raw) == tuple(self._v39_last_robot_raw) and self._v39_path_changes:
                robot_raw = raw_path[-1]
                self._v39_robot_source = "paths (position congelada)"
            else:
                self._v39_robot_source = "position del mapa Xiaomi Home"
        elif robot_raw is not None:
            self._v39_robot_source = "position del mapa Xiaomi Home"
        self._v39_last_robot_raw = snapshot.raw_robot

        robot = self._v39_relative_mm(robot_raw, base)
        self._v38_map_robot = robot_raw
        self._v38_map_base = base

        real_motion = self._v39_path_has_motion(local_path)
        if not real_motion and robot is not None and self._v38_map_last_xy is not None:
            real_motion = math.hypot(
                float(robot["x"]) - self._v38_map_last_xy[0],
                float(robot["y"]) - self._v38_map_last_xy[1],
            ) >= self.MIN_REAL_MOVE_M
        if robot is not None:
            self._v38_map_last_xy = (float(robot["x"]), float(robot["y"]))

        if not real_motion or not self.local_map:
            return

        self._v38_map_changes = max(self._v38_map_changes + 1, self._v39_path_changes, 1)
        self._v36_cloud_changes = max(int(getattr(self, "_v36_cloud_changes", 0) or 0), self._v38_map_changes)
        self._v36_cloud_motion_confirmed = True
        self._v34_motion_confirmed = True
        self._v34_position_changes = max(int(getattr(self, "_v34_position_changes", 0) or 0), self._v38_map_changes)

        self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
        if robot is None and local_path:
            robot = dict(local_path[-1])
        if robot is not None:
            self.local_map.set_robot(robot)

        phase = int(self.mapping_phase or 0)
        if phase in (1, 2) and not (phase == 2 and self.mapping_transitioning) and local_path:
            samples = []
            for index, point in enumerate(local_path):
                samples.append({
                    "id": self.MAP_POINT_ID_BASE + index,
                    "x": float(point["x"]),
                    "y": float(point["y"]),
                    "phi": 0.0,
                    "update": 1,
                })
            self.local_map.merge_trajectory(samples, phase=phase)
            if phase == 1 and len(local_path) >= 3:
                self._rebuild_mapped_walls(force=False)

        try:
            if robot is not None:
                self.map_status_label.configure(
                    text=(
                        f"Xiaomi Home EN VIVO · X {robot['x']:+.3f} m · Y {robot['y']:+.3f} m "
                        f"· recorrido {len(local_path)} puntos"
                    )
                )
            self.mapping_steps_info.configure(
                text="Movimiento confirmado por el archivo real de Xiaomi Home · trayectoria en vivo"
            )
        except Exception:
            pass
        self._render_maps()

    # ------------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V39 ACTIVO · Xiaomi Home v2 real\n"
            "=============================================\n"
            f"descifrado: {self._v39_crypto_mode or '—'}\n"
            f"clave modelo: {MODEL[-16:]!r} · {len(MODEL[-16:].encode('latin1'))} bytes\n"
            f"envelope version: {self._v39_envelope_version!r}\n"
            f"archivo descargado: {self._v39_raw_size} bytes\n"
            f"map_id JSON: {self._v39_map_id!r} · resolution: {self._v39_resolution!r}\n"
            f"position JSON crudo: {self._v39_raw_robot!r}\n"
            f"base JSON cruda: {self._v39_raw_base!r}\n"
            f"paths JSON: {self._v39_raw_path_count} puntos · distintos útiles: {self._v39_distinct_path_count}\n"
            f"cambios de path: {self._v39_path_changes}\n"
            f"fuente icono robot: {self._v39_robot_source}\n"
            f"error parser visual: {self._v39_parser_error or '—'}\n"
            f"restauraciones de ventana aplicadas: {self._v39_restore_attempts}\n"
            f"inicio marcado post-update: {self._v39_started_after_update}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

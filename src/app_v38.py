import ctypes
import math
import re
import threading
import time

import app_v37
from xiaomi_map import XiaomiE10MapClient


class App(app_v37.App):
    """v38: mapa Cloud real + geometría persistente de la ventana.

    10/24 queda como diagnóstico porque tanto LAN como MIoT Cloud pueden devolver
    una pose fija. En paralelo se descarga el archivo de mapa usado por Mi Home y
    sólo se confirma movimiento cuando ``vacuum_position`` cambia entre dos mapas.

    La ventana principal recuerda posición, tamaño y estado maximizado entre
    ejecuciones. Si cambia la configuración de monitores, la geometría se ajusta
    al área útil del monitor más cercano para no quedar fuera de pantalla.
    """

    CLOUD_FILE_POLL_SECONDS = 3.0
    CLOUD_FILE_MOVE_EPSILON_M = 0.015
    _GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")

    def __init__(self):
        self._v38_map_worker = False
        self._v38_map_last_at = 0.0
        self._v38_map_reads = 0
        self._v38_map_error = None
        self._v38_map_name = None
        self._v38_map_robot = None
        self._v38_map_base = None
        self._v38_map_last_xy = None
        self._v38_map_changes = 0

        self._v38_geometry_ready = False
        self._v38_geometry_save_job = None
        self._v38_last_normal_geometry = None
        super().__init__()

        # Capturamos cambios de tamaño/posición una vez que la UI terminó de
        # arrancar. El callback de v35 usa nuestro _center_initial_window.
        self.bind("<Configure>", self._v38_on_configure, add="+")
        self.after(900, self._v38_enable_geometry_tracking)

    # ----------------------------------------------------- ventana persistente
    @classmethod
    def _parse_geometry(cls, value):
        match = cls._GEOMETRY_RE.match(str(value or "").strip())
        if not match:
            return None
        width, height, x, y = (int(part) for part in match.groups())
        if width < 320 or height < 240 or width > 20000 or height > 20000:
            return None
        if abs(x) > 100000 or abs(y) > 100000:
            return None
        return width, height, x, y

    def _work_area_for_rect(self, x, y, width, height):
        """Área útil del monitor más cercano al rectángulo guardado."""
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            rect = RECT(int(x), int(y), int(x + width), int(y + height))
            monitor = ctypes.windll.user32.MonitorFromRect(ctypes.byref(rect), 2)  # NEAREST
            if monitor:
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    work = info.rcWork
                    return int(work.left), int(work.top), int(work.right), int(work.bottom)
        except Exception:
            pass
        return self._usable_work_area()

    def _validated_saved_geometry(self):
        parsed = self._parse_geometry((self.settings or {}).get("window_geometry"))
        if not parsed:
            return None
        width, height, x, y = parsed
        left, top, right, bottom = self._work_area_for_rect(x, y, width, height)
        usable_w = max(1, right - left)
        usable_h = max(1, bottom - top)

        # Respeta el tamaño elegido siempre que entre. Si la resolución cambió,
        # sólo lo reduce lo imprescindible y lo vuelve a poner dentro del monitor.
        margin = 8
        width = min(width, max(640, usable_w - margin * 2))
        height = min(height, max(520, usable_h - margin * 2))
        x = max(left, min(x, right - width))
        y = max(top, min(y, bottom - height))
        return width, height, x, y

    def _center_initial_window(self):
        """Restaura la última geometría; centra sólo en el primer uso."""
        restored = self._validated_saved_geometry()
        if not restored:
            return super()._center_initial_window()
        try:
            width, height, x, y = restored
            self.geometry(f"{width}x{height}+{x}+{y}")
            self._v38_last_normal_geometry = f"{width}x{height}+{x}+{y}"
            if str((self.settings or {}).get("window_state") or "normal") == "zoomed":
                self.after(120, lambda: self.state("zoomed"))
        except Exception:
            super()._center_initial_window()

    def _v38_enable_geometry_tracking(self):
        self._v38_geometry_ready = True
        self._v38_capture_geometry(save=False)

    def _v38_on_configure(self, event=None):
        if not self._v38_geometry_ready or event is not None and event.widget is not self:
            return
        if self._v38_geometry_save_job:
            try:
                self.after_cancel(self._v38_geometry_save_job)
            except Exception:
                pass
        self._v38_geometry_save_job = self.after(650, self._v38_capture_geometry)

    def _v38_capture_geometry(self, save=True):
        self._v38_geometry_save_job = None
        try:
            state = str(self.state())
            if state == "normal":
                self.update_idletasks()
                geometry = self.geometry()
                if self._parse_geometry(geometry):
                    self._v38_last_normal_geometry = geometry
                    self.settings["window_geometry"] = geometry
                    self.settings["window_state"] = "normal"
            elif state == "zoomed":
                self.settings["window_state"] = "zoomed"
            else:
                return
            if save:
                self.store.save(self.settings)
        except Exception:
            pass

    def destroy(self):
        # Guardamos antes de que Tk destruya el handle de la ventana.
        try:
            if str(self.state()) == "normal":
                self._v38_capture_geometry(save=False)
            elif str(self.state()) == "zoomed":
                self.settings["window_state"] = "zoomed"
            if self._v38_last_normal_geometry:
                self.settings["window_geometry"] = self._v38_last_normal_geometry
            self.store.save(self.settings)
        except Exception:
            pass
        return super().destroy()

    # ------------------------------------------------ archivo de mapa Mi Home
    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        self._v38_maybe_poll_map_file()
        return result

    def _v38_maybe_poll_map_file(self):
        if not self.mapping_active or not self.vacuum:
            return
        if bool(getattr(self, "_v34_motion_confirmed", False)):
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
                data = snapshot.map_data
                robot_xy = self._cloud_xy(getattr(data, "vacuum_position", None))
                base_xy = self._cloud_xy(getattr(data, "charger", None))
                self._post_ui("cloud_file_map_state", snapshot.map_name, robot_xy, base_xy)
            except Exception as exc:
                self._post_ui(
                    "cloud_file_map_error",
                    str(exc).strip() or "No se pudo descargar/leer el mapa real de Xiaomi Cloud.",
                )

        threading.Thread(target=worker, daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_file_map_state":
            self._v38_map_worker = False
            map_name, robot_xy, base_xy = payload
            self._v38_map_reads += 1
            self._v38_map_name = str(map_name)
            self._v38_map_robot = robot_xy
            self._v38_map_base = base_xy
            self._v38_map_error = None
            self._v38_consume_map_file_position(robot_xy, base_xy)
            return
        if kind == "cloud_file_map_error":
            self._v38_map_worker = False
            self._v38_map_error = str(payload[0]) if payload else "Error de mapa Cloud"
            return
        return super()._handle_ui_event(kind, payload)

    def _v38_consume_map_file_position(self, robot_xy, base_xy):
        relative = self._cloud_relative(robot_xy, base_xy)
        if relative is None:
            return
        current = (float(relative["x"]), float(relative["y"]))
        previous = self._v38_map_last_xy
        self._v38_map_last_xy = current
        if previous is None:
            return

        moved = math.hypot(current[0] - previous[0], current[1] - previous[1])
        if moved < self.CLOUD_FILE_MOVE_EPSILON_M:
            return

        self._v38_map_changes += 1

        # _consume_cloud_position contiene el pipeline ya probado para guardar
        # trayectoria. Le damos explícitamente la muestra anterior DE ESTA FUENTE
        # para que el 10/24 fijo no pueda provocar un falso positivo.
        self._v36_cloud_last_xy = previous
        self._consume_cloud_position(robot_xy, base_xy)
        try:
            self.map_status_label.configure(
                text=(
                    f"Mapa Xiaomi Cloud · X {current[0]:+.3f} m · Y {current[1]:+.3f} m "
                    f"· cambios reales {self._v38_map_changes}"
                )
            )
        except Exception:
            pass

    # ------------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V38 ACTIVO · archivo de mapa Mi Home\n"
            "================================================\n"
            f"mapas Cloud descargados: {self._v38_map_reads}\n"
            f"objeto/mapa actual: {self._v38_map_name or '—'}\n"
            f"vacuum_position del archivo: {self._v38_map_robot!r}\n"
            f"charger del archivo: {self._v38_map_base!r}\n"
            f"cambios de posición del archivo: {self._v38_map_changes}\n"
            f"error archivo de mapa: {self._v38_map_error or '—'}\n"
            f"geometría guardada: {(self.settings or {}).get('window_geometry') or '—'}\n"
            f"estado ventana guardado: {(self.settings or {}).get('window_state') or 'normal'}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

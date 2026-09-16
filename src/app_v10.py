import math
import threading
import time
import traceback

import app_v9


class App(app_v9.App):
    """v10: agrega asistencia automática de acople sin tocar torque de ruedas."""

    def __init__(self):
        self._dock_assist_status = -1
        self._dock_assist_reference_distance = None
        self._dock_assist_last_distance = None
        self._dock_assist_last_position = None
        self._dock_assist_last_motion_at = None
        self._dock_assist_retry_until = 0.0
        self._dock_assist_attempts = 0
        self._dock_assist_worker_running = False
        self._dock_assist_had_retry = False
        super().__init__()

    # -------------------------------------------------------- eventos seguros
    def _handle_ui_event(self, kind, payload):
        if kind == "status_ok":
            status = payload[0]
            self._dock_assist_on_status(int(getattr(status, "status", -1)))
            return super()._handle_ui_event(kind, payload)

        if kind == "dock_assist_started":
            attempt = int(payload[0])
            self._set_banner(
                f"Asistencia de base · detecté que quedó sin avanzar cerca de la base. "
                f"Reintentando el acople ({attempt}/2)…"
            )
            return

        if kind == "dock_assist_done":
            self._dock_assist_worker_running = False
            self._dock_assist_retry_until = time.monotonic() + 18.0
            self._dock_assist_last_motion_at = time.monotonic()
            self._dock_assist_last_position = None
            self._dock_assist_last_distance = None
            self._set_banner(
                "Asistencia de base · reinicié la maniobra de acople. "
                "Voy a seguir vigilando hasta que cargue."
            )
            return

        if kind == "dock_assist_error":
            self._dock_assist_worker_running = False
            self._dock_assist_retry_until = time.monotonic() + 20.0
            self._set_banner(f"Asistencia de base no disponible: {payload[0]}")
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------- estado de retorno
    def _dock_assist_reset_cycle(self):
        self._dock_assist_reference_distance = None
        self._dock_assist_last_distance = None
        self._dock_assist_last_position = None
        self._dock_assist_last_motion_at = None
        self._dock_assist_retry_until = 0.0
        self._dock_assist_attempts = 0
        self._dock_assist_worker_running = False
        self._dock_assist_had_retry = False

    def _dock_assist_on_status(self, status):
        previous = self._dock_assist_status
        self._dock_assist_status = int(status)
        now = time.monotonic()

        if status == 3:  # Volviendo a la base
            # Un STOP/START interno del reintento puede pasar un instante por
            # espera/pausa. Conservamos el mismo ciclo durante esa ventana para
            # no reiniciar el contador y entrar en un bucle infinito.
            continuing_retry = (
                self._dock_assist_had_retry
                and now < self._dock_assist_retry_until + 45.0
            )
            if previous != 3 and not continuing_retry:
                self._dock_assist_reset_cycle()
                self._dock_assist_status = 3
                self._dock_assist_last_motion_at = now
            elif self._dock_assist_last_motion_at is None:
                self._dock_assist_last_motion_at = now
            return

        if status == 4:  # Cargando
            if self._dock_assist_had_retry:
                self._set_banner("Asistencia de base · acople completado y cargando correctamente.")
            self._dock_assist_reset_cycle()
            self._dock_assist_status = 4
            return

        # Mientras el propio reintento está cambiando de estado, no borramos
        # el ciclo. Una limpieza nueva sí lo cancela inmediatamente.
        if status in (5, 6, 7, 8):
            self._dock_assist_reset_cycle()
            self._dock_assist_status = int(status)
            return

        if self._dock_assist_worker_running:
            return
        if self._dock_assist_had_retry and now < self._dock_assist_retry_until + 45.0:
            return

        if status in (0, 1, 2):
            self._dock_assist_reset_cycle()
            self._dock_assist_status = int(status)

    def _apply_map_state(self, state):
        super()._apply_map_state(state)
        self._dock_assist_process_position(
            state.get("robot"),
            state.get("charging_base"),
        )

    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        # Durante el retorno leemos posición más seguido para detectar un atasco
        # en la rampa de la base sin esperar varios segundos entre muestras.
        delay = 700 if (self.mapping_active or self._dock_assist_status == 3) else 2200
        self.after(delay, self._poll_local_map)

    # ----------------------------------------------------- asistencia de base
    @staticmethod
    def _dock_point(point):
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    @staticmethod
    def _near_base_limit(reference_distance):
        """Umbral tolerante a coordenadas expresadas en m, cm o mm."""
        reference_distance = max(float(reference_distance), 1e-9)
        relative = reference_distance * 0.18
        if reference_distance > 100.0:
            absolute = 650.0      # normalmente milímetros
        elif reference_distance > 20.0:
            absolute = 65.0       # representación centimétrica poco común
        else:
            absolute = 0.65       # normalmente metros
        return max(relative, absolute)

    def _dock_assist_process_position(self, robot, base):
        if not bool(self.settings.get("dock_assist", True)):
            return
        if self._dock_assist_status != 3 or not self.vacuum:
            return
        if self._dock_assist_worker_running:
            return

        robot_xy = self._dock_point(robot)
        base_xy = self._dock_point(base)
        if not robot_xy or not base_xy:
            return

        now = time.monotonic()
        distance = math.hypot(robot_xy[0] - base_xy[0], robot_xy[1] - base_xy[1])
        if not math.isfinite(distance):
            return

        if self._dock_assist_reference_distance is None:
            self._dock_assist_reference_distance = max(distance, 1e-6)
            self._dock_assist_last_distance = distance
            self._dock_assist_last_position = robot_xy
            self._dock_assist_last_motion_at = now
            return

        self._dock_assist_reference_distance = max(
            float(self._dock_assist_reference_distance),
            distance,
        )

        reference = max(float(self._dock_assist_reference_distance), 1e-6)
        motion_threshold = max(reference * 0.002, 1e-6)

        moved = 0.0
        if self._dock_assist_last_position is not None:
            moved = math.hypot(
                robot_xy[0] - self._dock_assist_last_position[0],
                robot_xy[1] - self._dock_assist_last_position[1],
            )

        distance_progress = 0.0
        if self._dock_assist_last_distance is not None:
            distance_progress = max(0.0, float(self._dock_assist_last_distance) - distance)

        if moved >= motion_threshold or distance_progress >= motion_threshold:
            self._dock_assist_last_motion_at = now

        self._dock_assist_last_position = robot_xy
        self._dock_assist_last_distance = distance

        near_base = distance <= self._near_base_limit(reference)
        stalled_for = now - float(self._dock_assist_last_motion_at or now)

        # Damos 10 s para la alineación normal con los contactos antes de actuar.
        if not near_base or stalled_for < 10.0:
            return
        if now < self._dock_assist_retry_until:
            return

        if self._dock_assist_attempts >= 2:
            self._set_banner(
                "Asistencia de base · hice 2 reintentos y el E10 sigue sin poder subir. "
                "Conviene revisar que la base esté firme, nivelada y que la rampa/ruedas estén limpias."
            )
            self._dock_assist_retry_until = now + 60.0
            return

        self._dock_assist_attempts += 1
        self._dock_assist_worker_running = True
        self._dock_assist_had_retry = True
        attempt = self._dock_assist_attempts
        vacuum = self.vacuum
        self._post_ui("dock_assist_started", attempt)

        threading.Thread(
            target=self._dock_assist_retry_worker,
            args=(vacuum, attempt),
            daemon=True,
        ).start()

    def _dock_assist_retry_worker(self, vacuum, attempt):
        """Reinicia el controlador de retorno sin usar control manual de ruedas.

        MIoT expone set-go-charging (7/7, piid 43: 1 Start / 2 Stop).
        Si ese método no está disponible en un firmware concreto, usamos las
        acciones estándar stop + start-charge como fallback.
        """
        try:
            try:
                vacuum.device.call_action_by(7, 7, [2])
            except Exception:
                try:
                    vacuum.stop()
                except Exception:
                    pass

            time.sleep(0.8)

            try:
                vacuum.device.call_action_by(7, 7, [1])
            except Exception:
                vacuum.dock()

            self._post_ui("dock_assist_done", attempt)
        except Exception as exc:
            self._post_ui(
                "dock_assist_error",
                str(exc).strip() or "el robot rechazó el reintento de acople",
            )


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        details = traceback.format_exc()
        app_v9._save_crash_log(details)
        try:
            root = app_v9.tk.Tk()
            root.withdraw()
            app_v9.messagebox.showerror(
                "Aspiradora Xiaomi",
                "La aplicación encontró un error y guardó el detalle en:\n"
                "%LOCALAPPDATA%\\Aspiradora Xiaomi\\crash.log",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass

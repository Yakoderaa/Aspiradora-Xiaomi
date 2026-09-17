import threading
import time
from tkinter import messagebox

import app_v12


class App(app_v12.App):
    """v13: Paso 1 -> base -> Paso 2 automático, conservando botones separados."""

    def __init__(self):
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._auto_step2_serial = 0
        self._last_robot_status = -1
        super().__init__()
        if hasattr(self, "mapping_steps_info"):
            self.mapping_steps_info.configure(
                text="Paso 1: perímetro · vuelve a base · Paso 2: interior automático"
            )

    # ------------------------------------------------------------ eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "edge_only_complete":
            banner = str(payload[0]) if payload else "Paso 1 terminado."
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step1_complete = self._has_perimeter_data()

            if self.mapping_step1_complete:
                self._auto_step2_pending = True
                self._auto_step2_scheduled = False
                self._set_banner(
                    "Paso 1 terminado · perímetro guardado. Esperando que el E10 vuelva a la base para iniciar Paso 2 automáticamente…"
                )
            else:
                self._auto_step2_pending = False
                self._set_banner(banner)

            self._sync_mapping_step_buttons()
            self._render_maps()
            return

        if kind == "status_ok":
            status_obj = payload[0]
            self._last_robot_status = int(getattr(status_obj, "status", -1))
            result = super()._handle_ui_event(kind, payload)
            self._maybe_schedule_auto_step2()
            return result

        if kind == "auto_step2_started":
            self._set_banner("Paso 2 · completando automáticamente el interior en tiempo real…")
            return

        if kind == "auto_step2_error":
            message = str(payload[0])
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("No se pudo iniciar automáticamente el Paso 2.")
            messagebox.showerror("Paso 2 · Interior", message, parent=self)
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------ botones
    def _sync_mapping_step_buttons(self):
        super()._sync_mapping_step_buttons()
        if not hasattr(self, "step2_mapping_button"):
            return
        if self._auto_step2_pending and not self.mapping_active:
            self.step2_mapping_button.configure(
                state="disabled",
                text="Paso 2 · Esperando base…",
            )

    def start_interior_mapping(self):
        # Si el usuario inicia el Paso 2 manualmente en otro momento, cancelamos
        # cualquier transición automática pendiente.
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._auto_step2_serial += 1
        return super().start_interior_mapping()

    # ------------------------------------------------------------ Paso 1
    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if self.mapping_active:
            messagebox.showinfo("Mapeo en curso", "Primero detené el paso actual.", parent=self)
            return

        ok = messagebox.askyesno(
            "Paso 1 · Solo bordes",
            "Se va a borrar el mapa local de esta aplicación y comenzar un recorrido nuevo.\n\n"
            "Primero el E10 recorrerá únicamente los bordes. Al terminar volverá a la base; "
            "cuando la app detecte que quedó cargando, iniciará automáticamente el Paso 2 para completar el interior.\n\n"
            "Los dos pasos siguen separados y se dibujan por separado en el mapa.",
            parent=self,
        )
        if not ok:
            return

        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._auto_step2_serial += 1
        self._edge_session += 1
        session = self._edge_session
        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 1
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 1 · iniciando recorrido exclusivo por bordes…")
        self._edge_log(f"Solicitando EDGE. sesión={session}")
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.start_mapping_perimeter()
                self._post_ui("edge_only_started", session)
            except Exception as exc:
                self._edge_log(f"Error al iniciar EDGE: {exc}")
                self._post_ui(
                    "edge_only_error",
                    str(exc).strip() or "El E10 rechazó el recorrido exclusivo de borde.",
                )

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------- transición automática
    def _maybe_schedule_auto_step2(self):
        if not self._auto_step2_pending or self._auto_step2_scheduled:
            return
        if self.mapping_active or not self.vacuum:
            return

        # El E10 reporta 4 cuando quedó acoplado y cargando. Esperamos un poco
        # para que los contactos y el estado del firmware se estabilicen.
        if self._last_robot_status != 4:
            if self._last_robot_status == 3:
                self._set_banner(
                    "Paso 1 terminado · E10 volviendo a la base. Paso 2 arrancará automáticamente al quedar cargando…"
                )
            return

        self._auto_step2_scheduled = True
        self._auto_step2_serial += 1
        serial = self._auto_step2_serial
        self._set_banner("E10 en la base · preparando Paso 2 automático…")
        self.after(1800, lambda: self._start_auto_step2_if_ready(serial))

    def _start_auto_step2_if_ready(self, serial):
        if serial != self._auto_step2_serial:
            return
        self._auto_step2_scheduled = False
        if not self._auto_step2_pending:
            return
        if self.mapping_active or not self.vacuum:
            return
        if self._last_robot_status != 4:
            return
        if not (self.mapping_step1_complete or self._has_perimeter_data()):
            self._auto_step2_pending = False
            self._set_banner("No encontré datos del perímetro; no inicié el Paso 2.")
            self._sync_mapping_step_buttons()
            return

        self._auto_step2_pending = False
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = True
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 2 · saliendo de la base para completar el interior…")
        vacuum = self.vacuum

        def worker():
            try:
                time.sleep(0.7)
                vacuum.start_mapping_interior()
                self._post_ui("auto_step2_started")
            except Exception as exc:
                self._post_ui(
                    "auto_step2_error",
                    str(exc).strip() or "El E10 rechazó el recorrido interior automático.",
                )

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

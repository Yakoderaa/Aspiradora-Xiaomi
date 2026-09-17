import threading
import time

import app_v27


class App(app_v27.App):
    """v28: trayectoria 10/12 robusta + retorno manual a base sin reinicios."""

    def __init__(self):
        self._manual_dock_guard = False
        self._manual_dock_at = 0.0
        super().__init__()

    # ------------------------------------------------ regreso manual a la base
    def _cancel_auto_starts_for_manual_dock(self):
        """Cancela cualquier flujo interno capaz de volver a arrancar el robot.

        Un clic explícito en "Volver a base" significa que el usuario quiere que
        el E10 se quede en la base. En versiones anteriores podía quedar pendiente
        el Paso 2 automático del mapeo; al detectar estado 4 (cargando), ese flujo
        iniciaba otra limpieza. También invalidamos la sesión EDGE para que un
        evento tardío no vuelva a armar la transición.
        """
        self._manual_dock_guard = True
        self._manual_dock_at = time.monotonic()

        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._auto_step2_serial = int(getattr(self, "_auto_step2_serial", 0) or 0) + 1
        self._edge_session = int(getattr(self, "_edge_session", 0) or 0) + 1

        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False

        try:
            self._sync_mapping_step_buttons()
        except Exception:
            pass
        try:
            self._render_maps()
        except Exception:
            pass

    def _clear_manual_dock_guard(self):
        self._manual_dock_guard = False

    def dock(self):
        if not self.vacuum:
            return
        self._cancel_auto_starts_for_manual_dock()
        self._set_banner("Volviendo a la base · se cancelaron arranques automáticos pendientes…")
        self._run_command("Enviando el robot a la base…", self.vacuum.dock)

    def _execute_quick_action(self, code):
        code = str(code or "")
        if code == "dock":
            self.dock()
            return
        if code in ("clean_all", "clean_map") or code.startswith("zone:"):
            self._clear_manual_dock_guard()
        return super()._execute_quick_action(code)

    def start_clean(self):
        self._clear_manual_dock_guard()
        return super().start_clean()

    def start_new_mapping(self):
        self._clear_manual_dock_guard()
        return super().start_new_mapping()

    def start_interior_mapping(self):
        self._clear_manual_dock_guard()
        return super().start_interior_mapping()

    # ------------------------------------------------ eventos tardíos/auto start
    def _handle_ui_event(self, kind, payload):
        # Un EDGE_COMPLETE puede haber quedado en la cola justo antes de que el
        # usuario pulsara volver a base. No permitimos que rearme Paso 2.
        if kind == "edge_only_complete" and self._manual_dock_guard:
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            try:
                self.mapping_step1_complete = bool(self._has_perimeter_data())
            except Exception:
                pass
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("Robot enviado a la base · el Paso 2 automático quedó cancelado.")
            return

        # El flujo rápido "aspirar y después mapear" también puede terminar
        # después de una orden manual de retorno. En ese caso no arrancamos mapa.
        if kind == "tray_clean_then_map_ready" and self._manual_dock_guard:
            self._set_banner("Robot en retorno/base · no inicié el mapeo automático porque pediste volver a la base.")
            return

        return super()._handle_ui_event(kind, payload)

    def _start_auto_step2_if_ready(self, serial):
        """Versión cancelable del arranque automático heredado de v13."""
        if self._manual_dock_guard:
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            return
        if serial != self._auto_step2_serial:
            return
        self._auto_step2_scheduled = False
        if not self._auto_step2_pending:
            return
        if self.mapping_active or not self.vacuum:
            return
        if self._last_robot_status != 4:
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
        expected_serial = serial

        def worker():
            try:
                time.sleep(0.7)
                # Revalidamos justo antes de mandar START. Esto cubre el caso en
                # que el usuario pulse "Volver a base" durante esos 700 ms.
                if self._manual_dock_guard:
                    return
                if expected_serial != self._auto_step2_serial:
                    return
                if not self.mapping_active or int(self.mapping_phase or 0) != 2:
                    return
                vacuum.start_mapping_interior()
                self._post_ui("auto_step2_started")
            except Exception as exc:
                self._post_ui(
                    "auto_step2_error",
                    str(exc).strip() or "El E10 rechazó el recorrido interior automático.",
                )

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------ telemetría visible
    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        if (
            self.mapping_active
            and isinstance(state, dict)
            and state.get("position_stale")
            and not int(state.get("direct_path_count", 0) or 0)
            and not int(state.get("action_path_count", 0) or 0)
        ):
            note = str(state.get("telemetry_note") or "posición sin cambios")
            try:
                current = str(self.map_status_label.cget("text") or "")
                self.map_status_label.configure(text=f"{current} · {note}")
            except Exception:
                pass
        return result


if __name__ == "__main__":
    app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

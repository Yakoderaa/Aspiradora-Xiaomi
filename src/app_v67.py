import threading
import time

import app_v66


class App(app_v66.App):
    """V67: transición Paso 1 -> base -> Paso 2 con watchdog LAN propio."""

    BASE_WATCH_SECONDS = 180.0
    BASE_POLL_SECONDS = 0.85
    BASE_CONFIRM_SAMPLES = 2
    STEP2_SETTLE_MS = 2200

    def __init__(self):
        self._v67_step1_session_active = False
        self._v67_watch_serial = 0
        self._v67_watch_running = False
        self._v67_start_scheduled = False
        self._v67_transition_diag = {
            "completion_event": None,
            "pending": False,
            "watch_started": False,
            "watch_serial": 0,
            "dock_sent": False,
            "saw_returning": False,
            "base_confirmed": False,
            "base_confirmed_by": None,
            "last_status": None,
            "last_charging_state": None,
            "last_battery": None,
            "samples": 0,
            "step2_scheduled": False,
            "step2_started": False,
            "step2_start_error": None,
            "timeout": False,
        }
        super().__init__()

    # ----------------------------------------------------- sesión Paso 1
    def start_new_mapping(self):
        result = super().start_new_mapping()
        if bool(getattr(self, "mapping_active", False)) and int(getattr(self, "mapping_phase", 0) or 0) == 1:
            self._v67_step1_session_active = True
            self._v67_watch_serial += 1
            self._v67_watch_running = False
            self._v67_start_scheduled = False
            self._v67_transition_diag = {
                "completion_event": None,
                "pending": False,
                "watch_started": False,
                "watch_serial": self._v67_watch_serial,
                "dock_sent": False,
                "saw_returning": False,
                "base_confirmed": False,
                "base_confirmed_by": None,
                "last_status": None,
                "last_charging_state": None,
                "last_battery": None,
                "samples": 0,
                "step2_scheduled": False,
                "step2_started": False,
                "step2_start_error": None,
                "timeout": False,
            }
        return result

    def start_interior_mapping(self):
        # Inicio manual: invalida cualquier watchdog automático pendiente.
        self._v67_step1_session_active = False
        self._v67_watch_serial += 1
        self._v67_watch_running = False
        self._v67_start_scheduled = False
        return super().start_interior_mapping()

    # ---------------------------------------------------------- helpers
    @staticmethod
    def _v67_int(value):
        try:
            return int(value)
        except Exception:
            return None

    @classmethod
    def _v67_base_evidence(cls, status, charging_state):
        """Confirmación de base: estado CARGANDO o battery charging-state=1."""
        status = cls._v67_int(status)
        charging_state = cls._v67_int(charging_state)
        if charging_state == 1:
            return True, "battery charging-state=1"
        if status == 4:
            return True, "status=4 cargando"
        return False, None

    @classmethod
    def _v67_should_send_dock(cls, status, charging_state):
        base, _ = cls._v67_base_evidence(status, charging_state)
        if base:
            return False
        status = cls._v67_int(status)
        # 3 = ya volviendo a base. No mandamos un segundo dock.
        return status != 3

    @staticmethod
    def _v67_read_base_state(vacuum):
        values = vacuum._get_many([
            ("status", 2, 1),
            ("battery", 3, 1),
            ("charging_state", 3, 2),
        ])
        return {
            "status": values.get("status"),
            "battery": values.get("battery"),
            "charging_state": values.get("charging_state"),
        }

    def _v67_arm_transition(self, completion_event):
        """Arma Paso 2 aunque el cierre de Paso 1 venga por una ruta heredada."""
        if not self.vacuum:
            return False

        self._v67_step1_session_active = False
        self._auto_step2_pending = True
        # No tocamos _auto_step2_scheduled: la ruta V13 puede funcionar en
        # paralelo. V67 usa un schedule propio y ambos son one-shot por checks.
        self._v67_watch_serial += 1
        serial = self._v67_watch_serial
        self._v67_watch_running = True
        self._v67_start_scheduled = False

        diag = dict(getattr(self, "_v67_transition_diag", {}) or {})
        diag.update({
            "completion_event": str(completion_event),
            "pending": True,
            "watch_started": True,
            "watch_serial": serial,
            "dock_sent": False,
            "saw_returning": False,
            "base_confirmed": False,
            "base_confirmed_by": None,
            "last_status": None,
            "last_charging_state": None,
            "last_battery": None,
            "samples": 0,
            "step2_scheduled": False,
            "step2_started": False,
            "step2_start_error": None,
            "timeout": False,
        })
        self._v67_transition_diag = diag

        vacuum = self.vacuum
        threading.Thread(
            target=self._v67_watch_base_worker,
            args=(vacuum, serial),
            daemon=True,
        ).start()
        return True

    # ------------------------------------------------------- watchdog base
    def _v67_watch_base_worker(self, vacuum, serial):
        deadline = time.monotonic() + self.BASE_WATCH_SECONDS
        stable = 0
        dock_sent = False
        saw_returning = False
        last_tuple = None
        first_probe_at = time.monotonic()

        while time.monotonic() < deadline:
            if serial != self._v67_watch_serial or not self._auto_step2_pending:
                return
            if self.mapping_active:
                return
            if vacuum is not self.vacuum:
                return

            try:
                state = self._v67_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                charging = self._v67_int(state.get("charging_state"))
                battery = self._v67_int(state.get("battery"))
            except Exception as exc:
                self._post_ui("v67_transition_probe_error", serial, str(exc).strip() or type(exc).__name__)
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            if status == 3:
                saw_returning = True

            # Si el evento de fin llegó en espera/pausa, pedimos base una sola
            # vez. Damos ~1.5 s para no interferir con un retorno ya arrancando.
            if (
                not dock_sent
                and time.monotonic() - first_probe_at >= 1.5
                and self._v67_should_send_dock(status, charging)
            ):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui("v67_dock_error", serial, str(exc).strip() or type(exc).__name__)

            current = (status, charging, battery, dock_sent, saw_returning)
            if current != last_tuple:
                self._post_ui(
                    "v67_transition_sample",
                    serial,
                    status,
                    charging,
                    battery,
                    dock_sent,
                    saw_returning,
                )
                last_tuple = current

            at_base, reason = self._v67_base_evidence(status, charging)
            stable = stable + 1 if at_base else 0
            if stable >= self.BASE_CONFIRM_SAMPLES:
                self._post_ui(
                    "v67_base_confirmed",
                    serial,
                    status,
                    charging,
                    battery,
                    reason,
                    dock_sent,
                    saw_returning,
                )
                return

            time.sleep(self.BASE_POLL_SECONDS)

        self._post_ui("v67_transition_timeout", serial)

    def _v67_schedule_step2(self, serial):
        if serial != self._v67_watch_serial:
            return
        if not self._auto_step2_pending or self.mapping_active or not self.vacuum:
            return
        if self._v67_start_scheduled:
            return
        self._v67_start_scheduled = True
        self._v67_transition_diag["step2_scheduled"] = True
        self._set_banner("E10 confirmado en la base · Paso 2 automático en unos segundos…")
        self.after(
            self.STEP2_SETTLE_MS,
            lambda: self._v67_recheck_base_before_step2(serial),
        )

    def _v67_recheck_base_before_step2(self, serial):
        if serial != self._v67_watch_serial:
            return
        self._v67_start_scheduled = False
        if not self._auto_step2_pending or self.mapping_active or not self.vacuum:
            return

        vacuum = self.vacuum

        def worker():
            try:
                state = self._v67_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                charging = self._v67_int(state.get("charging_state"))
                battery = self._v67_int(state.get("battery"))
                at_base, reason = self._v67_base_evidence(status, charging)
                if not at_base:
                    self._post_ui(
                        "v67_base_lost",
                        serial,
                        status,
                        charging,
                        battery,
                    )
                    return
                self._post_ui(
                    "v67_start_step2",
                    serial,
                    status,
                    charging,
                    battery,
                    reason,
                )
            except Exception as exc:
                self._post_ui("v67_transition_probe_error", serial, str(exc).strip() or type(exc).__name__)

        threading.Thread(target=worker, daemon=True).start()

    def _v67_commit_step2_start(self, serial, status, charging, battery, reason):
        """Commit UI one-shot; separado para poder probarlo sin Tk real."""
        if serial != self._v67_watch_serial:
            return False
        if not self._auto_step2_pending or self.mapping_active or not self.vacuum:
            return False

        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._v67_watch_running = False
        self._v67_start_scheduled = False
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = True
        self.mapping_step2_complete = False

        diag = dict(self._v67_transition_diag or {})
        diag.update({
            "pending": False,
            "base_confirmed": True,
            "base_confirmed_by": reason,
            "last_status": status,
            "last_charging_state": charging,
            "last_battery": battery,
            "step2_started": True,
        })
        self._v67_transition_diag = diag

        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 2 · base confirmada. Saliendo para completar el interior…")
        self._v67_launch_interior_worker(self.vacuum)
        return True

    def _v67_launch_interior_worker(self, vacuum):
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

    # ------------------------------------------------------------- eventos
    def _handle_ui_event(self, kind, payload):
        if kind in ("edge_only_complete", "perimeter_complete"):
            was_step1 = bool(self._v67_step1_session_active) or (
                bool(getattr(self, "mapping_active", False))
                and int(getattr(self, "mapping_phase", 0) or 0) == 1
            )
            result = super()._handle_ui_event(kind, payload)
            if was_step1:
                self._v67_arm_transition(kind)
            return result

        if kind in ("edge_only_error", "mapping_error", "unstick_abort"):
            self._v67_step1_session_active = False
            self._v67_watch_serial += 1
            self._v67_watch_running = False
            self._v67_start_scheduled = False
            return super()._handle_ui_event(kind, payload)

        if kind == "v67_transition_sample":
            serial, status, charging, battery, dock_sent, saw_returning = payload
            if int(serial) != self._v67_watch_serial:
                return
            diag = dict(self._v67_transition_diag or {})
            diag.update({
                "last_status": status,
                "last_charging_state": charging,
                "last_battery": battery,
                "dock_sent": bool(dock_sent),
                "saw_returning": bool(saw_returning),
                "samples": int(diag.get("samples", 0) or 0) + 1,
            })
            self._v67_transition_diag = diag
            if status == 3:
                self._set_banner("Paso 1 terminado · E10 volviendo a la base. Paso 2 sigue armado…")
            return

        if kind == "v67_base_confirmed":
            serial, status, charging, battery, reason, dock_sent, saw_returning = payload
            if int(serial) != self._v67_watch_serial:
                return
            diag = dict(self._v67_transition_diag or {})
            diag.update({
                "last_status": status,
                "last_charging_state": charging,
                "last_battery": battery,
                "dock_sent": bool(dock_sent),
                "saw_returning": bool(saw_returning),
                "base_confirmed": True,
                "base_confirmed_by": str(reason),
            })
            self._v67_transition_diag = diag
            self._v67_schedule_step2(int(serial))
            return

        if kind == "v67_start_step2":
            serial, status, charging, battery, reason = payload
            self._v67_commit_step2_start(
                int(serial), status, charging, battery, str(reason)
            )
            return

        if kind == "v67_base_lost":
            serial, status, charging, battery = payload
            if int(serial) != self._v67_watch_serial:
                return
            self._v67_transition_diag.update({
                "last_status": status,
                "last_charging_state": charging,
                "last_battery": battery,
                "base_confirmed": False,
                "base_confirmed_by": None,
                "step2_scheduled": False,
            })
            if self._auto_step2_pending and not self.mapping_active and self.vacuum:
                self._v67_watch_running = True
                threading.Thread(
                    target=self._v67_watch_base_worker,
                    args=(self.vacuum, int(serial)),
                    daemon=True,
                ).start()
            return

        if kind == "v67_transition_probe_error":
            serial, message = payload
            if int(serial) == self._v67_watch_serial:
                self._v67_transition_diag["last_probe_error"] = str(message)
            return

        if kind == "v67_dock_error":
            serial, message = payload
            if int(serial) == self._v67_watch_serial:
                self._v67_transition_diag["dock_error"] = str(message)
            return

        if kind == "v67_transition_timeout":
            serial = int(payload[0])
            if serial != self._v67_watch_serial:
                return
            self._v67_watch_running = False
            self._v67_transition_diag["timeout"] = True
            self._set_banner(
                "Paso 1 terminó, pero no pude confirmar que el E10 esté acoplado. "
                "Paso 2 no se inició por seguridad."
            )
            return

        result = super()._handle_ui_event(kind, payload)
        return result

    # ---------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        diag = dict(getattr(self, "_v67_transition_diag", {}) or {})
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V67 ACTIVO · transición automática Paso 1 → base → Paso 2",
            "=======================================================================",
            f"evento fin Paso 1: {diag.get('completion_event') or '—'}",
            f"pendiente Paso 2: {bool(getattr(self, '_auto_step2_pending', False))} · watchdog={bool(getattr(self, '_v67_watch_running', False))}",
            f"watch serial: {diag.get('watch_serial', 0)} · muestras/cambios: {diag.get('samples', 0)}",
            f"último status 2/1: {diag.get('last_status')!r} · charging-state 3/2: {diag.get('last_charging_state')!r} · batería: {diag.get('last_battery')!r}",
            f"vio retorno status=3: {bool(diag.get('saw_returning'))} · dock enviado: {bool(diag.get('dock_sent'))}",
            f"base confirmada: {bool(diag.get('base_confirmed'))} · por={diag.get('base_confirmed_by') or '—'}",
            f"Paso 2 programado: {bool(diag.get('step2_scheduled'))} · iniciado: {bool(diag.get('step2_started'))}",
            f"timeout: {bool(diag.get('timeout'))} · probe_error={diag.get('last_probe_error') or '—'} · dock_error={diag.get('dock_error') or '—'}",
            "regla V67: cualquier cierre válido de Paso 1 arma el watchdog, incluso si vino por perimeter_complete heredado",
            "regla V67: Paso 2 sólo arranca tras 2 confirmaciones de status=4 o charging-state=1 y una revalidación final",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

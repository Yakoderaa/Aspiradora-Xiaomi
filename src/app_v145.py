import threading
import time

import app_v144
import app_v9


class App(app_v144.App):
    """V145-IA: cerrojo de sesión + reset/dock robusto contra workers tardíos."""

    RESET_DOCK_TIMEOUT = 75.0

    def __init__(self):
        self._v145_session_latched = True
        self._v145_latch_reason = "startup"
        self._v145_active_serial = None
        self._v145_reset_guard = False
        self._v145_blocked_edge_starts = 0
        self._v145_blocked_phase2_starts = 0
        self._v145_blocked_late_events = 0
        self._v145_counter_returns = 0
        self._v145_last_block = {}
        self._v145_last_dock_probe = {}
        super().__init__()

    # ===================================================== cerrojo de sesión
    def _v145_latch_session(self, reason, close_mapping=False):
        self._v145_session_latched = True
        self._v145_latch_reason = str(reason)
        self._v121_phase2_requested = True
        self._v121_stage = "closed-v145"
        self._v137_manual_cancel = True
        self._v136_manual_abort = True
        self._v74_watch_active = False
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self.mapping_transitioning = False
        if close_mapping:
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
        return True

    def start_new_mapping(self):
        # Éste es el único punto que vuelve a abrir el cerrojo. Cualquier
        # worker heredado que aparezca sin este gesto explícito queda bloqueado.
        if not getattr(self, "vacuum", None):
            return super().start_new_mapping()
        if bool(getattr(self, "mapping_active", False)):
            return super().start_new_mapping()

        self._v145_session_latched = False
        self._v145_latch_reason = "explicit-map-request"
        self._v145_active_serial = None
        self._v145_last_block = {}
        result = super().start_new_mapping()

        if (
            bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
        ):
            self._v145_active_serial = int(
                getattr(self, "_v74_mapping_serial", -1)
            )
            self._v145_latch_reason = None
            self._v141_log(
                "V145 abrió sesión por Mapear vivienda",
                serial=self._v145_active_serial,
            )
        else:
            self._v145_session_latched = True
            self._v145_latch_reason = "explicit-map-not-started"
        return result

    # ====================================== bloqueo del comando físico EDGE
    def _v138_start_factory_edge(self, vacuum, label):
        blocked = bool(
            self._v145_session_latched
            or self._v145_reset_guard
            or not bool(getattr(self, "mapping_active", False))
            or int(getattr(self, "mapping_phase", 0) or 0) != 1
        )
        if blocked:
            self._v145_blocked_edge_starts += 1
            self._v145_last_block = {
                "kind": "EDGE",
                "label": str(label),
                "latched": bool(self._v145_session_latched),
                "reason": self._v145_latch_reason,
                "reset_guard": bool(self._v145_reset_guard),
                "mapping_active": bool(getattr(self, "mapping_active", False)),
                "phase": int(getattr(self, "mapping_phase", 0) or 0),
            }
            self._v141_log(
                "V145 bloqueó arranque EDGE tardío",
                **self._v145_last_block,
            )
            return {
                "route": "V145 BLOCKED EDGE",
                "label": str(label),
                "status_before": None,
                "sweep_before": None,
                "sweep_after_set": None,
                "response": None,
                "status_after": None,
                "sweep_after": None,
                "success": False,
                "movement_commands": 0,
                "room_clean_7_3_sent": False,
                "start_only_2_3_sent": False,
                "error": "sesión cerrada por V145",
            }
        return super()._v138_start_factory_edge(vacuum, label)

    # =============================================== bloqueo de Paso 2 tardío
    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        if self._v145_session_latched or self._v145_reset_guard:
            self._v145_blocked_phase2_starts += 1
            self._v145_last_block = {
                "kind": "Paso2",
                "serial": int(serial),
                "source": str(source),
                "latched": bool(self._v145_session_latched),
                "reason": self._v145_latch_reason,
                "reset_guard": bool(self._v145_reset_guard),
            }
            self._v141_log(
                "V145 bloqueó Paso2 tardío",
                **self._v145_last_block,
            )
            return False
        return super()._v121_request_phase2(
            vacuum,
            serial,
            source,
            sweep_type,
        )

    # ===================================== auto-abort V144 ahora cierra latch
    def _v144_execute_auto_abort(self, serial, metrics):
        if (
            serial == int(getattr(self, "_v74_mapping_serial", -1))
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
        ):
            self._v145_latch_session("ai_auto_abort", close_mapping=False)
        result = super()._v144_execute_auto_abort(serial, metrics)
        if self._v144_auto_abort_done:
            self._v145_latch_session("ai_auto_abort", close_mapping=True)
        return result

    def dock(self):
        if (
            bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
        ):
            self._v145_latch_session("manual_return", close_mapping=False)
        return super().dock()

    # ======================================================== reset robusto
    def _v138_wait_for_dock(self, vacuum, timeout=None):
        timeout = self.RESET_DOCK_TIMEOUT if timeout is None else max(
            self.RESET_DOCK_TIMEOUT,
            float(timeout),
        )
        deadline = time.monotonic() + max(5.0, timeout)
        dock_sent = False
        stop_sent = False
        last_status = None
        samples = 0

        while time.monotonic() < deadline:
            prop_status = None
            object_status = None
            try:
                prop_status = self._v138_int(vacuum._value(2, 1))
            except Exception:
                prop_status = None
            try:
                status_obj = vacuum.status()
                object_status = self._v138_int(
                    getattr(status_obj, "status", None)
                )
            except Exception:
                object_status = None

            samples += 1
            statuses = [
                value
                for value in (prop_status, object_status)
                if value is not None
            ]
            if statuses:
                last_status = statuses[-1]

            self._v145_last_dock_probe = {
                "samples": samples,
                "prop_status": prop_status,
                "object_status": object_status,
                "dock_sent": dock_sent,
                "stop_sent": stop_sent,
            }

            if 4 in statuses:
                self._v145_last_dock_probe["confirmed"] = True
                return True, 4

            # V138 sólo mandaba dock para 0/1/2/3. Si el firmware quedó
            # reportando 5/6/7, podía esperar hasta fallar aun estando en una
            # transición real. V145 corta primero la tarea y luego pide dock.
            if (
                not stop_sent
                and any(value in (5, 6, 7) for value in statuses)
            ):
                try:
                    vacuum.stop()
                    stop_sent = True
                except Exception:
                    pass
                time.sleep(0.65)

            if not dock_sent and statuses:
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception:
                    pass

            time.sleep(0.65)

        self._v145_last_dock_probe["confirmed"] = False
        return False, last_status

    def _v140_confirm_reset(self):
        result = super()._v140_confirm_reset()
        if result:
            self._v145_reset_guard = True
            self._v145_latch_session("deep_reset", close_mapping=True)
            self._v142_mapping_token += 1
            try:
                self._sync_mapping_step_buttons()
            except Exception:
                pass
            self._v141_log(
                "V145 cerró sesión antes de reset profundo",
                success=True,
            )
        return result

    def _v140_reset_worker(self, vacuum):
        self._v145_reset_guard = True
        self._v145_latch_session("deep_reset", close_mapping=True)
        self._v142_mapping_token += 1
        try:
            return super()._v140_reset_worker(vacuum)
        finally:
            # El cerrojo de sesión sigue cerrado. Sólo liberamos el guard
            # temporal del reset; Mapear vivienda es lo único que abre sesión.
            self._v145_reset_guard = False

    # ======================================== eventos tardíos: contramedida
    def _v145_counter_return(self, reason):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False

        def worker():
            ok = False
            error = None
            try:
                vacuum.dock()
                ok = True
            except Exception as exc:
                error = str(exc).strip() or type(exc).__name__
            self._v141_log(
                "V145 contrarregreso por evento tardío",
                success=ok,
                reason=str(reason),
                error=error,
            )

        self._v145_counter_returns += 1
        threading.Thread(
            target=worker,
            name="AspiradoraV145LateStartCounterReturn",
            daemon=True,
        ).start()
        return True

    def _handle_ui_event(self, kind, payload):
        if kind in ("v74_mapping_started", "v121_phase2_started"):
            serial = int(payload[0]) if payload else -1
            current = int(getattr(self, "_v74_mapping_serial", -1))
            blocked = bool(
                self._v145_session_latched
                or self._v145_reset_guard
                or serial != current
            )
            if blocked:
                self._v145_blocked_late_events += 1
                self._v145_last_block = {
                    "kind": kind,
                    "serial": serial,
                    "current_serial": current,
                    "latched": bool(self._v145_session_latched),
                    "reason": self._v145_latch_reason,
                    "reset_guard": bool(self._v145_reset_guard),
                }
                self._v145_latch_session(
                    "late-event:" + kind,
                    close_mapping=True,
                )
                self._v141_log(
                    "V145 descartó evento de arranque tardío",
                    **self._v145_last_block,
                )
                self._set_banner(
                    "V145 bloqueó un arranque tardío · "
                    "regresando a base · proceso finalizó."
                )
                self._v145_counter_return(kind)
                return None

        if kind in ("v140_reset_done", "v140_reset_error"):
            self._v145_latch_session(
                "reset_done" if kind == "v140_reset_done" else "reset_error",
                close_mapping=True,
            )
            self._v145_reset_guard = False
            try:
                self._sync_mapping_step_buttons()
            except Exception:
                pass

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V145-IA ACTIVO · cerrojo de sesión + reset robusto",
            "================================================================",
            f"sesión cerrada={self._v145_session_latched}",
            f"motivo cerrojo={self._v145_latch_reason or '—'}",
            f"serial V145={self._v145_active_serial}",
            f"reset guard={self._v145_reset_guard}",
            f"EDGE tardíos bloqueados={self._v145_blocked_edge_starts}",
            f"Paso2 tardíos bloqueados={self._v145_blocked_phase2_starts}",
            f"eventos tardíos bloqueados={self._v145_blocked_late_events}",
            f"contrarregresos={self._v145_counter_returns}",
            f"último bloqueo={self._v145_last_block or '—'}",
            f"última sonda dock/reset={self._v145_last_dock_probe or '—'}",
            "regla V145: una sesión cerrada no puede volver a mandar EDGE",
            "regla V145: una sesión cerrada no puede iniciar Paso2",
            "regla V145: un evento de arranque tardío se descarta y provoca retorno a base",
            "regla V145: sólo Mapear vivienda explícito vuelve a abrir el cerrojo",
            "reset V145: compara 2/1 + vacuum.status(), corta tarea activa y pide dock antes de fallar",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

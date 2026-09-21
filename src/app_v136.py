import threading
import time
from tkinter import messagebox

import app_v135
import app_v9


class App(app_v135.App):
    """V136: restaura el flujo completo V64/V68 -> V67, no sólo el comando."""

    def __init__(self):
        self._v136_edge_start_diag = {}
        self._v136_manual_abort = False
        self._v136_edge_complete_events = 0
        self._v136_phase2_transitions = 0
        self._v136_phase2_started_events = 0
        self._v136_flow = "idle"
        super().__init__()

    @staticmethod
    def _v136_new_v68_diag(session):
        return {
            "watch_started": False,
            "session": int(session),
            "samples": 0,
            "seen_moving": False,
            "seen_edge_type": False,
            "departed_base": False,
            "initial_base": None,
            "last_status": None,
            "last_sweep_type": None,
            "last_charging_state": None,
            "completion_reason": None,
            "timeout": False,
            "errors": 0,
        }

    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Primero detené el mapeo actual.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda",
            "V136 restaura el flujo que funcionaba: bordes primero y zonas después.\n\n"
            "Paso 1 usa la ruta EDGE V64/V68 completa y su watcher original. "
            "Si el firmware intenta abandonar EDGE, el watcher lo bloquea.\n\n"
            "Al terminar naturalmente el perímetro, el E10 vuelve a la base; "
            "V67 confirma el acople y recién entonces inicia el Paso 2 interior.",
            parent=self,
        )
        if not ok:
            return

        self._v136_manual_abort = False
        self._v136_edge_complete_events = 0
        self._v136_phase2_transitions = 0
        self._v136_phase2_started_events = 0
        self._v136_flow = "edge"

        self._v121_stage = "edge"
        self._v121_phase2_requested = False
        self._v121_phase2_started = False
        self._v121_phase2_departed = False
        self._v121_phase2_attempts = 0
        self._v121_phase2_errors = 0
        self._v121_edge_dock_suppressed_closes = 0
        self._v121_final_reads_suppressed = 0
        self._v121_invalid_final_grids_rejected = 0
        self._v121_phase2_diag = {}

        self._v74_reset_session()
        self._v73_session_phase = 1

        # Sesión EDGE exacta de V68.
        self._edge_session = int(getattr(self, "_edge_session", 0) or 0) + 1
        edge_session = self._edge_session
        self._v68_edge_diag = self._v136_new_v68_diag(edge_session)
        self._v67_step1_session_active = True
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False

        self._v131_capture_prestart_pose()

        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(
                before,
                "10/24 antes de EDGE V136; V130 corrige al dock 10/22",
            )

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
        self._set_banner(
            "Mapeando · Paso 1/2: iniciando aspirado por bordes V64/V68…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            diag = {
                "route": "V64/V68 exacto: arm_new_map(1) -> ECO -> repeat=0 -> sweep_type=2 -> 7/3 EDGE",
                "response": None,
                "build": None,
                "status_after": None,
                "sweep_type_after": None,
                "success": False,
                "error": None,
            }
            try:
                # IMPORTANTE: usamos el método histórico completo del
                # controlador XiaomiE10Edge. No reconstruimos sus pasos aquí.
                response = vacuum.start_mapping_perimeter()
                diag["response"] = repr(response)[:500]
                diag["build"] = dict(
                    getattr(vacuum, "last_map_build_diag", {}) or {}
                )

                deadline = time.monotonic() + 5.0
                while True:
                    try:
                        state = vacuum._get_many([
                            ("status", 2, 1),
                            ("sweep_type", 2, 8),
                        ])
                        status = self._v67_int(state.get("status"))
                        sweep = self._v67_int(state.get("sweep_type"))
                        diag["status_after"] = status
                        diag["sweep_type_after"] = sweep
                        if status in (5, 6, 7):
                            diag["success"] = True
                            break
                    except Exception as exc:
                        diag["readback_error"] = (
                            str(exc).strip() or type(exc).__name__
                        )

                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.30)

                if not diag["success"]:
                    raise RuntimeError(
                        "V136: la ruta EDGE V64/V68 no confirmó salida física "
                        f"(status={diag.get('status_after')!r}, "
                        f"sweep_type={diag.get('sweep_type_after')!r})."
                    )

                self._v136_edge_start_diag = dict(diag)
                self._v120_last_start_diag = {
                    "build": dict(diag.get("build") or {}),
                    "exploration": dict(diag),
                }
                self._post_ui(
                    "v136_edge_started",
                    serial,
                    edge_session,
                    diag,
                )
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v136_edge_start_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._post_ui(
                    "v136_edge_start_error",
                    serial,
                    diag["error"],
                )

        threading.Thread(
            target=worker,
            name="AspiradoraEdgeV64V68V136",
            daemon=True,
        ).start()

    def dock(self):
        if (
            bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
            and str(getattr(self, "_v121_stage", "")) == "edge"
        ):
            self._v136_manual_abort = True
            self._v136_flow = "manual_return"
            self._set_banner(
                "Paso 1 cancelado manualmente · volviendo a la base. "
                "Paso 2 queda cancelado."
            )
        return super().dock()

    def _v67_commit_step2_start(
        self,
        serial,
        status,
        charging,
        battery,
        reason,
    ):
        # V67 exacto sigue haciendo el commit y V71/V73 conservan sus
        # protecciones. Mantenemos stage=transition hasta que la orden interior
        # haya sido emitida, evitando que el status=4 intermedio cierre el mapa.
        started = super()._v67_commit_step2_start(
            serial,
            status,
            charging,
            battery,
            reason,
        )
        if started:
            self._v136_phase2_transitions += 1
            self._v136_flow = "phase2_starting"
            self._v121_stage = "transition"
            self._v121_phase2_requested = True
            self.mapping_transitioning = True
        return started

    def _v136_activate_phase2_ui(self):
        self._v136_phase2_started_events += 1
        self._v136_flow = "global"
        self._v121_stage = "global"
        self._v121_phase2_started = True
        self._v121_phase2_departed = False
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False
        self._v73_session_phase = 2

        # El dock recién confirmado era intermedio. Liberamos latches para que
        # el próximo status=4 sea el final de la Fase 2.
        self._v84_dock_latched = False
        self._v84_returning = False
        self._v81_dock_confirmed = False
        self._v81_dock_timeout = False
        self._v73_dock_failed = False

        self._v74_started_at = time.monotonic()
        self._v74_last_discovery_at = self._v74_started_at
        self._v74_coverage_cells = set()
        self._v74_finish_requested = False
        self._v74_finish_reason = None
        self._v74_return_samples = 0

        try:
            self._v95_reset_watchdog_for_mapping()
            self.map_polling = True
            self.after(0, self._poll_local_map)
        except Exception:
            pass

        self._sync_mapping_step_buttons()
        self._set_banner(
            "Mapeando · Paso 2/2: aspirando todas las zonas/interior. "
            "El perímetro ya terminó."
        )

    def _handle_ui_event(self, kind, payload):
        if kind == "v136_edge_started":
            serial = int(payload[0])
            edge_session = int(payload[1])
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._v74_started_at = time.monotonic()
            self._v74_last_discovery_at = self._v74_started_at
            self._v74_watch_active = True
            self._v136_flow = "edge"

            try:
                self._v95_reset_watchdog_for_mapping()
                self.map_polling = True
                self.after(0, self._poll_local_map)
            except Exception:
                pass

            self._set_banner(
                "Mapeando · Paso 1/2: aspirado por bordes activo. "
                "Watcher V68 protege EDGE; no se permite convertirlo en global."
            )
            threading.Thread(
                target=self._watch_edge_only,
                args=(edge_session,),
                name="AspiradoraEdgeWatchV68V136",
                daemon=True,
            ).start()
            return None

        if kind == "v136_edge_start_error":
            serial, message = payload
            if int(serial) != int(getattr(self, "_v74_mapping_serial", -1)):
                return None
            self._v136_flow = "error"
            self._v74_watch_active = False
            self._v67_step1_session_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "Paso 1 no pudo iniciar · proceso finalizó con error."
            )
            messagebox.showerror("Mapeo", str(message), parent=self)
            return None

        if kind in ("edge_only_complete", "perimeter_complete"):
            self._v136_edge_complete_events += 1
            self._v74_watch_active = False
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_step1_complete = True
            self.mapping_transitioning = True
            self._v121_stage = "transition"

            if self._v136_manual_abort:
                self._v136_flow = "manual_abort"
                self.mapping_transitioning = False
                self._v67_step1_session_active = False
                self._auto_step2_pending = False
                self._auto_step2_scheduled = False
                self._sync_mapping_step_buttons()
                self._set_banner(
                    "Paso 1 cancelado manualmente · proceso finalizó. "
                    "No se inicia el Paso 2."
                )
                return None

            armed = self._v67_arm_transition(kind)
            if armed:
                self._v136_flow = "waiting_base"
                self._set_banner(
                    "Paso 1/2 finalizado · bordes completos. "
                    "Volviendo/confirmando base antes de aspirar todas las zonas."
                )
            return None

        if kind == "edge_only_error":
            self._v136_flow = "error"
            self._v74_watch_active = False
            self._v67_step1_session_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "Paso 1 detenido · proceso finalizó sin habilitar Paso 2. "
                + (str(payload[0]) if payload else "")
            )
            return None

        if kind == "auto_step2_started":
            self._v136_activate_phase2_ui()
            return None

        if kind == "auto_step2_error":
            self._v136_flow = "phase2_error"
            self._v121_stage = "error"
            return super()._handle_ui_event(kind, payload)

        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        edge = dict(getattr(self, "_v68_edge_diag", {}) or {})
        transition = dict(getattr(self, "_v67_transition_diag", {}) or {})
        lines = [
            "DIAGNÓSTICO V136 ACTIVO · flujo V68/V67 restaurado",
            "====================================================",
            f"flujo actual={self._v136_flow}",
            f"START EDGE={self._v136_edge_start_diag or '—'}",
            f"watch V68={edge or '—'}",
            f"transición V67={transition or '—'}",
            (
                "eventos: fin EDGE="
                f"{self._v136_edge_complete_events} · transiciones Paso2="
                f"{self._v136_phase2_transitions} · START Paso2="
                f"{self._v136_phase2_started_events}"
            ),
            f"cancelación manual={self._v136_manual_abort}",
            "ruta Paso1 V136: XiaomiE10Edge.start_mapping_perimeter() exacto de V64",
            "protección Paso1 V136: _watch_edge_only() exacto de V68; si EDGE cambia a global, STOP antes de continuar",
            "transición V136: _v67_arm_transition() -> base confirmada -> start_mapping_interior()",
            "ruta Paso2 V136: flujo interior antiguo; NO usa start_mapping_whole_home V123",
            "regla V136: Volver a base durante Paso1 cancela la transición automática a Paso2",
            "regla V136: conserva pose V131, geometría/mapa moderno y reacople progresivo V133",
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

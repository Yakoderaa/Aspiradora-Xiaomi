import threading
import time
from tkinter import messagebox

import app_v150
import app_v9


class App(app_v150.App):
    """V151-IA: mapeo whole-home directo; EDGE queda fuera del camino automático."""

    DIRECT_GLOBAL_CONFIRM_TIMEOUT = 14.0

    def __init__(self):
        self._v151_direct_global_owner = False
        self._v151_direct_global_diag = {}
        self._v151_edge_blocks = 0
        self._v151_escape_blocks = 0
        self._v151_abort_blocks = 0
        self._v151_late_control_blocks = 0
        super().__init__()

    def _v151_reset_direct_state(self):
        self._v151_direct_global_owner = False
        self._v151_direct_global_diag = {}
        self._v151_edge_blocks = 0
        self._v151_escape_blocks = 0
        self._v151_abort_blocks = 0
        self._v151_late_control_blocks = 0

    def _v151_owner_active(self):
        return bool(
            self._v151_direct_global_owner
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 2
            and str(getattr(self, "_v121_stage", "")) in (
                "global-v151",
                "global",
            )
            and not bool(getattr(self, "_v145_session_latched", False))
            and not bool(getattr(self, "_v145_reset_guard", False))
        )

    # ==================================================== arranque directo
    def start_new_mapping(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
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
            "V151 inicia el mapa en modo whole-home desde el principio.\n\n"
            "No usa EDGE/perímetro automático, porque en este E10 ese modo "
            "queda repitiendo el sector entre la cama y la pared.\n\n"
            "Se crea un único build-map Xiaomi y luego se inicia whole-home "
            "V123. No hay escapes EDGE ni un segundo build-map.\n\n"
            "Dejá abiertas las puertas que quieras incluir y empezá con el "
            "robot en la base.",
            parent=self,
        )
        if not ok:
            return

        self._v151_reset_direct_state()

        # Este método reemplaza el wrapper V145, así que abrimos explícitamente
        # el único cerrojo autorizado por el gesto Mapear vivienda.
        self._v145_session_latched = False
        self._v145_latch_reason = "explicit-map-request-v151"
        self._v145_active_serial = None
        self._v145_last_block = {}

        # Limpiar estado final/diagnóstico de sesiones anteriores.
        self._v93_finalizing = False
        self._v93_finalized_serial = None
        self._v93_final_read_success = 0
        self._v93_final_read_errors = []

        self._v141_log("V151 Mapear vivienda confirmado · whole-home directo")
        self._v141_edge_diag = {}
        self._v139_edge_diag = {}
        self._v138_factory_edge_diag = {}

        self._v138_phase1_retry_count = 0
        self._v138_phase1_retry_running = False
        self._v138_phase1_progress = self._v138_new_progress(1)
        self._v138_phase2_progress = self._v138_new_progress(2)

        self._v137_phase1_diag = {
            "route": "V151: Paso EDGE omitido deliberadamente",
            "success": True,
            "skipped": True,
        }
        self._v137_phase2_diag = {}
        self._v137_phase1_starts = 0
        self._v137_phase2_starts = 1
        self._v137_manual_cancel = False
        self._v136_manual_abort = False
        self._v137_flow = "global-v151"

        self._v121_stage = "global-v151"
        self._v121_phase2_requested = True
        self._v121_phase2_started = False
        self._v121_phase2_departed = False
        self._v121_phase2_attempts = 1
        self._v121_phase2_errors = 0
        self._v121_edge_dock_suppressed_closes = 0
        self._v121_final_reads_suppressed = 0
        self._v121_invalid_final_grids_rejected = 0
        self._v121_phase2_diag = {}

        self._v74_reset_session()
        self._v73_session_phase = 2

        try:
            self._v131_capture_prestart_pose()
        except Exception:
            pass

        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(
                before,
                "10/24 antes de whole-home directo V151",
            )

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False

        # Desde este punto ningún controlador EDGE/escape/auto-abort heredado
        # tiene autoridad sobre ruedas durante la sesión whole-home.
        self._v151_direct_global_owner = True

        serial = int(self._v74_mapping_serial)
        self._v145_active_serial = serial
        self._v145_latch_reason = None

        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner(
            "V151 · iniciando whole-home directo · sin EDGE/perímetro previo…"
        )

        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            diag = {
                "route": (
                    "V151 directo: arm_new_map(1) -> "
                    "whole-home V123 7/3 ['',0,1] "
                    "-> 2/3 sólo si sigue físicamente en dock"
                ),
                "build": None,
                "whole_home": None,
                "arm_new_map_calls": 1,
                "edge_calls": 0,
                "escape_calls": 0,
                "success": False,
                "status_after": None,
                "sweep_type_after": None,
                "error": None,
            }
            try:
                if not self._v151_owner_active():
                    raise RuntimeError(
                        "sesión V151 dejó de ser válida antes de build-map"
                    )

                build_diag = vacuum.arm_new_map(1)
                diag["build"] = dict(build_diag or {})
                if not bool((build_diag or {}).get("success", True)):
                    raise RuntimeError("build-map Xiaomi no fue aceptado")

                if not self._v151_owner_active():
                    raise RuntimeError(
                        "sesión V151 cancelada después de build-map"
                    )

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                response = vacuum.start_mapping_whole_home(
                    confirm_timeout=self.DIRECT_GLOBAL_CONFIRM_TIMEOUT
                )
                native = dict(
                    getattr(
                        vacuum,
                        "_last_mapping_whole_home_diag",
                        {},
                    )
                    or {}
                )
                status_after = self._v67_int(native.get("status_after"))
                sweep_after = self._v67_int(
                    native.get("sweep_type_after")
                )
                success = bool(
                    native.get("success")
                    and status_after in (5, 6, 7)
                )
                diag.update({
                    "whole_home": native,
                    "response": repr(response)[:500],
                    "status_after": status_after,
                    "sweep_type_after": sweep_after,
                    "success": success,
                })
                self._v151_direct_global_diag = dict(diag)

                # Readback tardío nunca puede revivir una sesión cancelada.
                if not self._v151_owner_active():
                    raise RuntimeError(
                        "whole-home respondió después de cancelar la sesión"
                    )
                if not success:
                    raise RuntimeError(
                        native.get("error")
                        or (
                            "whole-home V151 no confirmó movimiento físico "
                            f"(status={status_after!r})"
                        )
                    )

                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": native,
                    "reset": "NO",
                    "route": "V151 whole-home directo",
                }
                self._v137_phase2_diag = dict(diag)
                self._v121_phase2_diag = dict(diag)
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                diag["success"] = False
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v151_direct_global_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._post_ui(
                    "v151_direct_global_error",
                    serial,
                    dict(diag),
                )

        threading.Thread(
            target=worker,
            name="AspiradoraV151DirectWholeHome",
            daemon=True,
        ).start()

    # =============================================== autoridad exclusiva
    def _v138_start_factory_edge(self, vacuum, label):
        if self._v151_owner_active():
            self._v151_edge_blocks += 1
            self._v141_log(
                "V151 bloqueó EDGE durante whole-home directo",
                label=str(label),
            )
            return {
                "route": "V151 BLOCKED EDGE",
                "label": str(label),
                "success": False,
                "movement_commands": 0,
                "error": "whole-home V151 es dueño exclusivo de la sesión",
            }
        return super()._v138_start_factory_edge(vacuum, label)

    def _v147_schedule_escape(self, serial, metrics):
        if self._v151_owner_active():
            self._v151_escape_blocks += 1
            self._v141_log(
                "V151 bloqueó escape EDGE durante whole-home",
                serial=int(serial),
            )
            return False
        return super()._v147_schedule_escape(serial, metrics)

    def _v147_request_abort(self, serial, metrics, reason):
        if self._v151_owner_active():
            self._v151_abort_blocks += 1
            self._v141_log(
                "V151 bloqueó auto-abort heredado durante whole-home",
                serial=int(serial),
                reason=str(reason),
            )
            return None
        return super()._v147_request_abort(serial, metrics, reason)

    def _v144_execute_auto_abort(self, serial, metrics):
        if self._v151_owner_active():
            self._v151_abort_blocks += 1
            self._v144_auto_abort_requested = False
            self._v141_log(
                "V151 ignoró evento auto-abort tardío durante whole-home",
                serial=int(serial),
            )
            return False
        return super()._v144_execute_auto_abort(serial, metrics)

    def _v149_request_global_transition(self, serial, metrics, reason):
        if self._v151_owner_active():
            self._v151_late_control_blocks += 1
            return True
        return super()._v149_request_global_transition(
            serial,
            metrics,
            reason,
        )

    # ============================================================ manual
    def dock(self):
        if self._v151_owner_active():
            self._v151_direct_global_owner = False
            self._v137_flow = "manual_return-v151"
            self._v141_log(
                "V151 cedió control por Volver a base manual",
                serial=int(getattr(self, "_v74_mapping_serial", -1)),
            )
        return super().dock()

    # ============================================================ eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v151_direct_global_error":
            serial = int(payload[0]) if payload else -1
            diag = dict(payload[1] or {}) if len(payload) > 1 else {}
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._v151_direct_global_owner = False
            self._v121_phase2_errors += 1
            self._v121_stage = "error-v151"
            self._v137_flow = "error-v151"
            self._v74_watch_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
            self._v145_latch_session(
                "v151-direct-global-start-error",
                close_mapping=True,
            )
            self._sync_mapping_step_buttons()
            self._set_banner(
                "V151 no pudo confirmar whole-home · sesión cerrada de forma "
                "segura. No se inició EDGE como fallback."
            )
            return None

        if kind == "v74_mapping_started":
            # Dejamos que toda la cadena V74/V90/V95/V142 active sus watchers,
            # START gate, mapa LAN y diagnóstico. V121 heredado marca EDGE en
            # su paso; al volver de super restauramos inmediatamente el estado
            # real V151: global/phase2. No se envía ningún comando físico aquí.
            result = super()._handle_ui_event(kind, payload)
            serial = int(payload[0]) if payload else -1
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return result
            if not bool(getattr(self, "mapping_active", False)):
                return result

            self._v121_stage = "global-v151"
            self._v121_phase2_requested = True
            self._v121_phase2_started = True
            self._v121_phase2_departed = True
            self._v137_flow = "global-v151"
            self.mapping_phase = 2
            self.mapping_transitioning = False
            self.mapping_step1_complete = True
            self.mapping_step2_complete = False
            self._v73_session_phase = 2
            self._v151_direct_global_owner = True

            self._v84_dock_latched = False
            self._v84_returning = False
            self._v81_dock_confirmed = False
            self._v81_dock_timeout = False
            self._v73_dock_failed = False

            self._v74_started_at = time.monotonic()
            self._v74_last_discovery_at = self._v74_started_at
            self._v74_finish_requested = False
            self._v74_finish_reason = None
            self._v74_return_samples = 0

            self._set_banner(
                "V151 · whole-home confirmado · mapeando toda la vivienda "
                "sin EDGE ni escapes."
            )
            self._sync_mapping_step_buttons()
            return result

        if kind == "v107_final_grid_done":
            result = super()._handle_ui_event(kind, payload)
            if not bool(getattr(self, "mapping_active", False)):
                self._v151_direct_global_owner = False
            return result

        return super()._handle_ui_event(kind, payload)

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        label = getattr(self, "map_status_label", None)
        if (
            label is not None
            and self._v151_owner_active()
            and not bool(getattr(self, "_v93_finalizing", False))
        ):
            text = "Mapeando · whole-home directo V151 · sin EDGE"
            try:
                label.configure(text=text, fg="#16a34a")
                self._v93_last_status_text = text
            except Exception:
                pass
        return result

    # ======================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V151-IA ACTIVO · whole-home directo",
            "==================================================",
            f"dueño global activo={self._v151_direct_global_owner}",
            f"estado real stage={getattr(self, '_v121_stage', '—')} · phase={getattr(self, 'mapping_phase', '—')}",
            f"diag arranque={self._v151_direct_global_diag or '—'}",
            f"EDGE bloqueados={self._v151_edge_blocks}",
            f"escapes bloqueados={self._v151_escape_blocks}",
            f"auto-aborts bloqueados={self._v151_abort_blocks}",
            f"controles tardíos bloqueados={self._v151_late_control_blocks}",
            "regla V151: Mapear vivienda = un build-map + whole-home V123 directo",
            "regla V151: EDGE automático queda eliminado del mapeo de vivienda",
            "regla V151: no hay retroceso/giro/reinicio EDGE durante whole-home",
            "regla V151: V147/V148 pueden diagnosticar, pero no tienen autoridad de movimiento en global",
            "regla V151: auto-abort V144/V147 no puede cerrar una sesión whole-home activa",
            "regla V151: la única salida voluntaria durante global es Volver a base del usuario",
            "regla V151: una respuesta tardía nunca revive una sesión cancelada",
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

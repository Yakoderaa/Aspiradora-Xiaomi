import threading
import time
from tkinter import messagebox

import app_v151
import app_v9
from fresh_robot_core import FreshRobotCore
from robot_command_arbiter import RobotBusyError
from robot_plans import local_rect_to_device


class App(app_v151.App):
    """Fresh Core: conserva la app, reemplaza TODO control físico de limpieza/mapeo."""

    def __init__(self):
        self._fresh_core = None
        self._fresh_mapping_serial = None
        self._fresh_mapping_active = False
        self._fresh_last_event = {}
        self._fresh_target_context = None
        super().__init__()

    # ====================================================== instalación core
    def _install_fresh_core(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            self._fresh_core = None
            return None
        current = getattr(self, "_fresh_core", None)
        if current is not None and current.vacuum is vacuum:
            return current
        self._fresh_core = FreshRobotCore(vacuum, source="gui")
        self._v141_log("Fresh Core instalado · transporte heredado en sólo lectura")
        return self._fresh_core

    def _on_connected(self, ip):
        result = super()._on_connected(ip)
        try:
            self._install_fresh_core()
            self._set_banner(
                "Fresh Core activo · un único motor controla aspirado y mapeo."
            )
        except Exception as exc:
            self._set_banner(
                "Conectado, pero Fresh Core no pudo instalarse: "
                + (str(exc).strip() or type(exc).__name__)
            )
        return result

    def _fresh(self):
        core = self._install_fresh_core()
        if core is None:
            raise RuntimeError("Robot desconectado.")
        return core

    # ====================================================== limpieza global
    def start_clean(self):
        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá el mapeo antes de iniciar una limpieza normal.",
                parent=self,
            )
            return

        mode = {
            "Aspirar": 0,
            "Aspirar + trapear": 1,
            "Trapear": 2,
        }.get(self.mode_var.get(), 0)
        try:
            suction = int(self.suction_var.get())
        except Exception:
            suction = 1
        try:
            water = int(self.water_var.get())
        except Exception:
            water = 0

        self._set_banner(
            "Fresh Core · normalizando navegación y arrancando una única "
            "limpieza global estándar…"
        )

        def started(diag):
            self._post_ui("fresh_clean_started", dict(diag or {}))

        def finished(diag):
            self._post_ui("fresh_clean_finished", dict(diag or {}))

        try:
            self._fresh().start_global_async(
                mode=mode,
                suction=suction,
                water=water,
                mapping=False,
                on_started=started,
                on_finished=finished,
                purpose="whole_clean",
            )
        except Exception as exc:
            messagebox.showerror(
                "Limpieza",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    def stop_clean(self):
        try:
            core = self._fresh()
            self._set_banner("Fresh Core · solicitando STOP prioritario…")
            threading.Thread(
                target=lambda: self._fresh_stop_worker(core),
                name="FreshCoreStopUI",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror(
                "Detener limpieza",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    def _fresh_stop_worker(self, core):
        try:
            core.request_stop()
            self._post_ui("fresh_control_ok", "STOP enviado.")
        except Exception as exc:
            self._post_ui(
                "fresh_control_error",
                str(exc).strip() or type(exc).__name__,
            )

    def dock(self):
        try:
            core = self._fresh()
            self._set_banner(
                "Fresh Core · Volver a base tiene prioridad sobre la sesión actual…"
            )
            threading.Thread(
                target=lambda: self._fresh_dock_worker(core),
                name="FreshCoreDockUI",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror(
                "Volver a base",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    def _fresh_dock_worker(self, core):
        try:
            core.request_dock()
            self._post_ui("fresh_control_ok", "Regreso a base solicitado.")
        except Exception as exc:
            self._post_ui(
                "fresh_control_error",
                str(exc).strip() or type(exc).__name__,
            )

    def locate(self):
        try:
            core = self._fresh()
            threading.Thread(
                target=lambda: self._fresh_simple_worker(
                    "Robot localizado.", core.locate
                ),
                name="FreshCoreLocate",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror("Localizar", str(exc), parent=self)

    def set_suction(self, level):
        try:
            core = self._fresh()
            threading.Thread(
                target=lambda: self._fresh_simple_worker(
                    "Succión actualizada.",
                    lambda: core.set_suction(int(level)),
                ),
                name="FreshCoreSuction",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror("Succión", str(exc), parent=self)

    def set_water(self, level):
        try:
            core = self._fresh()
            threading.Thread(
                target=lambda: self._fresh_simple_worker(
                    "Agua actualizada.",
                    lambda: core.set_water(int(level)),
                ),
                name="FreshCoreWater",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror("Agua", str(exc), parent=self)

    def manual(self, direction):
        if not getattr(self, "vacuum", None):
            return
        try:
            core = self._fresh()
        except Exception:
            return

        def worker():
            try:
                core.manual(int(direction))
            except Exception as exc:
                self._post_ui(
                    "fresh_control_error",
                    "Control manual: "
                    + (str(exc).strip() or type(exc).__name__),
                )
        threading.Thread(
            target=worker,
            name="FreshCoreManual",
            daemon=True,
        ).start()

    def _fresh_simple_worker(self, ok_text, function):
        try:
            function()
            self._post_ui("fresh_control_ok", str(ok_text))
        except Exception as exc:
            self._post_ui(
                "fresh_control_error",
                str(exc).strip() or type(exc).__name__,
            )

    # ============================================================ mapeo
    def start_new_mapping(self):
        if not getattr(self, "vacuum", None):
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
        try:
            if self._v114_cleaning_busy():
                return
        except Exception:
            pass
        try:
            if self._fresh().arbiter.active:
                messagebox.showinfo(
                    "Robot ocupado",
                    "Terminá la tarea física actual antes de crear un mapa nuevo.",
                    parent=self,
                )
                return
        except Exception as exc:
            messagebox.showerror("Mapear vivienda", str(exc), parent=self)
            return

        ok = messagebox.askyesno(
            "Mapear vivienda · Fresh Core",
            "El control físico de mapeo fue rehecho desde cero.\n\n"
            "La app conservará su interfaz, geometría, habitaciones y captura "
            "de mapa, pero el robot hará una secuencia física nueva:\n"
            "1) neutralizar estado de navegación viejo;\n"
            "2) pedir build-map una sola vez;\n"
            "3) fijar Global=0;\n"
            "4) enviar un único START estándar 2/3.\n\n"
            "No se usa EDGE, 7/3 de arranque, escapes, reasserts ni START "
            "secundarios.",
            parent=self,
        )
        if not ok:
            return

        self._v151_prepare_map_layers()

        self._v145_session_latched = False
        self._v145_latch_reason = "fresh-core-map-request"
        self._v145_active_serial = None
        self._v145_last_block = {}

        self._v137_phase1_diag = {
            "route": "Fresh Core: sin Paso EDGE",
            "success": True,
            "skipped": True,
        }
        self._v137_phase2_diag = {}
        self._v137_phase1_starts = 0
        self._v137_phase2_starts = 1
        self._v137_manual_cancel = False
        self._v136_manual_abort = False
        self._v137_flow = "fresh-global"

        self._v121_stage = "global-fresh"
        self._v121_phase2_requested = True
        self._v121_phase2_started = False
        self._v121_phase2_departed = False
        self._v121_phase2_attempts = 1
        self._v121_phase2_errors = 0
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
                "10/24 antes de Fresh Core mapping",
            )

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False

        # También activa los bloqueos heredados V151; el proxy del transporte
        # es la segunda barrera, independiente de estos flags.
        self._v151_direct_global_owner = True
        self._fresh_mapping_active = True

        serial = int(self._v74_mapping_serial)
        self._fresh_mapping_serial = serial
        self._v145_active_serial = serial
        self._v145_latch_reason = None

        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner(
            "Fresh Core · borrando estado de navegación viejo antes del mapa…"
        )

        def started(diag):
            self._post_ui(
                "fresh_mapping_started",
                serial,
                dict(diag or {}),
            )

        def finished(diag):
            self._post_ui(
                "fresh_mapping_finished",
                serial,
                dict(diag or {}),
            )

        try:
            self._fresh().start_global_async(
                mode=0,
                suction=1,
                water=0,
                mapping=True,
                on_started=started,
                on_finished=finished,
                purpose="mapping",
            )
        except Exception as exc:
            self._fresh_mapping_active = False
            self._v151_direct_global_owner = False
            self.mapping_active = False
            self.mapping_phase = 0
            self._v145_latch_session(
                "fresh-map-start-rejected",
                close_mapping=True,
            )
            messagebox.showerror(
                "Mapear vivienda",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    # ========================================== limpiezas dirigidas Fresh Core
    def _v114_run_safe_rectangles(
        self,
        target,
        kind,
        label,
        mode,
        suction,
        water,
    ):
        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(self._v114_target_clean_active) or bool(
            getattr(self, "_zone_job_running", False)
        ):
            messagebox.showinfo(
                "Limpieza",
                "Ya hay una limpieza dirigida gestionada por la app.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá el mapeo antes de limpiar una habitación o zona.",
                parent=self,
            )
            return

        try:
            map_id, _snapshot, native, plan, constrained = (
                self._v114_constrain_target(target, kind, label)
            )
        except Exception as exc:
            messagebox.showerror(
                "Limpieza dirigida",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return

        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v114_map_fingerprint_before = original_fp
        self._v114_map_fingerprint_after = original_fp
        self._v114_target_clean_active = True
        self._zone_job_running = True
        self._v114_target_clean_kind = str(kind)
        self._v114_target_clean_label = str(label)
        self._v114_target_clean_map_id = map_id

        raw_rects = [
            local_rect_to_device(rect, plan)
            for rect in list(constrained.get("rectangles") or [])
        ]
        passes = (
            ["vacuum", "mop"]
            if str(mode) == "vacuum_then_mop"
            else [str(mode)]
        )

        core = self._fresh()

        def stage(index, total):
            self._post_ui(
                "plan_job_stage",
                f"{label} · sector {index}/{total}",
            )

        def finished(diag):
            self._post_ui(
                "fresh_target_finished",
                map_id,
                original_grid,
                original_fp,
                str(label),
                dict(diag or {}),
            )

        try:
            # Paredes/restricciones se envían dentro del mismo transporte nuevo.
            core.sync_virtual_walls(plan)
            core.run_zone_sequence(
                raw_rects,
                passes,
                suction,
                water,
                on_stage=stage,
                on_finished=finished,
            )
        except Exception as exc:
            self._v114_target_clean_active = False
            self._zone_job_running = False
            self._v114_target_errors += 1
            self._v114_last_target_error = (
                str(exc).strip() or type(exc).__name__
            )
            messagebox.showerror(
                "Limpieza dirigida",
                self._v114_last_target_error,
                parent=self,
            )

    def _run_schedule_now(self, schedule):
        schedule = dict(schedule or {})
        if str(schedule.get("target", "all")) == "zones":
            return super()._run_schedule_now(schedule)

        if bool(getattr(self, "mapping_active", False)):
            self._post_ui(
                "plan_job_error",
                "No se puede iniciar una programación durante un mapeo.",
            )
            return

        mode = str(schedule.get("mode", "vacuum"))
        mode_id = {
            "vacuum": 0,
            "vacuum_mop": 1,
            "mop": 2,
        }.get(mode, 0)
        suction = int(schedule.get("suction", 1) or 1)
        water = int(schedule.get("water", 1) or 0)

        def started(diag):
            self._post_ui(
                "plan_job_stage",
                "Programación · Fresh Core inició limpieza global.",
            )

        def finished(diag):
            if (diag or {}).get("error"):
                self._post_ui("plan_job_error", diag.get("error"))
            else:
                self._post_ui(
                    "plan_job_done",
                    "Programación · limpieza global finalizada.",
                )

        try:
            return self._fresh().start_global_async(
                mode=mode_id,
                suction=suction,
                water=water,
                mapping=False,
                on_started=started,
                on_finished=finished,
                purpose="schedule-now",
            )
        except Exception as exc:
            self._post_ui(
                "plan_job_error",
                str(exc).strip() or type(exc).__name__,
            )

    # =============================================== bloquear viejos writers
    def _sync_no_go_async(self):
        core = getattr(self, "_fresh_core", None)
        if core is not None and core.arbiter.active:
            return None
        return super()._sync_no_go_async()

    def _v127_try_phase2_recovery(self, reason):
        if self._fresh_mapping_active:
            return False
        return super()._v127_try_phase2_recovery(reason)

    def _v147_schedule_escape(self, serial, metrics):
        if self._fresh_mapping_active:
            return False
        return super()._v147_schedule_escape(serial, metrics)

    def _v147_request_abort(self, serial, metrics, reason):
        if self._fresh_mapping_active:
            return None
        return super()._v147_request_abort(serial, metrics, reason)

    def _v144_execute_auto_abort(self, serial, metrics):
        if self._fresh_mapping_active:
            self._v144_auto_abort_requested = False
            return False
        return super()._v144_execute_auto_abort(serial, metrics)

    def _v149_request_global_transition(self, serial, metrics, reason):
        if self._fresh_mapping_active:
            return True
        return super()._v149_request_global_transition(
            serial, metrics, reason
        )

    def _v150_session_allows_strategy_switch(self, serial):
        if self._fresh_mapping_active:
            return False
        return super()._v150_session_allows_strategy_switch(serial)

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "fresh_clean_started":
            diag = dict(payload[0] or {}) if payload else {}
            self._fresh_last_event = {"clean_started": diag}
            self._set_banner(
                "Fresh Core · limpieza global activa · un único START estándar."
            )
            return None

        if kind == "fresh_clean_finished":
            diag = dict(payload[0] or {}) if payload else {}
            self._fresh_last_event = {"clean_finished": diag}
            if diag.get("error"):
                self._set_banner(
                    "Fresh Core · limpieza finalizó con error: "
                    + str(diag.get("error"))
                )
            else:
                self._set_banner(
                    "Fresh Core · limpieza física finalizada · "
                    f"{diag.get('finish_reason', 'fin')}."
                )
            return None

        if kind == "fresh_mapping_started":
            serial = int(payload[0])
            diag = dict(payload[1] or {})
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._fresh_last_event = {"mapping_started": diag}
            self._v120_last_start_diag = {
                "route": "Fresh Core",
                "fresh": dict(diag),
            }
            self._v137_phase2_diag = dict(diag)
            self._v121_phase2_diag = dict(diag)

            # Reutiliza sólo observadores/mapa/UI existentes. Cualquier escritura
            # heredada queda bloqueada por Fresh Core + proxy de transporte.
            result = super()._handle_ui_event(
                "v74_mapping_started",
                (serial,),
            )
            self._v121_stage = "global-fresh"
            self._v137_flow = "fresh-global"
            self.mapping_phase = 2
            self.mapping_step1_complete = True
            self.mapping_step2_complete = False
            self._v73_session_phase = 2
            self._set_banner(
                "Fresh Core · mapeo activo · Global=0 + START estándar único."
            )
            return result

        if kind == "fresh_mapping_finished":
            serial = int(payload[0])
            diag = dict(payload[1] or {})
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._fresh_last_event = {"mapping_finished": diag}
            self._fresh_mapping_active = False
            self._v151_direct_global_owner = False

            if diag.get("error"):
                self.mapping_active = False
                self.mapping_phase = 0
                self.mapping_transitioning = False
                self._v145_latch_session(
                    "fresh-map-error",
                    close_mapping=True,
                )
                self._sync_mapping_step_buttons()
                self._set_banner(
                    "Fresh Core · mapeo detenido por error: "
                    + str(diag.get("error"))
                )
                return None

            self._set_banner(
                "Fresh Core · recorrido terminó · finalizando mapa Xiaomi…"
            )
            try:
                self.after(120, self._v84_close_mapping_on_dock)
            except Exception:
                pass
            return None

        if kind == "fresh_target_finished":
            map_id = str(payload[0])
            original_grid = dict(payload[1] or {})
            original_fp = payload[2]
            label = str(payload[3])
            diag = dict(payload[4] or {})

            self._v114_restore_grid_if_needed(
                original_grid,
                original_fp,
                map_id,
            )
            self._v114_target_clean_active = False
            self._zone_job_running = False

            if diag.get("error"):
                self._v114_target_errors += 1
                self._v114_last_target_error = str(diag.get("error"))
                self._post_ui(
                    "plan_job_error",
                    self._v114_last_target_error,
                )
            else:
                self._v114_target_completed += int(
                    diag.get("completed", 0) or 0
                )
                self._post_ui(
                    "plan_job_done",
                    f"{label} · limpieza completada con Fresh Core.",
                )
            return None

        if kind == "fresh_control_ok":
            self._set_banner(str(payload[0]) if payload else "Comando enviado.")
            return None

        if kind == "fresh_control_error":
            message = str(payload[0]) if payload else "Error de control."
            self._set_banner(message)
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        core = getattr(self, "_fresh_core", None)
        diag = core.diagnostic() if core is not None else {}
        lines = [
            "FRESH CORE · CONTROL FÍSICO REHECHO DESDE CERO",
            "================================================",
            f"core instalado={core is not None}",
            f"sesión física activa={bool(diag.get('active'))}",
            f"sesión={diag.get('session') or '—'}",
            f"última ejecución={diag.get('last') or '—'}",
            f"writes heredados bloqueados={diag.get('legacy_blocks', 0)}",
            f"último write heredado bloqueado={diag.get('last_legacy_block') or '—'}",
            f"mapeo Fresh activo={self._fresh_mapping_active}",
            "regla Fresh: sólo fresh_robot_core escribe navegación/limpieza",
            "regla Fresh: GUI y Scheduler comparten bloqueo entre procesos",
            "regla Fresh: antes de limpiar se neutralizan EDGE/global/punto/remoto/repeat/twice",
            "regla Fresh: limpieza global = Global=0 + UN START estándar 2/3, 2/5 o 2/6",
            "regla Fresh: mapeo = neutralizar + 10/17 [1] una vez + Global=0 + UN START estándar",
            "regla Fresh: 7/3 sólo se usa como STOP durante neutralización, nunca como START",
            "regla Fresh: no hay reassert, recovery, escape ni START secundario",
            "regla Fresh: STOP/Volver a base invalidan la sesión actual por prioridad",
            "",
            "AUDITORÍA DE TRANSPORTE FRESH (últimas 40):",
            repr(diag.get("audit") or []),
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

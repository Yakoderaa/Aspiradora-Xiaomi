import math
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v73


class App(app_v73.App):
    """V74: mapeo único mediante limpieza normal ECO, sin EDGE ni dos fases."""

    MAP_CELL_SIZE = 3.0
    NO_NEW_AREA_SECONDS = 240.0
    MIN_MAPPING_SECONDS = 300.0
    MIN_COVERAGE_CELLS = 35
    STATUS_POLL_SECONDS = 0.8
    RETURN_CONFIRM_SAMPLES = 2

    def __init__(self):
        self._v74_mapping_serial = 0
        self._v74_watch_active = False
        self._v74_started_at = None
        self._v74_last_discovery_at = None
        self._v74_coverage_cells = set()
        self._v74_finish_requested = False
        self._v74_finish_reason = None
        self._v74_last_status = None
        self._v74_return_samples = 0
        self._v74_normal_clean_started = False
        super().__init__()
        self._v74_refresh_mapping_controls()

    def _build_map_page(self):
        super()._build_map_page()
        self._v74_refresh_mapping_controls()

    def _v74_refresh_mapping_controls(self):
        step1 = getattr(self, "step1_mapping_button", None)
        if step1 is not None:
            try:
                step1.configure(text="Mapear vivienda", command=self.start_new_mapping)
            except tk.TclError:
                pass
        step2 = getattr(self, "step2_mapping_button", None)
        if step2 is not None:
            try:
                step2.pack_forget()
            except tk.TclError:
                pass
        stop = getattr(self, "stop_mapping_button", None)
        if stop is not None:
            try:
                stop.configure(text="Detener mapeo")
            except tk.TclError:
                pass
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(text="Mapeo único · limpieza normal ECO · antiatasco · retorno seguro")
            except tk.TclError:
                pass

    def _sync_mapping_step_buttons(self):
        try:
            result = super()._sync_mapping_step_buttons()
        except Exception:
            result = None
        self._v74_refresh_mapping_controls()
        step1 = getattr(self, "step1_mapping_button", None)
        if step1 is not None:
            try:
                step1.configure(state="disabled" if bool(getattr(self, "mapping_active", False)) else "normal")
            except tk.TclError:
                pass
        return result

    def _v72_install_map_controls(self):
        super()._v72_install_map_controls()
        old = getattr(self, "_v72_legend", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        canvas = getattr(self, "map_canvas", None)
        if canvas is None:
            return
        legend = tk.Frame(canvas, bg="#ffffff", highlightthickness=1, highlightbackground="#e2e8f0", padx=10, pady=7)
        legend.place(x=14, y=14)
        row = tk.Frame(legend, bg="#ffffff")
        row.pack()
        line = tk.Canvas(row, width=23, height=10, bg="#ffffff", highlightthickness=0)
        line.pack(side="left")
        line.create_line(1, 5, 22, 5, fill="#3b82f6", width=3)
        tk.Label(row, text="Recorrido", bg="#ffffff", fg="#64748b", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(4, 0))
        self._v72_legend = legend
        legend.lift()

    def _v74_reset_session(self):
        self._v74_mapping_serial += 1
        self._v74_watch_active = False
        self._v74_started_at = None
        self._v74_last_discovery_at = None
        self._v74_coverage_cells = set()
        self._v74_finish_requested = False
        self._v74_finish_reason = None
        self._v74_last_status = None
        self._v74_return_samples = 0
        self._v74_normal_clean_started = False

        self._perimeter_watch_serial += 1
        self._v67_watch_serial += 1
        self._v67_watch_running = False
        self._v67_start_scheduled = False
        self._v67_step1_session_active = False
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False
        self._v71_phase2_watch_serial += 1
        self._v71_phase2_watch_active = False
        self._v71_phase2_seen_interior = False
        self._v71_phase2_edge_samples = 0
        self._v71_phase2_idle_samples = 0
        self._v71_phase2_complete_reason = None

        self._v73_session_phase = 2
        self._v73_seen_track_keys = set()
        self._v73_phase_new = {1: 0, 2: 0}
        self._v73_phase_saved = {1: 0, 2: 0}
        self._v73_transit_points = 0
        self._v73_pose_window.clear()
        self._v73_recovery_active = False
        self._v73_recovery_count = 0
        self._v73_last_recovery_at = 0.0
        self._v73_last_recovery_reason = None
        self._v73_repeat_triggered = False
        self._v73_dock_retries = 0
        self._v73_dock_failed = False
        self._v73_last_parsed_return_pose = None
        self._v73_dock_guard_serial += 1
        self._v73_dock_guard_active = False
        self._v73_dock_guard_reason = None

        self._v71_session_origin_raw = None
        self._v71_session_origin_source = None
        self._v71_session_max_departure = 0.0
        self._v71_return_distance = None
        self._v71_return_threshold = None
        self._v71_return_near_samples = 0
        self._v71_return_confirm_mode = None
        self._v71_path_points_merged = {1: 0, 2: 0}
        self._v71_path_points_seen = {1: 0, 2: 0}

    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo("Mapeo en curso", "Primero detené el mapeo actual.", parent=self)
            return

        ok = messagebox.askyesno(
            "Mapear vivienda",
            "Se va a borrar el mapa local seleccionado y comenzar un mapeo nuevo.\n\n"
            "El E10 hará una limpieza NORMAL en potencia ECO, con agua apagada. "
            "No se usará el modo de bordes ni habrá Paso 1/Paso 2.\n\n"
            "La app registrará un único recorrido, intentará liberarlo si queda "
            "girando sin avanzar y lo enviará a la base si deja de descubrir "
            "zona nueva durante varios minutos.\n\n"
            "Para que la base quede en (0,0), conviene iniciar con el robot acoplado.",
            parent=self,
        )
        if not ok:
            return

        self._v74_reset_session()
        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(before, "10/24 antes de mapeo único V74")

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Mapeo único · preparando limpieza normal ECO con agua apagada…")

        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.arm_new_map(1)
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
                vacuum.start_mapping_interior()
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                self._post_ui("v74_mapping_start_error", serial, str(exc).strip() or type(exc).__name__)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started":
            serial = int(payload[0])
            if serial != self._v74_mapping_serial:
                return
            self._v74_started_at = time.monotonic()
            self._v74_last_discovery_at = self._v74_started_at
            self._v74_normal_clean_started = True
            self._v74_watch_active = True
            self._set_banner("Mapeo único activo · limpieza normal ECO · registrando recorrido en tiempo real…")
            threading.Thread(target=self._v74_watch_mapping_worker, args=(self.vacuum, serial), daemon=True).start()
            return

        if kind == "v74_mapping_start_error":
            serial, message = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._v74_watch_active = False
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("No se pudo iniciar el mapeo único.")
            messagebox.showerror("Mapeo", str(message), parent=self)
            return

        if kind == "v74_mapping_complete":
            serial, reason = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._v74_watch_active = False
            self._v74_finish_requested = True
            self._v74_finish_reason = str(reason)
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = True
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(str(reason))
            try:
                threading.Thread(target=self._restore_cleaning_preferences, daemon=True).start()
            except Exception:
                pass
            self._v73_start_dock_guard("fin de mapeo único")
            try:
                self.after(100, self._v70_notify_mapping_complete)
            except Exception:
                pass
            return

        if kind == "v74_no_new_area":
            serial, seconds_without_new, cells = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._set_banner(
                "No aparecen zonas nuevas desde hace "
                f"{int(seconds_without_new)} s ({int(cells)} celdas cubiertas). "
                "Cerrando el mapeo y volviendo a la base…"
            )
            return

        if kind == "v73_stall_recovered":
            attempt, _phase, reason = payload
            self._v73_recovery_active = False
            self._v73_pose_window.clear()
            self._set_banner(
                f"Recuperación automática {attempt}/{self.MAX_STALL_RECOVERIES}: "
                f"el E10 salió del atasco y retomó el mapeo. {reason}"
            )
            return

        if kind == "v73_stall_recovery_error":
            attempt, _phase, message = payload
            self._v73_recovery_active = False
            self._v73_pose_window.clear()
            self._v74_finish_requested = True
            self._v74_finish_reason = f"Fallo de recuperación automática {attempt}: {message}"
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("No pude liberar al E10; detuve el mapeo y lo envié a la base. " + str(message))
            self._v73_start_dock_guard("fallo de recuperación V74")
            return

        if kind == "v73_stall_abort":
            reason = str(payload[0])
            self._v73_recovery_active = False
            self._v74_finish_requested = True
            self._v74_finish_reason = "Atasco repetido: " + reason
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("Mapeo detenido por seguridad: el E10 repitió el atasco. " + reason)
            self._v73_start_dock_guard("atasco repetido V74")
            return

        if kind in ("edge_only_complete", "perimeter_complete", "auto_step2_started", "v71_phase2_complete"):
            return

        return super()._handle_ui_event(kind, payload)

    def _apply_map_state(self, state):
        if isinstance(state, dict) and bool(getattr(self, "mapping_active", False)):
            raw_robot = state.get("robot")
            if self._v71_session_origin_raw is None:
                original_path = [point for point in list(state.get("path") or []) if isinstance(point, dict)]
                first = self._v71_xy(original_path[0]) if original_path else None
                if first is None:
                    parsed = self._v73_parse_pose(raw_robot)
                    if parsed is not None:
                        first = (parsed[0], parsed[1])
                if first is not None:
                    self._v71_set_origin(first, "primera pose real de mapeo único V74")
            self._v74_note_coverage(raw_robot)
        return super()._apply_map_state(state)

    def _v74_note_coverage(self, raw_robot):
        if self._v74_finish_requested or not bool(getattr(self, "mapping_active", False)) or self._v73_recovery_active:
            return
        origin = self._v71_session_origin_raw
        parsed = self._v73_parse_pose(raw_robot)
        if origin is None or parsed is None:
            return
        local_x = parsed[0] - origin[0]
        local_y = parsed[1] - origin[1]
        if not (math.isfinite(local_x) and math.isfinite(local_y)):
            return

        cell = (
            int(round(local_x / self.MAP_CELL_SIZE)),
            int(round(local_y / self.MAP_CELL_SIZE)),
        )
        now = time.monotonic()
        if cell not in self._v74_coverage_cells:
            self._v74_coverage_cells.add(cell)
            self._v74_last_discovery_at = now
            return

        started = self._v74_started_at
        last_new = self._v74_last_discovery_at
        if started is None or last_new is None:
            return
        elapsed = now - started
        no_new = now - last_new
        if (
            elapsed >= self.MIN_MAPPING_SECONDS
            and no_new >= self.NO_NEW_AREA_SECONDS
            and len(self._v74_coverage_cells) >= self.MIN_COVERAGE_CELLS
        ):
            self._v74_request_finish_for_coverage(no_new)

    def _v74_request_finish_for_coverage(self, no_new_seconds):
        if self._v74_finish_requested or not self.vacuum:
            return
        self._v74_finish_requested = True
        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        cells = len(self._v74_coverage_cells)
        self._post_ui("v74_no_new_area", serial, no_new_seconds, cells)

        def worker():
            try:
                vacuum.stop()
            except Exception:
                pass
            time.sleep(0.35)
            try:
                vacuum.dock()
            except Exception:
                pass
            self._post_ui(
                "v74_mapping_complete",
                serial,
                "Mapeo finalizado: el E10 dejó de descubrir zona nueva y volvió a la base.",
            )

        threading.Thread(target=worker, daemon=True).start()

    def _v74_watch_mapping_worker(self, vacuum, serial):
        return_samples = 0
        seen_moving = False
        while serial == self._v74_mapping_serial and self._v74_watch_active:
            if vacuum is not self.vacuum or not bool(getattr(self, "mapping_active", False)):
                return
            try:
                values = vacuum._get_many([("status", 2, 1), ("fault", 2, 2)])
                status = self._v67_int(values.get("status"))
                fault = self._v67_int(values.get("fault"))
            except Exception:
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            self._v74_last_status = status
            if status in (5, 6, 7):
                seen_moving = True

            if self._v73_recovery_active:
                return_samples = 0
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            returning = seen_moving and fault in (None, 0) and status in (3, 4)
            return_samples = return_samples + 1 if returning else 0
            self._v74_return_samples = return_samples

            if return_samples >= self.RETURN_CONFIRM_SAMPLES:
                self._v74_finish_requested = True
                reason = (
                    "Mapeo terminado · el E10 completó la limpieza y está cargando."
                    if status == 4
                    else "Mapeo terminado · el E10 completó la limpieza y regresó a la base."
                )
                self._post_ui("v74_mapping_complete", serial, reason)
                return

            time.sleep(self.STATUS_POLL_SECONDS)

    def finish_mapping(self):
        if not bool(getattr(self, "mapping_active", False)):
            return super().finish_mapping()

        self._v74_finish_requested = True
        self._v74_watch_active = False
        self._v74_mapping_serial += 1
        self._v73_session_phase = 0
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_transitioning = False
        self._sync_mapping_step_buttons()
        self._render_maps()

        vacuum = self.vacuum
        if vacuum is not None:
            def worker():
                try:
                    vacuum.stop()
                except Exception:
                    pass
            threading.Thread(target=worker, daemon=True).start()

        self._set_banner("Mapeo detenido manualmente.")
        return None

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()
        elapsed = now - self._v74_started_at if self._v74_started_at is not None else 0.0
        no_new = now - self._v74_last_discovery_at if self._v74_last_discovery_at is not None else 0.0
        lines = [
            "DIAGNÓSTICO V74 ACTIVO · mapeo único por limpieza normal ECO",
            "============================================================",
            f"mapeo activo: {bool(getattr(self, 'mapping_active', False))} · sweep normal iniciado={bool(self._v74_normal_clean_started)}",
            f"tiempo de mapeo: {elapsed:.1f}s · último status={self._v74_last_status!r}",
            f"celdas nuevas cubiertas: {len(self._v74_coverage_cells)} · tamaño celda={self.MAP_CELL_SIZE}",
            f"sin descubrir zona nueva: {no_new:.1f}s · umbral={self.NO_NEW_AREA_SECONDS}s",
            f"fin solicitado: {bool(self._v74_finish_requested)} · razón={self._v74_finish_reason or '—'}",
            f"muestras de retorno: {self._v74_return_samples}/{self.RETURN_CONFIRM_SAMPLES}",
            "regla V74: no se usa EDGE/perímetro; el mapa nace de un único sweep normal en ECO con agua=0",
            "regla V74: toda la trayectoria pertenece a una sola capa Recorrido; no existe transición Paso 1/Paso 2",
            "regla V74: si deja de descubrir celdas nuevas tras un tiempo mínimo, se cierra el mapeo y se envía a base",
            "regla V74: giro sin avance conserva la recuperación V73 y el acople conserva la protección de rampa",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

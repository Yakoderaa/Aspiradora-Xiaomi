import math
import threading
import time
import tkinter as tk

import app_v80


class App(app_v80.App):
    """V81: cobertura suficiente antes de cerrar + retorno al dock sin bucles."""

    # El mapa no puede declararse completo sólo porque el E10 repita un
    # corredor. Primero tiene que haber exploración espacial suficiente.
    MIN_MAPPING_SECONDS = 240.0
    NO_NEW_AREA_SECONDS = 180.0
    MIN_COVERAGE_CELLS = 20
    COMPLETE_MIN_DEPARTURE = 1.20
    COMPLETE_MIN_AXIS_SPAN = 1.00
    MAX_INCOMPLETE_CORRIDOR_EVENTS = 4
    MAX_NO_NEW_DEFERRALS = 1

    # El firmware recibe UN dock. Durante esta ventana sólo observamos.
    DOCK_SEARCH_TIMEOUT_SECONDS = 120.0
    DOCK_NEAR_RADIUS_METERS = 0.70

    def __init__(self):
        self._v81_min_x = None
        self._v81_max_x = None
        self._v81_min_y = None
        self._v81_max_y = None
        self._v81_completion_ready = False
        self._v81_completion_missing = []
        self._v81_corridor_incomplete_hits = 0
        self._v81_no_new_deferrals = 0
        self._v81_incomplete_reason = None

        self._v81_dock_commands_sent = 0
        self._v81_dock_monitor_started_at = None
        self._v81_dock_last_status = None
        self._v81_dock_last_distance = None
        self._v81_dock_near_samples = 0
        self._v81_dock_timeout = False
        self._v81_dock_confirmed = False
        super().__init__()

    def _v74_reset_session(self):
        self._v81_min_x = None
        self._v81_max_x = None
        self._v81_min_y = None
        self._v81_max_y = None
        self._v81_completion_ready = False
        self._v81_completion_missing = []
        self._v81_corridor_incomplete_hits = 0
        self._v81_no_new_deferrals = 0
        self._v81_incomplete_reason = None

        self._v81_dock_commands_sent = 0
        self._v81_dock_monitor_started_at = None
        self._v81_dock_last_status = None
        self._v81_dock_last_distance = None
        self._v81_dock_near_samples = 0
        self._v81_dock_timeout = False
        self._v81_dock_confirmed = False
        return super()._v74_reset_session()

    # ====================================================== controles / texto
    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · cobertura reforzada · "
                        "antiatasco · retorno al dock sin reintentos"
                    )
                )
            except tk.TclError:
                pass
        return result

    # =============================================== cobertura / completitud
    def _v81_note_extent(self, robot):
        try:
            x = float(robot["x"])
            y = float(robot["y"])
        except Exception:
            return
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        self._v81_min_x = x if self._v81_min_x is None else min(self._v81_min_x, x)
        self._v81_max_x = x if self._v81_max_x is None else max(self._v81_max_x, x)
        self._v81_min_y = y if self._v81_min_y is None else min(self._v81_min_y, y)
        self._v81_max_y = y if self._v81_max_y is None else max(self._v81_max_y, y)

    def _v81_completion_state(self):
        now = time.monotonic()
        elapsed = (
            now - self._v74_started_at
            if self._v74_started_at is not None
            else 0.0
        )
        cells = len(self._v74_coverage_cells)
        departure = float(self._v71_session_max_departure or 0.0)

        x_span = (
            float(self._v81_max_x - self._v81_min_x)
            if self._v81_min_x is not None and self._v81_max_x is not None
            else 0.0
        )
        y_span = (
            float(self._v81_max_y - self._v81_min_y)
            if self._v81_min_y is not None and self._v81_max_y is not None
            else 0.0
        )

        missing = []
        if elapsed < self.MIN_MAPPING_SECONDS:
            missing.append(
                f"tiempo {elapsed:.0f}/{self.MIN_MAPPING_SECONDS:.0f}s"
            )
        if cells < self.MIN_COVERAGE_CELLS:
            missing.append(
                f"cobertura {cells}/{self.MIN_COVERAGE_CELLS} celdas"
            )
        if departure < self.COMPLETE_MIN_DEPARTURE:
            missing.append(
                f"salida {departure:.2f}/{self.COMPLETE_MIN_DEPARTURE:.2f}m"
            )
        if x_span < self.COMPLETE_MIN_AXIS_SPAN:
            missing.append(
                f"ancho X {x_span:.2f}/{self.COMPLETE_MIN_AXIS_SPAN:.2f}m"
            )
        if y_span < self.COMPLETE_MIN_AXIS_SPAN:
            missing.append(
                f"ancho Y {y_span:.2f}/{self.COMPLETE_MIN_AXIS_SPAN:.2f}m"
            )

        ready = not missing
        self._v81_completion_ready = ready
        self._v81_completion_missing = list(missing)
        return {
            "ready": ready,
            "elapsed": elapsed,
            "cells": cells,
            "departure": departure,
            "x_span": x_span,
            "y_span": y_span,
            "missing": missing,
        }

    def _v77_note_coverage_metric(self, robot):
        self._v81_note_extent(robot)
        result = super()._v77_note_coverage_metric(robot)
        self._v81_completion_state()
        return result

    # ============================ no-new-area: nunca "completo" si falta mapa
    def _v74_request_finish_for_coverage(self, no_new_seconds):
        state = self._v81_completion_state()
        if state["ready"]:
            return self._v81_finish_complete(
                "Mapeo terminado · cobertura suficiente y sin zonas nuevas; "
                "regresando a la base."
            )

        if self._v74_finish_requested or not self.vacuum:
            return

        self._v81_no_new_deferrals += 1
        reason = (
            "Cobertura todavía insuficiente: "
            + ", ".join(state["missing"])
        )

        if self._v81_no_new_deferrals <= self.MAX_NO_NEW_DEFERRALS:
            # Le damos otra ventana completa al sweep normal. No fingimos que
            # el mapa está listo y tampoco mandamos dock.
            self._v74_last_discovery_at = time.monotonic()
            self._post_ui(
                "v81_mapping_continue",
                self._v74_mapping_serial,
                reason,
                int(state["cells"]),
            )
            return

        self._v81_stop_incomplete(
            "Mapeo incompleto: el E10 dejó de descubrir zonas nuevas y "
            + reason,
            send_dock=True,
        )

    # ================================ corredor: escapar, no completar el mapa
    def _v77_corridor_finish(self, reason):
        if self._v74_finish_requested or not self.vacuum:
            return

        state = self._v81_completion_state()
        if state["ready"]:
            return self._v81_finish_complete(
                "Mapeo terminado · cobertura suficiente; el E10 repitió "
                "un corredor y se envió una sola vez a la base."
            )

        self._v81_corridor_incomplete_hits += 1
        if self._v77_corridor_events < self.MAX_INCOMPLETE_CORRIDOR_EVENTS:
            # V77 quería terminar en el segundo evento. V81 usa ese evento para
            # otra maniobra de salida porque el mapa todavía no cumple cobertura.
            recovery_reason = (
                "pasadas ida/vuelta con cobertura incompleta · "
                + ", ".join(state["missing"])
            )
            self._post_ui(
                "v81_corridor_continue",
                self._v74_mapping_serial,
                self._v77_corridor_events,
                recovery_reason,
            )
            self._v73_schedule_recovery(2, recovery_reason)
            return

        self._v81_stop_incomplete(
            "Mapeo incompleto/atascado: el E10 repitió el mismo corredor "
            f"{self._v77_corridor_events} veces sin explorar suficiente área "
            "(" + ", ".join(state["missing"]) + ").",
            send_dock=True,
        )

    # ============================================ cierre completo / incompleto
    def _v81_send_single_dock(self, vacuum):
        try:
            vacuum.dock()
            self._v81_dock_commands_sent += 1
            return True
        except Exception:
            return False

    def _v81_finish_complete(self, reason):
        if self._v74_finish_requested or not self.vacuum:
            return
        self._v74_finish_requested = True
        self._v74_finish_reason = str(reason)
        self._v75_invalidate_recovery()
        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.stop()
            except Exception:
                pass
            time.sleep(0.35)
            self._v81_send_single_dock(vacuum)
            self._post_ui("v74_mapping_complete", serial, str(reason))

        threading.Thread(target=worker, daemon=True).start()

    def _v81_stop_incomplete(self, reason, send_dock):
        if self._v74_finish_requested:
            return
        self._v74_finish_requested = True
        self._v74_finish_reason = str(reason)
        self._v81_incomplete_reason = str(reason)
        self._v75_invalidate_recovery()
        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.stop()
            except Exception:
                pass
            sent = False
            if send_dock:
                time.sleep(0.35)
                sent = self._v81_send_single_dock(vacuum)
            self._post_ui(
                "v81_mapping_incomplete",
                serial,
                str(reason),
                bool(sent),
            )

        threading.Thread(target=worker, daemon=True).start()

    # ============================= watcher: retorno propio también se valida
    def _v74_watch_mapping_worker(self, vacuum, serial):
        return_samples = 0
        idle_samples = 0
        seen_moving = False
        status4_samples = 0

        while serial == self._v74_mapping_serial and self._v74_watch_active:
            if vacuum is not self.vacuum:
                return
            if not bool(getattr(self, "mapping_active", False)):
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("fault", 2, 2),
                ])
                status = self._v67_int(values.get("status"))
                fault = self._v67_int(values.get("fault"))
            except Exception:
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            self._v74_last_status = status
            mapped_points = int(self._v73_phase_saved.get(2, 0) or 0)
            if status in (5, 6, 7) or mapped_points >= 3:
                seen_moving = True

            if self._v73_recovery_active:
                return_samples = 0
                idle_samples = 0
                status4_samples = 0
                self._v77_status4_confirmations = 0
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            returning = seen_moving and fault in (None, 0) and status in (3, 4)
            return_samples = return_samples + 1 if returning else 0
            self._v74_return_samples = return_samples

            if seen_moving and fault in (None, 0) and status == 4:
                status4_samples += 1
            else:
                status4_samples = 0
            self._v77_status4_confirmations = status4_samples

            if seen_moving and fault in (None, 0) and status == 1:
                idle_samples += 1
            else:
                idle_samples = 0
            self._v75_idle_samples = idle_samples

            if (
                return_samples >= self.RETURN_CONFIRM_SAMPLES
                or status4_samples >= self.RETURN_CONFIRM_SAMPLES
            ):
                state = self._v81_completion_state()
                if state["ready"]:
                    self._v74_finish_requested = True
                    reason = (
                        "Mapeo terminado · el E10 está cargando en la base."
                        if status == 4
                        else "Mapeo terminado · el E10 completó la cobertura y regresó a la base."
                    )
                    self._post_ui("v74_mapping_complete", serial, reason)
                else:
                    # Si el firmware decide volver antes de tiempo, guardamos
                    # el recorrido parcial como diagnóstico, pero NO notificamos
                    # "mapeo terminado".
                    self._v74_finish_requested = True
                    reason = (
                        "Mapeo incompleto: el E10 volvió a la base antes de "
                        "alcanzar cobertura suficiente ("
                        + ", ".join(state["missing"])
                        + ")."
                    )
                    self._v81_incomplete_reason = reason
                    self._post_ui(
                        "v81_mapping_incomplete",
                        serial,
                        reason,
                        False,
                    )
                return

            if idle_samples >= self.IDLE_FINISH_SAMPLES:
                state = self._v81_completion_state()
                if state["ready"]:
                    self._v81_finish_complete(
                        "Mapeo terminado · cobertura suficiente; el E10 quedó "
                        "inactivo y fue enviado una sola vez a la base."
                    )
                else:
                    self._v81_stop_incomplete(
                        "Mapeo incompleto: el E10 quedó inactivo antes de "
                        "alcanzar cobertura suficiente ("
                        + ", ".join(state["missing"])
                        + ").",
                        send_dock=True,
                    )
                return

            time.sleep(self.STATUS_POLL_SECONDS)

    # ========================================== dock: observar, nunca reordenar
    def _v73_start_dock_guard(self, reason):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return
        self._v73_dock_guard_serial += 1
        serial = self._v73_dock_guard_serial
        self._v73_dock_guard_active = True
        self._v73_dock_guard_reason = str(reason)
        self._v73_dock_retries = 0
        self._v73_dock_failed = False

        self._v81_dock_monitor_started_at = time.monotonic()
        self._v81_dock_last_status = None
        self._v81_dock_last_distance = None
        self._v81_dock_near_samples = 0
        self._v81_dock_timeout = False
        self._v81_dock_confirmed = False

        threading.Thread(
            target=self._v81_dock_monitor_worker,
            args=(vacuum, serial, str(reason)),
            daemon=True,
        ).start()

    def _v81_dock_monitor_worker(self, vacuum, serial, reason):
        deadline = time.monotonic() + self.DOCK_SEARCH_TIMEOUT_SECONDS
        charge_samples = 0

        while time.monotonic() < deadline:
            if serial != self._v73_dock_guard_serial:
                return
            if vacuum is not getattr(self, "vacuum", None):
                return

            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                raw_robot = state.get("robot")
            except Exception:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            self._v81_dock_last_status = status
            distance = self._v71_raw_distance_to_origin(raw_robot)
            self._v81_dock_last_distance = distance

            if (
                distance is not None
                and distance <= self.DOCK_NEAR_RADIUS_METERS
                and fault in (None, 0)
            ):
                # Girar cerca del dock es una maniobra normal del firmware.
                # No stop, no reverse, no recovery y NO segundo dock.
                self._v81_dock_near_samples += 1

            charging = status == 4 and fault in (None, 0)
            charge_samples = charge_samples + 1 if charging else 0
            if charge_samples >= self.BASE_CONFIRM_SAMPLES:
                self._v81_dock_confirmed = True
                self._v73_dock_guard_active = False
                self._post_ui("v81_dock_confirmed", serial, reason)
                return

            time.sleep(self.BASE_POLL_SECONDS)

        if serial != self._v73_dock_guard_serial:
            return

        # La única intervención tras el timeout es parar las ruedas. No se
        # reenvía dock y no se hace marcha atrás automática.
        try:
            vacuum.stop()
        except Exception:
            pass
        try:
            vacuum.manual(5)
        except Exception:
            pass

        self._v81_dock_timeout = True
        self._v73_dock_failed = True
        self._v73_dock_guard_active = False
        self._post_ui(
            "v81_dock_timeout",
            serial,
            reason,
            self._v81_dock_last_status,
            self._v81_dock_last_distance,
        )

    # ============================================================= eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v81_mapping_continue":
            serial, reason, cells = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._set_banner(
                f"El mapa todavía está incompleto ({int(cells)} celdas). "
                "Se mantiene el barrido para buscar más zona. "
                + str(reason)
            )
            return

        if kind == "v81_corridor_continue":
            serial, event_number, reason = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._set_banner(
                f"Corredor repetido #{int(event_number)}: el mapa aún no "
                "tiene cobertura suficiente; intento de salida sin finalizar. "
                + str(reason)
            )
            return

        if kind == "v81_mapping_incomplete":
            serial, reason, dock_sent = payload
            if int(serial) != self._v74_mapping_serial:
                return
            self._v74_watch_active = False
            self._v74_finish_requested = True
            self._v74_finish_reason = str(reason)
            self._v81_incomplete_reason = str(reason)
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(str(reason))
            try:
                threading.Thread(
                    target=self._restore_cleaning_preferences,
                    daemon=True,
                ).start()
            except Exception:
                pass
            # No se usa la notificación de "mapeo terminado".
            if bool(dock_sent):
                self._v73_start_dock_guard("mapeo incompleto V81")
            return

        if kind == "v81_dock_confirmed":
            serial, reason = payload
            if int(serial) != self._v73_dock_guard_serial:
                return
            self._v73_dock_guard_active = False
            self._set_banner(
                "Base confirmada: el E10 está cargando. "
                f"Retorno supervisado sin reintentos ({reason})."
            )
            return

        if kind == "v81_dock_timeout":
            serial, reason, status, distance = payload
            if int(serial) != self._v73_dock_guard_serial:
                return
            self._v73_dock_guard_active = False
            self._v73_dock_failed = True
            distance_text = (
                "sin posición"
                if distance is None
                else f"{float(distance):.2f} m de la base"
            )
            self._set_banner(
                "Retorno detenido por seguridad: el E10 no confirmó carga "
                f"tras {int(self.DOCK_SEARCH_TIMEOUT_SECONDS)} s "
                f"({distance_text}, status={status}). "
                "No se reenviaron comandos de dock."
            )
            return

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        state = self._v81_completion_state()
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V81 ACTIVO · cobertura real + dock sin bucles",
            "=========================================================",
            (
                "completitud: "
                f"{state['ready']} · celdas={state['cells']}/{self.MIN_COVERAGE_CELLS} · "
                f"salida={state['departure']:.2f}/{self.COMPLETE_MIN_DEPARTURE:.2f} m"
            ),
            (
                "extensión explorada: "
                f"X={state['x_span']:.2f} m · Y={state['y_span']:.2f} m · "
                f"mínimo por eje={self.COMPLETE_MIN_AXIS_SPAN:.2f} m"
            ),
            (
                "tiempo: "
                f"{state['elapsed']:.1f}/{self.MIN_MAPPING_SECONDS:.0f}s · "
                f"faltante={', '.join(state['missing']) if state['missing'] else '—'}"
            ),
            (
                "corredor incompleto: "
                f"hits={self._v81_corridor_incomplete_hits} · "
                f"eventos máximos antes de abortar={self.MAX_INCOMPLETE_CORRIDOR_EVENTS}"
            ),
            (
                "sin zona nueva: "
                f"aplazamientos={self._v81_no_new_deferrals}/"
                f"{self.MAX_NO_NEW_DEFERRALS} · umbral={self.NO_NEW_AREA_SECONDS:.0f}s"
            ),
            f"motivo incompleto: {self._v81_incomplete_reason or '—'}",
            (
                "dock V81: "
                f"comandos enviados={self._v81_dock_commands_sent} · "
                f"status={self._v81_dock_last_status!r} · "
                f"distancia={self._v81_dock_last_distance!r} · "
                f"muestras cerca={self._v81_dock_near_samples}"
            ),
            (
                "dock resultado: "
                f"confirmado={self._v81_dock_confirmed} · "
                f"timeout={self._v81_dock_timeout} · "
                f"ventana={self.DOCK_SEARCH_TIMEOUT_SECONDS:.0f}s"
            ),
            "regla V81: corredor repetido nunca convierte un mapa insuficiente en mapa terminado",
            "regla V81: el mapa sólo queda completo con tiempo, cobertura, salida y extensión en ambos ejes",
            "regla V81: durante retorno no hay antiatasco, reversa ni segundo dock; girar cerca de la base es búsqueda normal",
            "regla V81: si no aparece status=4 dentro de la ventana, se paran las ruedas y se informa fallo sin repetir dock",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

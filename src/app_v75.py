import threading
import time

import app_v74


class App(app_v74.App):
    """V75: origen real del sweep + cierre único + recuperación cancelable."""

    IDLE_FINISH_SECONDS = 12.0
    IDLE_FINISH_SAMPLES = 12

    def __init__(self):
        self._v75_recovery_generation = 0
        self._v75_origin_waiting = True
        self._v75_origin_samples = 0
        self._v75_origin_first_raw = None
        self._v75_idle_samples = 0
        self._v75_legacy_false_finishes_blocked = 0
        self._v75_recovery_cancellations = 0
        super().__init__()

    # ===================================================== origen de sesión
    def _v71_set_origin(self, xy, source):
        source_text = str(source or "")
        # V74 fijaba una lectura 10/24 anterior al START. El diagnóstico real
        # mostró (0,39) antes y ~ (59,58) al comenzar el sweep: esa muestra vieja
        # no pertenece al recorrido nuevo y no puede ser la base.
        if "antes de mapeo único V74" in source_text:
            return False
        return super()._v71_set_origin(xy, source)

    @staticmethod
    def _v75_distinct_path_xy(path):
        unique = []
        for point in path:
            if not isinstance(point, dict):
                continue
            try:
                xy = (float(point.get("x")), float(point.get("y")))
            except Exception:
                continue
            if not unique or xy != unique[-1]:
                unique.append(xy)
            if len(unique) >= 2:
                break
        return unique

    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return app_v74.app_v73.App._apply_map_state(self, state)

        active = bool(getattr(self, "mapping_active", False))
        if active and self._v71_session_origin_raw is None:
            path = [
                dict(point)
                for point in list(state.get("path") or [])
                if isinstance(point, dict)
            ]
            unique = self._v75_distinct_path_xy(path)
            self._v75_origin_samples = max(self._v75_origin_samples, len(unique))

            # Esperamos movimiento real del NUEVO sweep. Mientras tanto el robot
            # queda visualmente sobre la base (0,0), sin dibujar un salto falso.
            if len(unique) < 2:
                waiting = dict(state)
                waiting["path"] = []
                waiting["robot"] = {"x": 0.0, "y": 0.0, "angle": 0.0}
                waiting["charging_base"] = {"x": 0.0, "y": 0.0, "angle": 0.0}
                waiting["path_source"] = "V75 esperando dos posiciones reales del sweep"
                try:
                    self.local_map.set_robot(waiting["robot"])
                    self.local_map.set_charging_base(waiting["charging_base"])
                    self._render_maps()
                except Exception:
                    pass
                return None

            self._v75_origin_first_raw = tuple(unique[0])
            self._v71_set_origin(
                unique[0],
                "primera posición del nuevo sweep normal · V75",
            )
            self._v75_origin_waiting = False

        if active and self._v71_session_origin_raw is not None:
            self._v74_note_coverage(state.get("robot"))

        # Saltamos solamente el _apply_map_state de V74, que todavía podía fijar
        # el origen desde una pose cruda aislada. V73 conserva el consumo
        # incremental de 10/24 y todo el render/persistencia posterior.
        return app_v74.app_v73.App._apply_map_state(self, state)

    # ============================================ blindaje contra lógica vieja
    def _render_status(self, status):
        if (
            bool(getattr(self, "mapping_active", False))
            and bool(getattr(self, "_v74_normal_clean_started", False))
        ):
            # app_v6 heredado usa mapping_seen_moving + status 1/4 para cerrar
            # "Paso 2". V75 no tiene fases: neutralizamos exclusivamente esa
            # bandera durante el render de estado. El watcher V74/V75 decide el
            # fin real por su cuenta.
            self.mapping_seen_moving = False
            was_active = bool(self.mapping_active)
            result = super()._render_status(status)
            if was_active and not self._v74_finish_requested:
                if not bool(getattr(self, "mapping_active", False)):
                    self._v75_legacy_false_finishes_blocked += 1
                    self.mapping_active = True
                    self.mapping_phase = 2
                self.mapping_seen_moving = False
                self._sync_mapping_step_buttons()
            return result

        return super()._render_status(status)

    # ================================================ recuperación cancelable
    def _v75_invalidate_recovery(self):
        self._v75_recovery_generation += 1
        if bool(getattr(self, "_v73_recovery_active", False)):
            self._v75_recovery_cancellations += 1
        self._v73_recovery_active = False
        try:
            self._v73_pose_window.clear()
        except Exception:
            pass

    def _v75_recovery_valid(self, vacuum, mapping_serial, generation):
        return bool(
            vacuum is getattr(self, "vacuum", None)
            and int(mapping_serial) == int(getattr(self, "_v74_mapping_serial", -1))
            and int(generation) == int(self._v75_recovery_generation)
            and bool(getattr(self, "mapping_active", False))
            and bool(getattr(self, "_v74_watch_active", False))
            and not bool(getattr(self, "_v74_finish_requested", False))
        )

    def _v73_schedule_recovery(self, phase, reason):
        if int(phase or 0) != 2:
            return
        if self._v73_recovery_active or not self.vacuum:
            return
        if not bool(getattr(self, "mapping_active", False)):
            return
        if bool(getattr(self, "_v74_finish_requested", False)):
            return

        self._v73_recovery_active = True
        self._v73_last_recovery_at = time.monotonic()
        self._v73_last_recovery_reason = str(reason)
        self._v73_recovery_count += 1
        attempt = self._v73_recovery_count
        vacuum = self.vacuum
        mapping_serial = self._v74_mapping_serial

        self._v75_recovery_generation += 1
        generation = self._v75_recovery_generation

        if attempt > self.MAX_STALL_RECOVERIES:
            def abort_worker():
                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.25)
                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v73_stall_abort",
                    f"Última detección: {reason}",
                )

            threading.Thread(target=abort_worker, daemon=True).start()
            return

        def worker():
            try:
                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.35)

                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                vacuum.manual(4)
                time.sleep(0.80)

                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    try:
                        vacuum.manual(5)
                    except Exception:
                        pass
                    return
                vacuum.manual(5)
                time.sleep(0.20)

                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                turn = 2 if attempt % 2 else 3
                vacuum.manual(turn)
                time.sleep(0.65)

                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    try:
                        vacuum.manual(5)
                    except Exception:
                        pass
                    return
                vacuum.manual(5)
                time.sleep(0.25)

                # Revalidación crítica: jamás reiniciar un sweep de una sesión
                # que ya terminó, fue detenida o recibió volver-a-base.
                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    return
                vacuum.start_mapping_interior()

                if not self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    return

                self._post_ui(
                    "v73_stall_recovered",
                    attempt,
                    int(phase),
                    str(reason),
                )
            except Exception as exc:
                if self._v75_recovery_valid(vacuum, mapping_serial, generation):
                    try:
                        vacuum.manual(5)
                    except Exception:
                        pass
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    time.sleep(0.20)
                    try:
                        vacuum.dock()
                    except Exception:
                        pass
                    self._post_ui(
                        "v73_stall_recovery_error",
                        attempt,
                        int(phase),
                        str(exc).strip() or type(exc).__name__,
                    )

        threading.Thread(target=worker, daemon=True).start()

    # ============================================== fin único / retorno real
    def _handle_ui_event(self, kind, payload):
        if kind in (
            "v74_mapping_complete",
            "v74_mapping_start_error",
            "v73_stall_recovery_error",
            "v73_stall_abort",
        ):
            self._v75_invalidate_recovery()
        return super()._handle_ui_event(kind, payload)

    def finish_mapping(self):
        self._v75_invalidate_recovery()
        return super().finish_mapping()

    def dock(self):
        if bool(getattr(self, "mapping_active", False)):
            self._v75_invalidate_recovery()
            self._v74_finish_requested = True
            self._v74_finish_reason = "retorno manual solicitado"
        return super().dock()

    def _v74_watch_mapping_worker(self, vacuum, serial):
        return_samples = 0
        idle_samples = 0
        seen_moving = False

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
            if status in (5, 6, 7):
                seen_moving = True

            if self._v73_recovery_active:
                return_samples = 0
                idle_samples = 0
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            returning = seen_moving and fault in (None, 0) and status in (3, 4)
            return_samples = return_samples + 1 if returning else 0
            self._v74_return_samples = return_samples

            # status=1 puede aparecer brevemente durante STOP/manual del E10.
            # Sólo lo consideramos fin si queda estable un intervalo completo,
            # sin recuperación activa ni reinicio de movimiento.
            if seen_moving and fault in (None, 0) and status == 1:
                idle_samples += 1
            else:
                idle_samples = 0
            self._v75_idle_samples = idle_samples

            if return_samples >= self.RETURN_CONFIRM_SAMPLES:
                self._v74_finish_requested = True
                reason = (
                    "Mapeo terminado · el E10 completó la limpieza y está cargando."
                    if status == 4
                    else "Mapeo terminado · el E10 completó la limpieza y regresó a la base."
                )
                self._post_ui("v74_mapping_complete", serial, reason)
                return

            if idle_samples >= self.IDLE_FINISH_SAMPLES:
                self._v74_finish_requested = True
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v74_mapping_complete",
                    serial,
                    "Mapeo terminado · el E10 quedó inactivo de forma estable y fue enviado a la base.",
                )
                return

            time.sleep(self.STATUS_POLL_SECONDS)

    # ============================================================= sesión
    def _v74_reset_session(self):
        self._v75_invalidate_recovery()
        self._v75_origin_waiting = True
        self._v75_origin_samples = 0
        self._v75_origin_first_raw = None
        self._v75_idle_samples = 0
        self._v75_legacy_false_finishes_blocked = 0
        return super()._v74_reset_session()

    # ========================================================= diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V75 ACTIVO · origen post-START + cierre único + recovery token",
            "============================================================================",
            f"origen esperando movimiento real: {bool(self._v75_origin_waiting)} · muestras distintas={self._v75_origin_samples}",
            f"primer punto real usado como base: {self._v75_origin_first_raw!r}",
            f"origen sesión vigente: {self._v71_session_origin_raw!r}",
            f"status=1 estable: {self._v75_idle_samples}/{self.IDLE_FINISH_SAMPLES}",
            f"cierres falsos heredados bloqueados: {self._v75_legacy_false_finishes_blocked}",
            f"generación recovery: {self._v75_recovery_generation} · cancelaciones={self._v75_recovery_cancellations}",
            "regla V75: ninguna lectura 10/24 anterior al START puede fijar la base",
            "regla V75: se requieren dos posiciones distintas del nuevo sweep antes de dibujar movimiento",
            "regla V75: status=1 aislado no termina el mapa; la lógica vieja Paso 2 queda neutralizada",
            "regla V75: toda recuperación revalida sesión/estado antes de reiniciar el sweep",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

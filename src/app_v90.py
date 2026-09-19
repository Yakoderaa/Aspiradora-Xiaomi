import threading
import time

import app_v89


class App(app_v89.App):
    """V90: gate de arranque real antes de aceptar un retorno al dock.

    Corrige la carrera observada en V89: puntos 10/24 podían acumularse mientras
    el E10 todavía informaba status=4 y antes de que v74_mapping_started
    confirmara el START. V84 interpretaba esos puntos como salida+retorno y
    cerraba la sesión con tiempo 0.0 s.

    V90 exige, para un cierre automático por dock:
      1) START confirmado para el serial vigente.
      2) haber observado después un estado físico de limpieza 5/6/7.
      3) recién entonces un status=3/4 puede representar retorno real.

    Los puntos tempranos siguen disponibles para diagnóstico, pero nunca
    habilitan por sí solos el cierre de la sesión.
    """

    START_CONFIRM_TIMEOUT_MS = 60000

    def __init__(self):
        self._v90_start_confirmed = False
        self._v90_start_confirmed_at = None
        self._v90_start_serial = None
        self._v90_departure_confirmed = False
        self._v90_departure_confirmed_at = None
        self._v90_departure_source = None
        self._v90_prestart_points = 0
        self._v90_prestart_saved = 0
        self._v90_status4_prestart_blocks = 0
        self._v90_status4_nodeparture_blocks = 0
        self._v90_return_predeparture_blocks = 0
        self._v90_close_permissions = 0
        self._v90_start_timeouts = 0
        self._v90_last_gate_reason = "sin sesión V90"
        super().__init__()

    # ======================================================== ciclo de sesión
    def _v90_reset_gate(self):
        self._v90_start_confirmed = False
        self._v90_start_confirmed_at = None
        self._v90_start_serial = None
        self._v90_departure_confirmed = False
        self._v90_departure_confirmed_at = None
        self._v90_departure_source = None
        self._v90_prestart_points = 0
        self._v90_prestart_saved = 0
        self._v90_last_gate_reason = "esperando START de la sesión actual"

    def _v74_reset_session(self):
        self._v90_reset_gate()
        return super()._v74_reset_session()

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if bool(getattr(self, "mapping_active", False)):
            serial = int(getattr(self, "_v74_mapping_serial", 0) or 0)
            try:
                self.after(
                    self.START_CONFIRM_TIMEOUT_MS,
                    lambda s=serial: self._v90_check_start_timeout(s),
                )
            except Exception:
                pass
        return result

    def _v90_snapshot_point_count(self):
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        return len(list((snapshot or {}).get("points") or []))

    def _v90_saved_count(self):
        try:
            return int(self._v73_phase_saved.get(2, 0) or 0)
        except Exception:
            return 0

    def _v90_confirm_start(self, serial):
        serial = int(serial)
        current = int(getattr(self, "_v74_mapping_serial", 0) or 0)
        if serial != current:
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False

        self._v90_start_confirmed = True
        self._v90_start_confirmed_at = time.monotonic()
        self._v90_start_serial = serial
        self._v90_prestart_points = self._v90_snapshot_point_count()
        self._v90_prestart_saved = self._v90_saved_count()
        self._v90_departure_confirmed = False
        self._v90_departure_confirmed_at = None
        self._v90_departure_source = None
        self._v90_last_gate_reason = (
            "START confirmado; esperando salida física status 5/6/7"
        )
        return True

    def _v90_mark_departure(self, source):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if not bool(self._v90_start_confirmed):
            return False
        if self._v90_departure_confirmed:
            return True

        self._v90_departure_confirmed = True
        self._v90_departure_confirmed_at = time.monotonic()
        self._v90_departure_source = str(source or "estado de limpieza")
        self._v90_last_gate_reason = (
            "salida física confirmada; retorno al dock ya puede cerrar la sesión"
        )
        # Un dock previo al START nunca debe quedar pegado a la nueva salida.
        self._v84_dock_latched = False
        return True

    def _v90_note_physical_status(self, physical, source="status UI"):
        try:
            physical = int(physical)
        except Exception:
            return False
        if (
            bool(getattr(self, "mapping_active", False))
            and bool(self._v90_start_confirmed)
            and physical in (5, 6, 7)
        ):
            return self._v90_mark_departure(
                f"{source}: status={physical}"
            )
        return False

    def _v90_check_start_timeout(self, serial):
        serial = int(serial)
        if serial != int(getattr(self, "_v74_mapping_serial", 0) or 0):
            return
        if not bool(getattr(self, "mapping_active", False)):
            return
        if bool(self._v90_start_confirmed):
            return

        self._v90_start_timeouts += 1
        self._v90_last_gate_reason = (
            "timeout: START no confirmado dentro de 60 s"
        )
        self._v74_watch_active = False
        self._v74_finish_requested = True
        self._v74_finish_reason = (
            "No se confirmó el inicio físico del mapeo dentro de 60 s. "
            "La sesión se canceló sin marcarla como mapeo incompleto."
        )
        self._v73_session_phase = 0
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False

        try:
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(self._v74_finish_reason)
        except Exception:
            pass

        vacuum = getattr(self, "vacuum", None)
        if vacuum is not None:
            def worker():
                try:
                    vacuum.stop()
                except Exception:
                    pass
            threading.Thread(target=worker, daemon=True).start()

    # ======================================================= eventos / status
    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started" and payload:
            try:
                self._v90_confirm_start(int(payload[0]))
            except Exception:
                pass
        elif kind == "v74_mapping_start_error":
            self._v90_last_gate_reason = "START rechazado/error de arranque"
        return super()._handle_ui_event(kind, payload)

    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))
        self._v90_note_physical_status(physical, "status UI")
        return super()._render_status(status)

    # ========================================== cierre físico protegido V84
    def _v84_has_mapping_motion(self):
        if not bool(getattr(self, "mapping_active", False)):
            return super()._v84_has_mapping_motion()
        # En una sesión V90, muchos puntos 10/24 anteriores al START no son
        # evidencia suficiente de que el robot salió físicamente del dock.
        return bool(
            self._v90_start_confirmed
            and self._v90_departure_confirmed
        )

    def _v84_should_finalize_dock(self):
        if not bool(getattr(self, "mapping_active", False)):
            return super()._v84_should_finalize_dock()

        if not bool(self._v90_start_confirmed):
            self._v90_status4_prestart_blocks += 1
            self._v90_last_gate_reason = (
                "status=4 bloqueado: START todavía no confirmado"
            )
            return False

        if not bool(self._v90_departure_confirmed):
            self._v90_status4_nodeparture_blocks += 1
            self._v90_last_gate_reason = (
                "status=4 bloqueado: todavía no hubo status 5/6/7 "
                "posterior al START"
            )
            return False

        allowed = bool(super()._v84_should_finalize_dock())
        if allowed:
            self._v90_close_permissions += 1
            self._v90_last_gate_reason = (
                "cierre permitido: START + salida física + retorno"
            )
        return allowed

    def _v84_note_returning(self, source):
        if bool(getattr(self, "mapping_active", False)):
            if not self._v90_start_confirmed or not self._v90_departure_confirmed:
                self._v90_return_predeparture_blocks += 1
                self._v84_physical_status = 3
                self._v74_last_status = 3
                self._v81_dock_last_status = 3
                self._v84_returning = False
                self._v90_last_gate_reason = (
                    "status=3 observado pero ignorado como retorno: "
                    "falta salida física post-START"
                )
                return False
        return super()._v84_note_returning(source)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()

        start_age = None
        if self._v90_start_confirmed_at is not None:
            start_age = max(0.0, now - self._v90_start_confirmed_at)

        departure_age = None
        if self._v90_departure_confirmed_at is not None:
            departure_age = max(
                0.0,
                now - self._v90_departure_confirmed_at,
            )

        current_points = self._v90_snapshot_point_count()
        current_saved = self._v90_saved_count()
        post_start_points = max(
            0,
            current_points - int(self._v90_prestart_points or 0),
        )
        post_start_saved = max(
            0,
            current_saved - int(self._v90_prestart_saved or 0),
        )

        lines = [
            "DIAGNÓSTICO V90 ACTIVO · START real + salida física antes del cierre",
            "=====================================================================",
            (
                "gate sesión: "
                f"mapping_active={bool(getattr(self, 'mapping_active', False))} · "
                f"serial={getattr(self, '_v74_mapping_serial', None)} · "
                f"START={bool(self._v90_start_confirmed)} · "
                f"edad START={start_age if start_age is not None else '—'}"
            ),
            (
                "salida post-START: "
                f"confirmada={bool(self._v90_departure_confirmed)} · "
                f"fuente={self._v90_departure_source or '—'} · "
                f"edad={departure_age if departure_age is not None else '—'}"
            ),
            (
                "puntos alrededor del START: "
                f"pre={self._v90_prestart_points} / guardados={self._v90_prestart_saved} · "
                f"post={post_start_points} / guardados={post_start_saved}"
            ),
            (
                "cierres bloqueados: "
                f"status4 pre-START={self._v90_status4_prestart_blocks} · "
                f"status4 sin salida={self._v90_status4_nodeparture_blocks} · "
                f"status3 sin salida={self._v90_return_predeparture_blocks}"
            ),
            (
                "cierres permitidos="
                f"{self._v90_close_permissions} · "
                f"timeouts START={self._v90_start_timeouts}"
            ),
            f"último gate: {self._v90_last_gate_reason}",
            "regla V90: puntos 10/24 por sí solos nunca prueban salida física del dock",
            "regla V90: status=4 previo al START o previo a un status 5/6/7 no puede cerrar el mapeo",
            "regla V90: sólo una salida física observada después del START habilita un retorno status=3/4",
            "regla V90: si START no se confirma en 60 s, el intento se cancela sin etiquetarlo como mapeo incompleto",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v89.app_v88.app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v89.app_v88.app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

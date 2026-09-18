import threading
import time

import app_v83
import app_v9


class App(app_v83.App):
    """V84: estado físico autoritativo del dock + cierre sin carreras."""

    def __init__(self):
        self._v84_physical_status = None
        self._v84_returning = False
        self._v84_dock_latched = False
        self._v84_dock_source = None
        self._v84_dock_confirmed_at = None
        self._v84_recovery_invalidations = 0
        self._v84_timeout_overrides = 0
        self._v84_robot_snaps = 0
        self._v84_initial_status4_ignored = 0
        self._v84_stale_robot_before_dock = None
        self._v84_last_close_reason = None
        super().__init__()

    def _v74_reset_session(self):
        self._v84_physical_status = None
        self._v84_returning = False
        self._v84_dock_latched = False
        self._v84_dock_source = None
        self._v84_dock_confirmed_at = None
        self._v84_recovery_invalidations = 0
        self._v84_timeout_overrides = 0
        self._v84_robot_snaps = 0
        self._v84_initial_status4_ignored = 0
        self._v84_stale_robot_before_dock = None
        self._v84_last_close_reason = None
        return super()._v74_reset_session()

    # ================================================= estado físico único
    def _v84_has_mapping_motion(self):
        try:
            saved = int(self._v73_phase_saved.get(2, 0) or 0)
        except Exception:
            saved = 0
        departure = float(
            getattr(self, "_v71_session_max_departure", 0.0) or 0.0
        )
        return saved >= 3 or departure >= 0.20

    def _v84_should_finalize_dock(self):
        if not bool(getattr(self, "mapping_active", False)):
            return True
        if bool(getattr(self, "_v74_finish_requested", False)):
            return True
        if bool(self._v84_returning):
            return True
        return self._v84_has_mapping_motion()

    def _v84_cancel_recovery(self, reason):
        before = int(getattr(self, "_v75_recovery_generation", 0) or 0)
        try:
            self._v75_invalidate_recovery()
        except Exception:
            try:
                self._v73_recovery_active = False
                self._v73_pose_window.clear()
            except Exception:
                pass
        after = int(getattr(self, "_v75_recovery_generation", before) or before)
        if after != before:
            self._v84_recovery_invalidations += 1
        try:
            self._v73_repeat_triggered = False
        except Exception:
            pass
        return str(reason or "")

    def _v84_mark_dock_authoritative(self, source, final=True):
        self._v84_physical_status = 4
        self._v74_last_status = 4
        self._v81_dock_last_status = 4

        if not final:
            return False

        first = not bool(self._v84_dock_latched)
        if bool(getattr(self, "_v81_dock_timeout", False)):
            self._v84_timeout_overrides += 1

        self._v84_dock_latched = True
        self._v84_returning = False
        self._v84_dock_source = str(source or "status=4")
        if first or self._v84_dock_confirmed_at is None:
            self._v84_dock_confirmed_at = time.monotonic()
            self._v84_cancel_recovery("status=4 autoritativo")

        # Invariante V84: estos estados nunca pueden coexistir con status=4.
        self._v81_dock_confirmed = True
        self._v81_dock_timeout = False
        self._v73_dock_failed = False
        self._v73_dock_guard_active = False
        return first

    def _v84_note_returning(self, source):
        previous = self._v84_physical_status
        self._v84_physical_status = 3
        self._v74_last_status = 3
        self._v81_dock_last_status = 3
        if previous != 3 or not self._v84_returning:
            self._v84_returning = True
            self._v84_dock_latched = False
            self._v84_cancel_recovery(
                f"status=3 retorno · {source}"
            )

    def _v84_snap_robot_to_dock(self, force=False):
        local_map = getattr(self, "local_map", None)
        if local_map is None:
            return False

        changed = bool(force)
        try:
            snapshot = local_map.snapshot() or {}
        except Exception:
            snapshot = {}

        robot = snapshot.get("robot")
        base = snapshot.get("charging_base")

        if isinstance(robot, dict):
            try:
                rx = float(robot.get("x", 0.0) or 0.0)
                ry = float(robot.get("y", 0.0) or 0.0)
                if self._v84_stale_robot_before_dock is None and (
                    abs(rx) > 1e-9 or abs(ry) > 1e-9
                ):
                    self._v84_stale_robot_before_dock = (rx, ry)
                if abs(rx) > 1e-9 or abs(ry) > 1e-9:
                    changed = True
            except Exception:
                changed = True
        else:
            changed = True

        if isinstance(base, dict):
            try:
                if (
                    abs(float(base.get("x", 0.0) or 0.0)) > 1e-9
                    or abs(float(base.get("y", 0.0) or 0.0)) > 1e-9
                ):
                    changed = True
            except Exception:
                changed = True
        else:
            changed = True

        try:
            local_map.set_charging_base(
                {"x": 0.0, "y": 0.0, "angle": 0.0}
            )
            local_map.set_robot(
                {"x": 0.0, "y": 0.0, "angle": 0.0}
            )
        except Exception:
            return False

        if changed:
            self._v84_robot_snaps += 1
            try:
                self._render_maps()
            except Exception:
                pass
        return True

    def _v84_close_mapping_on_dock(self):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if not self._v84_has_mapping_motion():
            # status=4 durante la captura inicial del dock es normal.
            return False

        try:
            state = self._v81_completion_state()
        except Exception:
            state = {"ready": False, "missing": ["estado de cobertura no disponible"]}

        ready = bool(state.get("ready"))
        missing = list(state.get("missing") or [])

        self._v74_watch_active = False
        self._v74_finish_requested = True
        self._v73_session_phase = 0
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = bool(ready)

        if ready:
            reason = "Mapeo terminado · carga confirmada físicamente en la base."
            self._v82_status4_session_closes += 1
            self._v81_incomplete_reason = None
        else:
            reason = (
                "Mapeo incompleto: el E10 ya está físicamente en la base y "
                "cargando; la sesión se cerró sin inventar cobertura"
            )
            if missing:
                reason += " (" + ", ".join(missing) + ")"
            reason += "."
            self._v81_incomplete_reason = reason

        self._v74_finish_reason = reason
        self._v84_last_close_reason = reason
        self._v84_cancel_recovery("cierre físico en dock")

        try:
            self._sync_mapping_step_buttons()
        except Exception:
            pass

        try:
            threading.Thread(
                target=self._restore_cleaning_preferences,
                daemon=True,
            ).start()
        except Exception:
            pass

        try:
            self._set_banner(reason)
        except Exception:
            pass

        if ready:
            try:
                self.after(100, self._v70_notify_mapping_complete)
            except Exception:
                pass
        return True

    def _v84_authoritative_dock_ui(self, source):
        self._v84_mark_dock_authoritative(source, final=True)
        self._v84_close_mapping_on_dock()
        self._v84_snap_robot_to_dock(force=True)

    # ================================================== status principal UI
    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))

        if physical == 3:
            self._v84_note_returning("status UI")

        elif physical == 4:
            final = self._v84_should_finalize_dock()
            if final:
                self._v84_authoritative_dock_ui("status UI")
            else:
                if self._v84_physical_status != 4:
                    self._v84_initial_status4_ignored += 1
                self._v84_mark_dock_authoritative(
                    "status inicial sobre dock",
                    final=False,
                )
                self._v84_snap_robot_to_dock(force=False)

        elif physical in (5, 6, 7):
            self._v84_physical_status = physical
            self._v74_last_status = physical
            self._v81_dock_last_status = physical
            self._v84_returning = False
            # El robot realmente salió del dock: liberamos el pin visual.
            self._v84_dock_latched = False

        elif physical is not None:
            self._v84_physical_status = physical
            self._v74_last_status = physical

        result = super()._render_status(status)

        if physical == 4 and self._v84_should_finalize_dock():
            self._v84_snap_robot_to_dock(force=False)
        return result

    # ======================================= recovery nunca durante retorno/base
    def _v83_recovery_gate(self, reason, now=None):
        if self._v84_dock_latched or self._v84_returning:
            kind = self._v83_recovery_kind(reason)
            return False, {
                "kind": kind,
                "reason": (
                    "V84: retorno/base física activa; recovery deshabilitado"
                ),
                "no_new": 0.0,
                "cooldown": 0.0,
            }
        return super()._v83_recovery_gate(reason, now=now)

    def _v75_recovery_valid(self, vacuum, mapping_serial, generation):
        if self._v84_dock_latched or self._v84_returning:
            return False
        return super()._v75_recovery_valid(
            vacuum,
            mapping_serial,
            generation,
        )

    def dock(self):
        if not self._v84_dock_latched:
            self._v84_note_returning("orden manual")
        return super().dock()

    # ====================================== guard de dock sin carrera de timeout
    def _v73_start_dock_guard(self, reason):
        if self._v84_dock_latched:
            self._v81_dock_confirmed = True
            self._v81_dock_timeout = False
            self._v73_dock_failed = False
            self._v73_dock_guard_active = False
            return
        return super()._v73_start_dock_guard(reason)

    def _v81_dock_monitor_worker(self, vacuum, serial, reason):
        deadline = time.monotonic() + self.DOCK_SEARCH_TIMEOUT_SECONDS

        def read_state():
            state = self._v69_read_base_state(vacuum)
            status = self._v67_int(state.get("status"))
            fault = self._v67_int(state.get("fault"))
            raw_robot = state.get("robot")
            distance = self._v71_raw_distance_to_origin(raw_robot)
            self._v81_dock_last_status = status
            self._v81_dock_last_distance = distance
            self._v84_physical_status = status
            if status is not None:
                self._v74_last_status = status
            return status, fault, distance

        def confirm(source):
            self._v84_mark_dock_authoritative(source, final=True)
            self._post_ui(
                "v84_dock_authoritative",
                serial,
                str(reason),
                str(source),
            )

        while time.monotonic() < deadline:
            if serial != self._v73_dock_guard_serial:
                return
            if vacuum is not getattr(self, "vacuum", None):
                return
            if self._v84_dock_latched:
                return

            try:
                status, fault, distance = read_state()
            except Exception:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            if status == 3:
                self._v84_note_returning("dock guard")

            if (
                distance is not None
                and distance <= self.DOCK_NEAR_RADIUS_METERS
                and fault in (None, 0)
            ):
                self._v81_dock_near_samples += 1

            # V84: una sola lectura 4 es suficiente. No existe un segundo
            # muestreo que pueda quedar del otro lado del deadline.
            if status == 4:
                confirm("dock guard status=4")
                return

            time.sleep(self.BASE_POLL_SECONDS)

        if serial != self._v73_dock_guard_serial:
            return
        if self._v84_dock_latched:
            return

        # Relectura final obligatoria ANTES de tocar las ruedas. Esto elimina
        # la carrera observada en V83: status=4 no puede coexistir con timeout.
        try:
            status, _fault, _distance = read_state()
            if status == 4:
                confirm("relectura final status=4")
                return
        except Exception:
            pass

        if self._v84_dock_latched:
            return

        try:
            vacuum.stop()
        except Exception:
            pass

        if self._v84_dock_latched:
            return

        try:
            vacuum.manual(5)
        except Exception:
            pass

        if self._v84_dock_latched:
            return

        self._v81_dock_timeout = True
        self._v81_dock_confirmed = False
        self._v73_dock_failed = True
        self._v73_dock_guard_active = False
        self._post_ui(
            "v81_dock_timeout",
            serial,
            reason,
            self._v81_dock_last_status,
            self._v81_dock_last_distance,
        )

    # ========================================================= eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v84_dock_authoritative":
            _serial, reason, source = payload
            self._v84_authoritative_dock_ui(source)
            try:
                self._set_banner(
                    "Base confirmada: status=4 autoritativo. "
                    "Retorno cerrado, antiatasco cancelado y robot fijado "
                    "visualmente al dock."
                )
            except Exception:
                pass
            return

        if kind == "v81_dock_timeout":
            if (
                self._v84_dock_latched
                or self._v84_physical_status == 4
                or self._v81_dock_last_status == 4
            ):
                self._v84_timeout_overrides += 1
                self._v84_authoritative_dock_ui(
                    "timeout heredado anulado por status=4"
                )
                return

        if kind == "v81_dock_confirmed":
            self._v84_authoritative_dock_ui(
                "confirmación heredada V81"
            )

        if kind in ("v74_mapping_complete", "v81_mapping_incomplete"):
            self._v84_cancel_recovery(
                f"evento de cierre {kind}"
            )

        result = super()._handle_ui_event(kind, payload)

        if self._v84_dock_latched:
            self._v84_snap_robot_to_dock(force=False)
        return result

    # ================================ mapa: status=4 gana a 10/24 obsoleto
    def _apply_map_state(self, state):
        if self._v84_dock_latched and isinstance(state, dict):
            docked = dict(state)
            docked["path"] = []
            docked["robot"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }
            docked["charging_base"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }
            docked["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V84 status=4 fija robot al dock"
            )
            return app_v9.App._apply_map_state(self, docked)

        return super()._apply_map_state(state)

    def start_new_mapping(self):
        # Al comenzar una sesión nueva se permite que el E10 parta físicamente
        # desde la base. Un status=4 inicial no significa "fin de mapa".
        self._v84_dock_latched = False
        self._v84_returning = False
        self._v84_physical_status = None
        return super().start_new_mapping()

    # ========================================================= texto/diag
    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · estado físico unificado · status=4 "
                        "autoritativo · antiatasco bloqueado en retorno"
                    )
                )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        # Sanitizamos antes de pedir diagnósticos heredados: V81 jamás debe
        # imprimir status=4 junto con timeout=True/confirmado=False.
        if self._v84_physical_status == 4 or self._v84_dock_latched:
            self._v81_dock_last_status = 4
            self._v81_dock_confirmed = True
            self._v81_dock_timeout = False
            self._v73_dock_failed = False
            self._v73_dock_guard_active = False

        inherited = super()._diagnostic_text()
        confirmed_age = None
        if self._v84_dock_confirmed_at is not None:
            confirmed_age = max(
                0.0,
                time.monotonic() - float(self._v84_dock_confirmed_at),
            )

        lines = [
            "DIAGNÓSTICO V84 ACTIVO · dock autoritativo + cierre físico unificado",
            "======================================================================",
            (
                "estado físico V84: "
                f"status={self._v84_physical_status} · retorno={self._v84_returning} · "
                f"dock fijado={self._v84_dock_latched} · fuente="
                f"{self._v84_dock_source or '—'}"
            ),
            (
                "dock final: confirmado="
                f"{bool(getattr(self, '_v81_dock_confirmed', False))} · "
                f"timeout={bool(getattr(self, '_v81_dock_timeout', False))} · "
                f"fallo={bool(getattr(self, '_v73_dock_failed', False))} · "
                "edad="
                + (
                    f"{confirmed_age:.1f}s"
                    if confirmed_age is not None
                    else "—"
                )
            ),
            (
                "cierres: recoveries invalidados="
                f"{self._v84_recovery_invalidations} · timeouts anulados="
                f"{self._v84_timeout_overrides} · snaps robot→dock="
                f"{self._v84_robot_snaps}"
            ),
            (
                "status=4 iniciales no tratados como fin: "
                f"{self._v84_initial_status4_ignored}"
            ),
            (
                "última pose visual obsoleta antes del dock: "
                f"{self._v84_stale_robot_before_dock!r}"
            ),
            (
                "último cierre por dock: "
                f"{self._v84_last_close_reason or '—'}"
            ),
            "regla V84: una sola lectura status=4 confirma físicamente el dock y anula cualquier timeout pendiente",
            "regla V84: status=3 o status=4 invalida recovery/antiatasco y ningún worker puede reiniciar el sweep durante el retorno",
            "regla V84: con status=4 el robot se renderiza exactamente en la base (0,0), aunque 10/24 conserve una pose vieja",
            "regla V84: status=4 inicial antes de que el robot salga del dock no finaliza una sesión nueva",
            "regla V84: V74, V81, V83 y el render comparten el mismo estado físico V84",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v9._save_crash_log(traceback.format_exc())
        raise

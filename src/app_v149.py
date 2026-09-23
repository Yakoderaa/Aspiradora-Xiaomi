import threading
import time

import app_v148
import app_v9


class App(app_v148.App):
    """V149-IA: EDGE adaptativo -> whole-home V123 en la misma sesión."""

    GLOBAL_AFTER_FAILED_ESCAPES = 2

    def __init__(self):
        self._v149_global_requested = False
        self._v149_global_started = False
        self._v149_global_failed = False
        self._v149_global_reason = None
        self._v149_global_diag = {}
        self._v149_transition_count = 0
        self._v149_fallback_dock_sent = False
        super().__init__()

    def _v147_reset_state(self):
        result = super()._v147_reset_state()
        self._v149_global_requested = False
        self._v149_global_started = False
        self._v149_global_failed = False
        self._v149_global_reason = None
        self._v149_global_diag = {}
        self._v149_transition_count = 0
        self._v149_fallback_dock_sent = False
        return result

    def _v149_can_switch_global(self, serial, metrics):
        return bool(
            serial == int(getattr(self, "_v74_mapping_serial", -1))
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
            and not bool(getattr(self, "_v145_session_latched", False))
            and not bool(getattr(self, "_v145_reset_guard", False))
            and bool((metrics or {}).get("v148_persistent_strip"))
            and str((metrics or {}).get("pattern") or "") == "oscillation_corridor"
        )

    def _v149_request_global_transition(self, serial, metrics, reason):
        if self._v149_global_requested:
            return True
        if not self._v149_can_switch_global(serial, metrics):
            return False

        self._v149_global_requested = True
        self._v149_global_reason = str(reason)
        self._v149_global_diag = {
            "requested": True,
            "started": False,
            "failed": False,
            "serial": int(serial),
            "reason": str(reason),
            "escape_total": int(getattr(self, "_v147_escape_total", 0) or 0),
            "escape_consecutive": int(
                getattr(self, "_v147_escape_consecutive", 0) or 0
            ),
            "pattern": str((metrics or {}).get("pattern") or ""),
            "ratio_2d": (metrics or {}).get("v148_2d_ratio"),
            "reversals": (metrics or {}).get("oscillation_reversals"),
            "path_m": (metrics or {}).get("path_m"),
            "arm_new_map_called": False,
            "route": "V123 whole-home 7/3 ['',0,1] sobre el mismo build-map",
        }
        self._v141_log(
            "V149 solicitó transición EDGE -> whole-home",
            **self._v149_global_diag,
        )
        self._post_ui(
            "v149_switch_global",
            int(serial),
            dict(metrics or {}),
            str(reason),
        )
        return True

    def _v147_schedule_escape(self, serial, metrics):
        # V148 ya demostró que repetir EDGE por tercera vez no aporta
        # expansión 2D y puede dejar sweep_type en un estado intermedio.
        # Después de dos escapes realmente fallidos cambiamos de estrategia,
        # manteniendo el único build-map de la sesión.
        if (
            int(getattr(self, "_v147_escape_consecutive", 0) or 0)
            >= self.GLOBAL_AFTER_FAILED_ESCAPES
            and self._v149_can_switch_global(serial, metrics)
        ):
            return self._v149_request_global_transition(
                serial,
                metrics,
                "dos escapes EDGE sin expansión 2D real",
            )

        if self._v149_global_requested:
            return True
        return super()._v147_schedule_escape(serial, metrics)

    def _v147_request_abort(self, serial, metrics, reason):
        # Antes del auto-abort de V147/V148 damos una sola oportunidad a la
        # estrategia global. Esto también cubre el error observado en V148:
        # EDGE no confirmó sweep_type=2 al intentar el tercer reacople.
        if self._v149_can_switch_global(serial, metrics):
            if self._v149_request_global_transition(
                serial,
                metrics,
                "EDGE agotó sus escapes; cambiar a whole-home antes de abortar",
            ):
                return
        return super()._v147_request_abort(serial, metrics, reason)

    def _v149_start_global_now(self, serial, metrics, reason):
        vacuum = getattr(self, "vacuum", None)
        if not self._v149_can_switch_global(serial, metrics):
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "gate físico V149 rechazó la transición",
            })
            return False

        if vacuum is None:
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "robot desconectado",
            })
            return False

        self._v149_transition_count += 1
        self._v147_escape_active = False
        self._v147_escape_awaiting_validation = False
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v143_bad_pattern_streak = 0

        self._set_banner(
            "V149: EDGE quedó atrapado en una franja 1D · "
            "cambiando a exploración global sobre el MISMO mapa Xiaomi…"
        )

        accepted = self._v121_request_phase2(
            vacuum,
            int(serial),
            source="V149: " + str(reason),
            sweep_type=2,
        )
        self._v149_global_diag["phase2_request_accepted"] = bool(accepted)

        if not accepted:
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "la capa V121/V137 rechazó la solicitud whole-home",
            })
            self._v141_log(
                "V149 transición global rechazada",
                serial=int(serial),
                reason=str(reason),
            )
            return False

        self._v141_log(
            "V149 transición global aceptada por la app",
            serial=int(serial),
            reason=str(reason),
            arm_new_map_called=False,
        )
        return True

    def _v149_safe_return_after_global_failure(self, error):
        if self._v149_fallback_dock_sent:
            return
        self._v149_fallback_dock_sent = True

        try:
            self._v145_latch_session(
                "v149-global-failed",
                close_mapping=True,
            )
        except Exception:
            self.mapping_active = False
            self.mapping_phase = 0

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return

        def worker():
            dock_error = None
            try:
                vacuum.dock()
            except Exception as exc:
                dock_error = str(exc).strip() or type(exc).__name__
            self._v141_log(
                "V149 regreso seguro tras fallo whole-home",
                error=str(error),
                dock_error=dock_error,
            )

        threading.Thread(
            target=worker,
            name="AspiradoraV149GlobalFailureDock",
            daemon=True,
        ).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "v149_switch_global":
            serial = int(payload[0])
            metrics = dict(payload[1] or {})
            reason = str(payload[2])
            ok = self._v149_start_global_now(
                serial,
                metrics,
                reason,
            )
            if not ok:
                error = str(
                    self._v149_global_diag.get("error")
                    or "transición whole-home rechazada"
                )
                self._set_banner(
                    "V149 no pudo iniciar la exploración global · "
                    "cerrando sesión y volviendo a la base."
                )
                self._v149_safe_return_after_global_failure(error)
            return None

        result = super()._handle_ui_event(kind, payload)

        if kind == "v121_phase2_started":
            serial = int(payload[0]) if payload else -1
            if (
                self._v149_global_requested
                and serial == int(getattr(self, "_v74_mapping_serial", -1))
            ):
                diag = dict(payload[1] or {}) if len(payload) > 1 else {}
                self._v149_global_started = True
                self._v149_global_failed = False
                self._v149_global_diag.update({
                    "started": True,
                    "failed": False,
                    "phase2": diag,
                    "confirmed_at": round(time.monotonic(), 3),
                })
                self._v147_escape_consecutive = 0
                self._v147_oscillation_streak = 0
                self._v147_oscillation_votes = []
                self._set_banner(
                    "V149: exploración global confirmada · Fase 2/2 activa "
                    "sobre el mismo mapa Xiaomi. Dejá que el E10 continúe."
                )
                self._v141_log(
                    "V149 whole-home confirmado",
                    serial=serial,
                    status_after=diag.get("status_after"),
                    sweep_type_after=diag.get("sweep_type_after"),
                )
            return result

        if kind == "v121_phase2_error" and self._v149_global_requested:
            diag = dict(payload[1] or {}) if len(payload) > 1 else {}
            error = str(diag.get("error") or "whole-home no confirmado")
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "started": False,
                "failed": True,
                "phase2": diag,
                "error": error,
            })
            self._set_banner(
                "V149: el E10 rechazó la exploración global · "
                "cerrando sesión y volviendo a la base."
            )
            self._v149_safe_return_after_global_failure(error)
            return result

        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V149-IA ACTIVO · EDGE adaptativo -> whole-home",
            "==============================================================",
            f"global solicitado={self._v149_global_requested}",
            f"global iniciado={self._v149_global_started}",
            f"global falló={self._v149_global_failed}",
            f"transiciones={self._v149_transition_count}",
            f"motivo transición={self._v149_global_reason or '—'}",
            f"diag global={self._v149_global_diag or '—'}",
            f"regreso seguro por fallo={self._v149_fallback_dock_sent}",
            "regla V149: dos escapes EDGE fallidos terminan la estrategia EDGE, no el mapa",
            "regla V149: la siguiente estrategia es whole-home V123 7/3 ['',0,1]",
            "regla V149: la transición NO ejecuta arm_new_map y conserva la misma sesión Xiaomi",
            "regla V149: 2/3 sólo puede aparecer si V123 detecta que el robot sigue en status=4",
            "regla V149: el tercer reinicio EDGE queda eliminado",
            "regla V149: si whole-home no confirma movimiento físico, recién entonces cierra y vuelve a base",
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

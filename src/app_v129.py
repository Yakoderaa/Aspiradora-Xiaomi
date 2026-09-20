import time

import app_v128
import app_v9


class App(app_v128.App):
    """V129: Fase 2 monitorizada, sin comandos automáticos de recovery."""

    PHASE2_RECOVERY_NO_NEW_SECONDS = 75.0
    PHASE2_RECOVERY_COOLDOWN_SECONDS = 90.0
    PHASE2_RECOVERY_MAX = 50

    def __init__(self):
        self._v129_phase2_stuck_detections = 0
        self._v129_phase2_idle_notices = 0
        self._v129_phase2_last_detection = {}
        self._v129_phase2_idle_latched = False
        super().__init__()

    def _v127_try_phase2_recovery(self, reason):
        """V129: detectar y avisar; jamás mandar una orden al E10."""
        allowed, detail = self._v127_phase2_recovery_allowed(reason)
        if not allowed:
            return False

        now = time.monotonic()
        self._v127_phase2_recoveries += 1
        self._v127_phase2_recovery_last_at = now
        self._v127_phase2_recovery_last_reason = str(detail)
        self._v74_last_discovery_at = now

        result = {
            "attempt": int(self._v127_phase2_recoveries),
            "reason": str(detail),
            "success": False,
            "resume": None,
            "error": None,
            "strategy": "PASSIVE ONLY · no motor command",
            "commands_sent": 0,
        }
        self._v127_phase2_recovery_last_result = dict(result)
        self._v129_phase2_stuck_detections += 1
        self._v129_phase2_last_detection = dict(result)

        try:
            self._v77_corridor_samples.clear()
        except Exception:
            pass

        self._post_ui("v129_phase2_stuck_detected", result)
        return True

    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))
        result = super()._render_status(status)

        if (
            physical == 1
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 2
        ):
            if not self._v129_phase2_idle_latched:
                self._v129_phase2_idle_latched = True
                self._v129_phase2_idle_notices += 1
                self._post_ui(
                    "v129_phase2_idle",
                    self._v129_phase2_idle_notices,
                )
        elif physical in (5, 6, 7):
            self._v129_phase2_idle_latched = False

        return result

    def _handle_ui_event(self, kind, payload):
        if kind == "v129_phase2_stuck_detected":
            result = dict(payload[0]) if payload else {}
            self._set_banner(
                "Fase 2: patrón repetitivo detectado · V129 no envía "
                "ningún comando automático. Si el E10 se detiene, usá "
                "Volver a la base."
            )
            return None

        if kind == "v129_phase2_idle":
            self._set_banner(
                "Fase 2: el E10 quedó en espera durante el mapeo. "
                "No se enviaron comandos automáticos; podés usar "
                "Volver a la base."
            )
            return None

        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V129 ACTIVO · antiatasco pasivo de Fase 2",
            "=====================================================",
            (
                "detecciones repetición="
                f"{self._v129_phase2_stuck_detections} · idle detectados="
                f"{self._v129_phase2_idle_notices}"
            ),
            f"última detección={self._v129_phase2_last_detection or '—'}",
            "regla V129: durante Fase 2 el antiatasco no envía ninguna orden al robot",
            "regla V129: prohibidos STOP/manual/7-3/2-3/2-1 automáticos por atasco",
            "regla V129: status=1 durante mapeo sólo genera aviso; el usuario decide si vuelve a base",
            "regla V129: V123, mapa V128 y regreso asistido permanecen sin cambios",
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

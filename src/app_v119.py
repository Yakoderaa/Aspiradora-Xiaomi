import time

import app_v118
import app_v9


class App(app_v118.App):
    """V119: un heurístico nunca puede declarar completa una vivienda."""

    def __init__(self):
        self._v119_no_new_finishes_suppressed = 0
        self._v119_corridor_finishes_suppressed = 0
        self._v119_corridor_recoveries_suppressed = 0
        self._v119_mapping_status_samples_ignored_by_v118 = 0
        self._v119_last_suppressed_reason = "—"
        super().__init__()

    def _v74_request_finish_for_coverage(self, no_new_seconds):
        if not bool(getattr(self, "mapping_active", False)):
            return super()._v74_request_finish_for_coverage(no_new_seconds)

        self._v119_no_new_finishes_suppressed += 1
        self._v119_last_suppressed_reason = (
            f"no-new-area {float(no_new_seconds):.1f}s"
        )
        self._v74_last_discovery_at = time.monotonic()
        try:
            self._post_ui(
                "v119_mapping_continue",
                self._v74_mapping_serial,
                (
                    "El E10 lleva un tiempo sin descubrir una celda nueva, "
                    "pero V119 no considera eso un fin de vivienda."
                ),
            )
        except Exception:
            pass
        return None

    def _v77_corridor_finish(self, reason):
        if not bool(getattr(self, "mapping_active", False)):
            return super()._v77_corridor_finish(reason)

        self._v119_corridor_finishes_suppressed += 1
        self._v119_last_suppressed_reason = "corredor: " + str(reason)
        self._v77_corridor_finishing = False
        try:
            self._v77_corridor_samples.clear()
        except Exception:
            pass
        try:
            self._post_ui(
                "v119_mapping_continue",
                self._v74_mapping_serial,
                (
                    "Corredor repetido detectado. Se conserva la sesión: "
                    "no se envía STOP ni dock y el mapa sigue abierto."
                ),
            )
        except Exception:
            pass
        return None

    def _v73_schedule_recovery(self, phase, reason):
        text = str(reason or "").lower()
        corridor_like = (
            "corredor" in text
            or "pasadas ida/vuelta" in text
            or "sector repetido" in text
        )
        if corridor_like and bool(getattr(self, "mapping_active", False)):
            self._v119_corridor_recoveries_suppressed += 1
            self._v119_last_suppressed_reason = (
                "recovery corredor suprimido: " + str(reason)
            )
            try:
                self._v83_last_recovery_gate = {
                    "kind": "corredor",
                    "reason": "V119: autorrecuperación del firmware priorizada",
                    "no_new": 0.0,
                    "cooldown": 0.0,
                }
            except Exception:
                pass
            return None
        return super()._v73_schedule_recovery(phase, reason)

    def _v118_note_status(self, status_code):
        try:
            code = int(status_code)
        except Exception:
            return

        now = time.monotonic()
        previous = self._v118_last_status_code
        if previous != code:
            rows = list(self._v118_status_transitions)
            rows.append({
                "t": round(now, 3),
                "from": previous,
                "to": code,
            })
            self._v118_status_transitions = rows[-30:]
            self._v118_last_status_code = code

        mapping = bool(getattr(self, "mapping_active", False))
        if mapping:
            self._v119_mapping_status_samples_ignored_by_v118 += 1
            self._v118_physical_clean_active = False
            self._v118_physical_clean_seen = False
            return

        if code in (5, 6, 7):
            self._v118_physical_clean_active = True
            self._v118_physical_clean_seen = True
        elif code == 3 and self._v118_physical_clean_seen:
            self._v118_physical_clean_active = True
        elif code == 4:
            self._v118_physical_clean_active = False
            self._v118_physical_clean_seen = False

        logical = bool(getattr(self, "_v115_global_clean_active", False))
        physical = bool(self._v118_physical_clean_active)
        if physical and not logical:
            self._v118_logical_physical_mismatches += 1
            self._v118_last_mismatch = (
                f"status={code}: limpieza física activa con worker V115 inactivo"
            )

    def _handle_ui_event(self, kind, payload):
        if kind == "v119_mapping_continue":
            serial, message = payload
            try:
                if int(serial) != int(self._v74_mapping_serial):
                    return
            except Exception:
                return
            if bool(getattr(self, "mapping_active", False)):
                self._set_banner(str(message))
            return
        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V119 ACTIVO · mapeo de vivienda sin cierre heurístico",
            "=================================================================",
            (
                f"cierres no-new suprimidos="
                f"{self._v119_no_new_finishes_suppressed} · "
                f"cierres por corredor suprimidos="
                f"{self._v119_corridor_finishes_suppressed}"
            ),
            (
                f"recoveries por corredor suprimidos="
                f"{self._v119_corridor_recoveries_suppressed} · "
                f"último={self._v119_last_suppressed_reason}"
            ),
            (
                f"muestras status de mapeo excluidas de V118="
                f"{self._v119_mapping_status_samples_ignored_by_v118}"
            ),
            "regla V119: cobertura mínima, tiempo o corredor repetido jamás equivalen a 'toda la vivienda completa'",
            "regla V119: no-new-area sólo difiere la heurística; no ejecuta stop(), dock() ni v74_mapping_complete",
            "regla V119: corredor repetido conserva la sesión y no ejecuta _v81_finish_complete/_v81_stop_incomplete",
            "regla V119: recovery de corredor se suprime para priorizar la autorrecuperación del firmware; oscilación realmente estacionaria conserva recovery",
            "regla V119: el cierre normal queda reservado al retorno físico que el propio E10 produzca o a Detener mapeo del usuario",
            "regla V119: status 5/6/7 con mapping_active=True no alimenta el detector de limpieza global V118",
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

import time

import app_v111
import app_v9
from xiaomi_e10_map_v111 import XiaomiE10MapV111


class App(app_v111.App):
    """V113: congela la geometría V111 y corrige retorno/renderer."""

    def __init__(self):
        self._v113_renderer_contract_hits = 0
        self._v113_return_prolonged = False
        self._v113_return_prolonged_events = 0
        self._v113_return_last_progress_at = None
        self._v113_return_last_distance = None
        self._v113_return_progress_events = 0
        self._v113_auto_stops_blocked = 0
        super().__init__()

    # ============================================= renderer V88/V110 compatible
    def _v87_draw_rooms_and_plan(self, canvas, snapshot, xy, transform=None):
        self._v113_renderer_contract_hits += 1
        return super()._v87_draw_rooms_and_plan(canvas, snapshot, xy)

    # ================================================ retorno sin auto-stop
    def _v74_reset_session(self):
        self._v113_return_prolonged = False
        self._v113_return_prolonged_events = 0
        self._v113_return_last_progress_at = None
        self._v113_return_last_distance = None
        self._v113_return_progress_events = 0
        self._v113_auto_stops_blocked = 0
        return super()._v74_reset_session()

    def dock(self):
        try:
            self._v84_cancel_recovery("V113: orden manual de volver a base")
        except Exception:
            pass
        return super().dock()

    def _v81_dock_monitor_worker(self, vacuum, serial, reason):
        next_warning = time.monotonic() + float(self.DOCK_SEARCH_TIMEOUT_SECONDS)
        self._v113_return_last_progress_at = time.monotonic()
        self._v113_return_last_distance = None

        while True:
            if serial != self._v73_dock_guard_serial:
                return
            if vacuum is not getattr(self, "vacuum", None):
                return
            if bool(getattr(self, "_v84_dock_latched", False)):
                return

            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                raw_robot = state.get("robot")
                distance = self._v71_raw_distance_to_origin(raw_robot)
            except Exception:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            self._v81_dock_last_status = status
            self._v81_dock_last_distance = distance
            self._v84_physical_status = status
            if status is not None:
                self._v74_last_status = status

            if status == 3:
                self._v84_note_returning("V113 dock guard")

            if (
                distance is not None
                and distance <= self.DOCK_NEAR_RADIUS_METERS
                and fault in (None, 0)
            ):
                self._v81_dock_near_samples += 1

            if status == 4:
                self._v84_mark_dock_authoritative(
                    "V113 dock guard status=4",
                    final=True,
                )
                self._post_ui(
                    "v84_dock_authoritative",
                    serial,
                    str(reason),
                    "V113 dock guard status=4",
                )
                return

            if distance is not None:
                previous = self._v113_return_last_distance
                if previous is None or abs(float(distance) - float(previous)) >= 0.05:
                    self._v113_return_last_progress_at = time.monotonic()
                    self._v113_return_progress_events += 1
                self._v113_return_last_distance = float(distance)

            now = time.monotonic()
            if now >= next_warning:
                self._v113_return_prolonged = True
                self._v113_return_prolonged_events += 1
                self._v113_auto_stops_blocked += 1
                self._v81_dock_timeout = False
                self._v73_dock_failed = False
                self._v73_dock_guard_active = True
                self._post_ui(
                    "v113_return_prolonged",
                    serial,
                    str(reason),
                    status,
                    distance,
                )
                next_warning = now + float(self.DOCK_SEARCH_TIMEOUT_SECONDS)

            time.sleep(self.BASE_POLL_SECONDS)

    def _handle_ui_event(self, kind, payload):
        if kind == "v113_return_prolonged":
            serial, reason, status, distance = payload
            if int(serial) != int(self._v73_dock_guard_serial):
                return
            distance_text = (
                "sin posición"
                if distance is None
                else f"{float(distance):.2f} m de la base"
            )
            self._set_banner(
                "Retorno prolongado: el E10 sigue controlando el regreso "
                f"({distance_text}, status={status}). La app no frenó las "
                "ruedas ni reenvió comandos."
            )
            return
        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        map_diag = (
            dict(getattr(client, "last_v111_diagnostics", {}) or {})
            if isinstance(client, XiaomiE10MapV111)
            else {}
        )
        progress_age = None
        if self._v113_return_last_progress_at is not None:
            progress_age = max(
                0.0,
                time.monotonic() - float(self._v113_return_last_progress_at),
            )

        lines = [
            "DIAGNÓSTICO V113 ACTIVO · geometría V111 congelada + retorno seguro",
            "======================================================================",
            (
                "geometría: selector=V111 sin gate rígido V112 · "
                f"grid={map_diag.get('grid_m2','—')} m² · "
                f"objetivo={map_diag.get('target_m2','—')}"
            ),
            (
                "renderer V88→V110: llamadas compatibles="
                f"{self._v113_renderer_contract_hits} · transform opcional=True"
            ),
            (
                "retorno: prolongado="
                f"{self._v113_return_prolonged} · avisos="
                f"{self._v113_return_prolonged_events} · progreso="
                f"{self._v113_return_progress_events} · último progreso="
                + (f"{progress_age:.1f}s" if progress_age is not None else "—")
            ),
            (
                "seguridad retorno: auto-stops bloqueados="
                f"{self._v113_auto_stops_blocked} · "
                "timeout jamás ejecuta stop/manual"
            ),
            "regla V113: se conserva exactamente la selección geométrica de V111 que produjo el mapa visualmente cercano a Mi Home",
            "regla V113: no existe retención mínima artificial de celdas ni obligación de conservar el 84% de V93",
            "regla V113: superar 120 s de retorno sólo genera aviso; jamás stop, reverse, manual(5) ni segundo dock",
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

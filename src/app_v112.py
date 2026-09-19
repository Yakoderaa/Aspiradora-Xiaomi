import math
import threading
import time

import app_v111
import app_v9
from xiaomi_e10_map_v112 import XiaomiE10MapV112


class App(app_v111.App):
    """V112: geometría final conservadora + retorno que nunca frena solo."""

    def __init__(self):
        self._v112_renderer_contract_hits = 0
        self._v112_return_prolonged = False
        self._v112_return_prolonged_events = 0
        self._v112_return_started_at = None
        self._v112_return_last_progress_at = None
        self._v112_return_last_distance = None
        self._v112_return_progress_events = 0
        self._v112_auto_stops_blocked = 0
        super().__init__()

    # ============================================= renderer V88/V110 compatible
    def _v87_draw_rooms_and_plan(
        self,
        canvas,
        snapshot,
        xy,
        transform=None,
    ):
        # V88 todavía llama con transform como quinto argumento. El rediseño
        # V110 no lo necesita, pero debe conservar ese contrato para no lanzar
        # una excepción en cada render.
        self._v112_renderer_contract_hits += 1
        return super()._v87_draw_rooms_and_plan(
            canvas,
            snapshot,
            xy,
        )

    # ======================================================== cliente V112
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV112)
        ):
            self._v40_client = XiaomiE10MapV112(vacuum, settings)
            self._v40_client_vacuum = vacuum

        try:
            points = (
                list(self.local_map.snapshot().get("points") or [])
                if self.local_map
                else []
            )
            self._v40_client.set_v109_reference_path(points)
        except Exception:
            pass

        try:
            self._v40_client.set_v111_area_raw(
                self._v111_area_raw_max,
                self._v111_area_m2_max,
            )
        except Exception:
            pass
        return self._v40_client

    # ================================================ retorno sin auto-stop
    def _v74_reset_session(self):
        self._v112_return_prolonged = False
        self._v112_return_prolonged_events = 0
        self._v112_return_started_at = None
        self._v112_return_last_progress_at = None
        self._v112_return_last_distance = None
        self._v112_return_progress_events = 0
        self._v112_auto_stops_blocked = 0
        return super()._v74_reset_session()

    def dock(self):
        # Una orden manual de dock invalida cualquier recovery pendiente, pero
        # jamás manda stop/reverse. El firmware conserva control del retorno.
        try:
            self._v84_cancel_recovery("V112: orden manual de volver a base")
        except Exception:
            pass
        self._v112_return_prolonged = False
        self._v112_return_started_at = time.monotonic()
        self._v112_return_last_progress_at = self._v112_return_started_at
        return super().dock()

    def _v81_dock_monitor_worker(self, vacuum, serial, reason):
        self._v112_return_started_at = time.monotonic()
        self._v112_return_last_progress_at = self._v112_return_started_at
        self._v112_return_last_distance = None
        next_warning = (
            self._v112_return_started_at
            + float(self.DOCK_SEARCH_TIMEOUT_SECONDS)
        )

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
                self._v84_note_returning("V112 dock guard")

            if (
                distance is not None
                and distance <= self.DOCK_NEAR_RADIUS_METERS
                and fault in (None, 0)
            ):
                self._v81_dock_near_samples += 1

            if status == 4:
                self._v84_mark_dock_authoritative(
                    "V112 dock guard status=4",
                    final=True,
                )
                self._post_ui(
                    "v84_dock_authoritative",
                    serial,
                    str(reason),
                    "V112 dock guard status=4",
                )
                return

            # Cualquier cambio apreciable de distancia cuenta como progreso. El
            # timeout ya no es una orden de movimiento; sólo genera diagnóstico.
            if distance is not None:
                previous = self._v112_return_last_distance
                if (
                    previous is None
                    or abs(float(distance) - float(previous)) >= 0.05
                ):
                    self._v112_return_last_progress_at = time.monotonic()
                    self._v112_return_progress_events += 1
                self._v112_return_last_distance = float(distance)

            now = time.monotonic()
            if now >= next_warning:
                self._v112_return_prolonged = True
                self._v112_return_prolonged_events += 1
                self._v112_auto_stops_blocked += 1
                # Importante: NO vacuum.stop(), NO manual(5), NO segundo dock.
                self._v81_dock_timeout = False
                self._v73_dock_failed = False
                self._v73_dock_guard_active = True
                self._post_ui(
                    "v112_return_prolonged",
                    serial,
                    str(reason),
                    status,
                    distance,
                )
                next_warning = now + float(self.DOCK_SEARCH_TIMEOUT_SECONDS)

            time.sleep(self.BASE_POLL_SECONDS)

    def _handle_ui_event(self, kind, payload):
        if kind == "v112_return_prolonged":
            serial, reason, status, distance = payload
            if int(serial) != int(self._v73_dock_guard_serial):
                return
            distance_text = (
                "sin posición"
                if distance is None
                else f"{float(distance):.2f} m de la base"
            )
            self._set_banner(
                "Retorno prolongado: el E10 sigue teniendo control del regreso "
                f"({distance_text}, status={status}). La app no frenó las "
                "ruedas ni reenvió comandos."
            )
            return
        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        diag = (
            dict(getattr(client, "last_v112_diagnostics", {}) or {})
            if isinstance(client, XiaomiE10MapV112)
            else {}
        )

        progress_age = None
        if self._v112_return_last_progress_at is not None:
            progress_age = max(
                0.0,
                time.monotonic() - float(self._v112_return_last_progress_at),
            )

        top = list(diag.get("top") or [])
        lines = [
            "DIAGNÓSTICO V112 ACTIVO · geometría retenida + retorno libre",
            "================================================================",
            (
                "mapa final: baseline V93="
                f"{diag.get('baseline_main','—')} celdas · "
                f"mínimo={diag.get('min_retained','—')} · "
                f"elegido={diag.get('final_cells','—')} · "
                f"retención="
                + (
                    f"{float(diag.get('retention_ratio')):.1%}"
                    if diag.get("retention_ratio") is not None
                    else "—"
                )
            ),
            (
                f"fuente objetivo={diag.get('target_source','—')} · "
                f"objetivo≈{diag.get('target_m2','—')} m² · "
                f"grid≈{diag.get('grid_m2','—')} m² · "
                f"fallback V93={diag.get('fallback_to_v93','—')}"
            ),
            (
                "gates final: rechazados por tamaño="
                f"{diag.get('rejected_small','—')} · "
                f"por extensión={diag.get('rejected_span','—')}"
            ),
            (
                "renderer V88→V110: llamadas compatibles="
                f"{self._v112_renderer_contract_hits} · transform opcional=True"
            ),
            (
                "retorno: prolongado="
                f"{self._v112_return_prolonged} · avisos="
                f"{self._v112_return_prolonged_events} · progreso="
                f"{self._v112_return_progress_events} · "
                f"último progreso="
                + (
                    f"{progress_age:.1f}s"
                    if progress_age is not None
                    else "—"
                )
            ),
            (
                "seguridad retorno: auto-stops bloqueados="
                f"{self._v112_auto_stops_blocked} · "
                "timeout V81 no ejecuta stop/manual"
            ),
            "top candidatos V112:",
        ]
        if top:
            for index, row in enumerate(top[:8], 1):
                lines.append(
                    f"    #{index} {row.get('key')} · "
                    f"{row.get('orientation')} · "
                    f"{row.get('cells')} celdas · "
                    f"ret={row.get('retention')} · "
                    f"grid={row.get('grid_m2')}m² · "
                    f"cov={row.get('coverage')}"
                )
        else:
            lines.append("    — todavía sin captura final V112 —")

        lines.extend([
            "regla V112: una máscara final no puede encogerse por debajo del 84% del componente V93 válido sin evidencia física",
            "regla V112: con cleaning-area=0 la escala geométrica se guía por huella/extensión de la trayectoria, no por el área mostrada de la tarea",
            "regla V112: superar 120 s de retorno sólo genera aviso; jamás stop, reverse, manual(5) ni segundo dock",
            "regla V112: _v87_draw_rooms_and_plan acepta transform opcional y no debe volver a generar TypeError",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

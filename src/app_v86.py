import statistics
import time
from collections import deque

import app_v85


class App(app_v85.App):
    """V86: fin de mapa sólo en dock + ETA real de batería/carga."""

    BATTERY_RATE_MIN_PCT_PER_MIN = 0.02
    BATTERY_RATE_MAX_PCT_PER_MIN = 4.0
    BATTERY_RATE_SEGMENTS = 8
    BATTERY_RATE_MIN_SEGMENT_SECONDS = 15.0

    def __init__(self):
        self._v86_completion_pending = False
        self._v86_completion_deferred = 0
        self._v86_completion_delivered_at = None

        self._v86_battery_mode = None
        self._v86_battery_last = None
        self._v86_battery_mode_started_at = None
        self._v86_charge_points = deque(maxlen=48)
        self._v86_clean_points = deque(maxlen=48)
        self._v86_charge_rate = None
        self._v86_clean_rate = None
        self._v86_charge_eta_min = None
        self._v86_clean_eta_min = None
        self._v86_battery_resets = 0
        self._v86_battery_last_status = None
        super().__init__()

    # =============================================== aviso fin sólo en dock
    def start_new_mapping(self):
        self._v86_completion_pending = False
        self._v86_completion_deferred = 0
        self._v86_completion_delivered_at = None
        return super().start_new_mapping()

    def _v86_dock_ready_for_completion_notice(self):
        return (
            bool(getattr(self, "_v84_dock_latched", False))
            and int(getattr(self, "_v84_physical_status", -1) or -1) == 4
            and bool(getattr(self, "_v81_dock_confirmed", False))
        )

    def _v70_notify_mapping_complete(self):
        # V70 podía disparar la ventana apenas la lógica de cobertura marcaba
        # el mapa como completo. En V86 la ventana sólo existe después de que
        # V84 haya confirmado físicamente status=4 en el dock.
        if not self._v86_dock_ready_for_completion_notice():
            self._v86_completion_pending = True
            self._v86_completion_deferred += 1
            try:
                self._set_banner(
                    "Mapeo completo · regresando a la base para cerrar y guardar…"
                )
            except Exception:
                pass
            return False

        self._v86_completion_pending = False
        self._v86_completion_delivered_at = time.monotonic()
        return super()._v70_notify_mapping_complete()

    # ======================================================== ETA batería
    @staticmethod
    def _v86_clamp_battery(value):
        try:
            return max(0, min(100, int(round(float(value)))))
        except Exception:
            return None

    def _v86_reset_mode_points(self, mode, now, battery):
        target = (
            self._v86_charge_points
            if mode == "charge"
            else self._v86_clean_points
        )
        target.clear()
        target.append((float(now), int(battery)))

    def _v86_note_battery(self, status):
        now = time.monotonic()
        physical = self._v67_int(getattr(status, "status", None))
        battery = self._v86_clamp_battery(getattr(status, "battery", None))
        self._v86_battery_last_status = physical
        self._v86_battery_last = battery

        if battery is None:
            return

        if physical == 4:
            mode = "charge"
        elif physical in (5, 6, 7):
            mode = "clean"
        else:
            mode = None

        if mode != self._v86_battery_mode:
            self._v86_battery_mode = mode
            self._v86_battery_mode_started_at = now
            if mode in ("charge", "clean"):
                self._v86_reset_mode_points(mode, now, battery)

        if mode not in ("charge", "clean"):
            return

        points = (
            self._v86_charge_points
            if mode == "charge"
            else self._v86_clean_points
        )
        if not points:
            points.append((now, battery))
        elif int(points[-1][1]) != int(battery):
            previous_battery = int(points[-1][1])
            wrong_direction = (
                (mode == "charge" and battery < previous_battery - 1)
                or (mode == "clean" and battery > previous_battery + 1)
            )
            if wrong_direction:
                self._v86_battery_resets += 1
                self._v86_reset_mode_points(mode, now, battery)
                points = (
                    self._v86_charge_points
                    if mode == "charge"
                    else self._v86_clean_points
                )
            else:
                points.append((now, battery))

        if mode == "charge":
            self._v86_charge_rate = self._v86_estimate_rate(points, "charge")
            self._v86_charge_eta_min = self._v86_eta_minutes(
                battery, self._v86_charge_rate, "charge"
            )
        else:
            self._v86_clean_rate = self._v86_estimate_rate(points, "clean")
            self._v86_clean_eta_min = self._v86_eta_minutes(
                battery, self._v86_clean_rate, "clean"
            )

    def _v86_estimate_rate(self, points, mode):
        rows = list(points or [])
        if len(rows) < 2:
            return None

        segments = []
        for (t0, b0), (t1, b1) in zip(rows, rows[1:]):
            seconds = float(t1) - float(t0)
            if seconds < self.BATTERY_RATE_MIN_SEGMENT_SECONDS:
                continue
            delta = float(b1) - float(b0)
            if mode == "clean":
                delta = -delta
            if delta <= 0:
                continue
            rate = delta / (seconds / 60.0)
            if (
                self.BATTERY_RATE_MIN_PCT_PER_MIN
                <= rate
                <= self.BATTERY_RATE_MAX_PCT_PER_MIN
            ):
                segments.append(float(rate))

        if not segments:
            return None
        recent = segments[-self.BATTERY_RATE_SEGMENTS :]
        return float(statistics.median(recent))

    @staticmethod
    def _v86_eta_minutes(battery, rate, mode):
        if battery is None or rate is None or rate <= 0:
            return None
        if mode == "charge":
            remaining = max(0.0, 100.0 - float(battery))
        else:
            remaining = max(0.0, float(battery))
        return max(0.0, remaining / float(rate))

    @staticmethod
    def _v86_format_eta(minutes):
        if minutes is None:
            return "calculando…"
        total = max(0, int(round(float(minutes))))
        if total < 60:
            return f"{total} min"
        hours, mins = divmod(total, 60)
        if mins == 0:
            return f"{hours} h"
        return f"{hours} h {mins} min"

    def _v86_refresh_battery_header(self):
        label = getattr(self, "battery_header", None)
        battery = self._v86_battery_last
        if label is None or battery is None:
            return

        status = self._v86_battery_last_status
        if status == 4:
            if battery >= 100:
                text = "Batería 100% · Carga completa"
            else:
                text = (
                    f"Batería {battery}% · Carga completa en ~"
                    f"{self._v86_format_eta(self._v86_charge_eta_min)}"
                )
        elif status in (5, 6, 7):
            text = (
                f"Batería {battery}% · Autonomía ~"
                f"{self._v86_format_eta(self._v86_clean_eta_min)}"
            )
        elif status == 3:
            text = f"Batería {battery}% · Volviendo a base"
        else:
            text = f"Batería {battery}%"

        try:
            label.configure(text=text)
        except Exception:
            pass

    def _render_status(self, status):
        result = super()._render_status(status)

        self._v86_note_battery(status)
        self._v86_refresh_battery_header()

        physical = self._v67_int(getattr(status, "status", None))
        if (
            physical == 4
            and self._v86_dock_ready_for_completion_notice()
            and bool(getattr(self, "_v74_finish_requested", False))
            and bool(getattr(self, "mapping_step2_complete", False))
            and not bool(getattr(self, "_v70_completion_notified", False))
        ):
            try:
                self.after(100, self._v70_notify_mapping_complete)
            except Exception:
                pass
        return result

    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · V85 anti-salto activo · aviso sólo en dock · "
                        "ETA batería V86"
                    )
                )
            except Exception:
                pass
        return result

    # =========================================================== diagnóstico
    @staticmethod
    def _v86_points_span(points):
        rows = list(points or [])
        if len(rows) < 2:
            return 0.0
        return max(0.0, float(rows[-1][0]) - float(rows[0][0]))

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        dock_ready = self._v86_dock_ready_for_completion_notice()
        charge_span = self._v86_points_span(self._v86_charge_points)
        clean_span = self._v86_points_span(self._v86_clean_points)

        lines = [
            "DIAGNÓSTICO V86 ACTIVO · fin físico + ETA batería + V85 empaquetado",
            "====================================================================",
            (
                "aviso fin: pendiente="
                f"{self._v86_completion_pending} · diferido="
                f"{self._v86_completion_deferred} · dock listo={dock_ready} · "
                f"notificado={bool(getattr(self, '_v70_completion_notified', False))}"
            ),
            (
                "batería: "
                f"{self._v86_battery_last}% · status="
                f"{self._v86_battery_last_status} · modo="
                f"{self._v86_battery_mode or '—'} · resets={self._v86_battery_resets}"
            ),
            (
                "carga ETA: tasa="
                f"{self._v86_charge_rate if self._v86_charge_rate is not None else '—'} %/min · "
                f"restante={self._v86_format_eta(self._v86_charge_eta_min)} · "
                f"cambios={max(0, len(self._v86_charge_points) - 1)} · "
                f"ventana={charge_span:.0f}s"
            ),
            (
                "aspirado ETA: tasa="
                f"{self._v86_clean_rate if self._v86_clean_rate is not None else '—'} %/min · "
                f"restante={self._v86_format_eta(self._v86_clean_eta_min)} · "
                f"cambios={max(0, len(self._v86_clean_points) - 1)} · "
                f"ventana={clean_span:.0f}s"
            ),
            "regla V86: el aviso de mapeo terminado no aparece hasta status=4 con dock confirmado",
            "regla V86: la ETA de carga usa la tasa real observada de aumento de batería",
            "regla V86: la autonomía de aspirado usa la tasa real observada de descarga de batería",
            "regla V86: hasta observar un cambio fiable de batería la UI muestra calculando… en vez de inventar minutos",
            "regla V86: el ejecutable se empaqueta desde main_v86 e incluye la continuidad anti-salto V85",
        ]
        return "\n".join(lines) + "\n\n" + inherited

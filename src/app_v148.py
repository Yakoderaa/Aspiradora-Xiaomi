import math
import time

import app_v147
import app_v9


class App(app_v147.App):
    """V148-IA: escape sólo válido con expansión 2D real y sin rebases V85."""

    STRIP_MIN_POINTS = 110
    STRIP_MIN_PATH_M = 12.0
    STRIP_MAX_2D_RATIO = 0.20
    STRIP_MIN_REVERSALS = 5
    STRIP_MIN_REVISIT = 0.72
    STRIP_MIN_PATH_TO_MAJOR = 2.05

    ESCAPE_2D_CROSS_GROWTH_M = 0.45
    ESCAPE_2D_MINOR_SPAN_M = 0.80
    ESCAPE_2D_RATIO = 0.22
    ESCAPE_RECENT_MINOR_SPAN_M = 0.50
    ESCAPE_RECENT_2D_RATIO = 0.16
    ESCAPE_SUCCESS_VOTES = 3

    def __init__(self):
        self._v148_escape_pre_bbox = None
        self._v148_escape_axis = None
        self._v148_escape_rebases = 0
        self._v148_success_votes = 0
        self._v148_last_validation = {}
        self._v148_rebase_progress_blocks = 0
        self._v148_last_rebases_seen = 0
        self._v148_persistent_strip_hits = 0
        super().__init__()

    def _v147_reset_state(self):
        result = super()._v147_reset_state()
        self._v148_escape_pre_bbox = None
        self._v148_escape_axis = None
        self._v148_escape_rebases = int(getattr(self, "_v85_rebases", 0) or 0)
        self._v148_success_votes = 0
        self._v148_last_validation = {}
        self._v148_rebase_progress_blocks = 0
        self._v148_last_rebases_seen = int(getattr(self, "_v85_rebases", 0) or 0)
        self._v148_persistent_strip_hits = 0
        return result

    @staticmethod
    def _v148_ratio(x_span, y_span):
        major = max(float(x_span or 0.0), float(y_span or 0.0))
        minor = min(float(x_span or 0.0), float(y_span or 0.0))
        return (minor / major) if major > 0.05 else 1.0

    @staticmethod
    def _v148_axis_growth(current, previous):
        if current is None or previous is None:
            return 0.0, 0.0
        x_growth = (
            max(0.0, float(previous[0]) - float(current[0]))
            + max(0.0, float(current[1]) - float(previous[1]))
        )
        y_growth = (
            max(0.0, float(previous[2]) - float(current[2]))
            + max(0.0, float(current[3]) - float(previous[3]))
        )
        return float(x_growth), float(y_growth)

    def _v142_classify_path(self, points):
        metrics = dict(super()._v142_classify_path(points))
        span_x = float(metrics.get("span_x", 0.0) or 0.0)
        span_y = float(metrics.get("span_y", 0.0) or 0.0)
        major = max(span_x, span_y)
        ratio = self._v148_ratio(span_x, span_y)
        path_m = float(metrics.get("path_m", 0.0) or 0.0)
        path_to_major = path_m / major if major > 0.05 else 0.0
        reversals = int(metrics.get("oscillation_reversals", 0) or 0)
        revisit = float(metrics.get("revisit_ratio", 0.0) or 0.0)
        count = int(metrics.get("points", 0) or 0)

        persistent_strip = bool(
            count >= self.STRIP_MIN_POINTS
            and path_m >= self.STRIP_MIN_PATH_M
            and ratio <= self.STRIP_MAX_2D_RATIO
            and reversals >= self.STRIP_MIN_REVERSALS
            and revisit >= self.STRIP_MIN_REVISIT
            and path_to_major >= self.STRIP_MIN_PATH_TO_MAJOR
        )

        metrics["v148_2d_ratio"] = round(ratio, 3)
        metrics["v148_path_to_major"] = round(path_to_major, 3)
        metrics["v148_persistent_strip"] = persistent_strip

        if persistent_strip:
            self._v148_persistent_strip_hits = (
                int(getattr(self, "_v148_persistent_strip_hits", 0) or 0) + 1
            )
            confidence = max(
                0.94,
                float(metrics.get("oscillation_confidence", 0.0) or 0.0),
            )
            metrics["pattern"] = "oscillation_corridor"
            metrics["confidence"] = round(min(0.995, confidence), 3)
            metrics["oscillation_evidence"] = True
            metrics["oscillation_confidence"] = metrics["confidence"]
            metrics["directional_progress"] = False
            metrics["corridor_progress"] = False
            metrics["reasoning"] = (
                "franja 1D persistente: recorrido largo con reversiones, "
                "revisita alta y expansión transversal insuficiente"
            )

        return metrics

    def _v146_apply_progress_evidence(self, metrics, now):
        state = self._v146_progress_state
        before = {
            "best_unique": state.get("best_unique"),
            "best_diag": state.get("best_diag"),
            "last_progress_at": state.get("last_progress_at"),
            "good_streak": state.get("good_streak"),
            "bad_streak": state.get("bad_streak"),
            "best_bbox": self._v147_state.get("best_bbox"),
            "v147_last_progress": self._v147_state.get("last_real_progress_at"),
            "v147_reason": self._v147_state.get("last_real_progress_reason"),
        }

        metrics = super()._v146_apply_progress_evidence(metrics, now)

        rebases = int(getattr(self, "_v85_rebases", 0) or 0)
        previous = int(getattr(self, "_v148_last_rebases_seen", rebases) or 0)
        rebase_changed = rebases != previous
        self._v148_last_rebases_seen = rebases

        metrics["v148_rebases"] = rebases
        metrics["v148_rebase_changed"] = rebase_changed
        metrics["v148_frame_offset"] = tuple(
            getattr(self, "_v85_frame_offset", (0.0, 0.0)) or (0.0, 0.0)
        )

        if rebase_changed:
            # Un cambio de marco no es movimiento físico. Deshacemos cualquier
            # progreso que la capa V146/V147 haya podido atribuir a esa muestra.
            for key in ("best_unique", "best_diag", "last_progress_at", "good_streak", "bad_streak"):
                if before[key] is not None:
                    state[key] = before[key]
            self._v147_state["best_bbox"] = before["best_bbox"]
            if before["v147_last_progress"] is not None:
                self._v147_state["last_real_progress_at"] = before["v147_last_progress"]
            if before["v147_reason"] is not None:
                self._v147_state["last_real_progress_reason"] = before["v147_reason"]

            last_progress = float(
                before["v147_last_progress"]
                or before["last_progress_at"]
                or now
            )
            metrics["progress_now"] = False
            metrics["real_progress"] = False
            metrics["no_progress_s"] = round(max(0.0, now - last_progress), 1)
            metrics["v148_rebase_progress_blocked"] = True
            self._v148_rebase_progress_blocks += 1
        else:
            metrics["v148_rebase_progress_blocked"] = False

        return metrics

    def _v147_schedule_escape(self, serial, metrics):
        bbox = metrics.get("bbox")
        self._v148_escape_pre_bbox = tuple(bbox) if bbox is not None else None
        if bbox is not None:
            span_x = max(0.0, float(bbox[1]) - float(bbox[0]))
            span_y = max(0.0, float(bbox[3]) - float(bbox[2]))
            self._v148_escape_axis = "x" if span_x >= span_y else "y"
        else:
            self._v148_escape_axis = None

        self._v148_escape_rebases = int(getattr(self, "_v85_rebases", 0) or 0)
        self._v148_success_votes = 0
        self._v148_last_validation = {
            "state": "escape iniciado",
            "pre_bbox": self._v148_escape_pre_bbox,
            "axis": self._v148_escape_axis,
            "rebases": self._v148_escape_rebases,
        }
        started = super()._v147_schedule_escape(serial, metrics)
        if started and self._v147_escape_history:
            self._v147_escape_history[-1]["v148_pre_bbox"] = self._v148_escape_pre_bbox
            self._v147_escape_history[-1]["v148_axis"] = self._v148_escape_axis
            self._v147_escape_history[-1]["v148_rebases_at_start"] = self._v148_escape_rebases
            self._v147_escape_history[-1]["success"] = None
            self._v147_escape_history[-1]["validation"] = "pendiente 2D V148"
        return started

    def _v148_escape_geometry(self, metrics):
        current = metrics.get("bbox")
        pre = self._v148_escape_pre_bbox
        x_growth, y_growth = self._v148_axis_growth(current, pre)

        if self._v148_escape_axis == "x":
            cross_growth = y_growth
        elif self._v148_escape_axis == "y":
            cross_growth = x_growth
        else:
            cross_growth = min(x_growth, y_growth)

        span_x = float(metrics.get("span_x", 0.0) or 0.0)
        span_y = float(metrics.get("span_y", 0.0) or 0.0)
        minor_span = min(span_x, span_y)
        ratio = self._v148_ratio(span_x, span_y)

        recent_x = float(metrics.get("recent_span_x", 0.0) or 0.0)
        recent_y = float(metrics.get("recent_span_y", 0.0) or 0.0)
        recent_minor = min(recent_x, recent_y)
        recent_ratio = self._v148_ratio(recent_x, recent_y)

        rebases = int(getattr(self, "_v85_rebases", 0) or 0)
        rebase_stable = rebases == int(self._v148_escape_rebases or 0)

        good = bool(
            rebase_stable
            and not bool(metrics.get("oscillation_evidence"))
            and not bool(metrics.get("v148_persistent_strip"))
            and cross_growth >= self.ESCAPE_2D_CROSS_GROWTH_M
            and minor_span >= self.ESCAPE_2D_MINOR_SPAN_M
            and ratio >= self.ESCAPE_2D_RATIO
            and recent_minor >= self.ESCAPE_RECENT_MINOR_SPAN_M
            and recent_ratio >= self.ESCAPE_RECENT_2D_RATIO
        )

        return {
            "candidate": good,
            "x_growth_m": round(x_growth, 2),
            "y_growth_m": round(y_growth, 2),
            "cross_growth_m": round(cross_growth, 2),
            "minor_span_m": round(minor_span, 2),
            "ratio_2d": round(ratio, 3),
            "recent_minor_span_m": round(recent_minor, 2),
            "recent_ratio_2d": round(recent_ratio, 3),
            "rebase_stable": rebase_stable,
            "rebases_start": int(self._v148_escape_rebases or 0),
            "rebases_now": rebases,
            "persistent_strip": bool(metrics.get("v148_persistent_strip")),
            "oscillation": bool(metrics.get("oscillation_evidence")),
        }

    def _v147_escape_success(self, metrics, now):
        if not self._v147_escape_awaiting_validation:
            return False
        if now - float(self._v147_escape_done_at or 0.0) < self.ESCAPE_MIN_VALIDATE_SECONDS:
            return False

        validation = self._v148_escape_geometry(metrics)
        if validation["candidate"]:
            self._v148_success_votes += 1
        else:
            self._v148_success_votes = 0

        validation["votes"] = self._v148_success_votes
        validation["votes_required"] = self.ESCAPE_SUCCESS_VOTES
        self._v148_last_validation = dict(validation)

        if self._v148_success_votes < self.ESCAPE_SUCCESS_VOTES:
            if now >= float(self._v147_escape_grace_until or 0.0):
                self._v147_escape_awaiting_validation = False
                if self._v147_escape_history:
                    self._v147_escape_history[-1]["success"] = False
                    self._v147_escape_history[-1]["validation"] = dict(validation)
                self._v141_log(
                    "V148 escape rechazado: no hubo expansión 2D sostenida",
                    validation=validation,
                    consecutive=self._v147_escape_consecutive,
                    total=self._v147_escape_total,
                )
            return False

        self._v147_escape_awaiting_validation = False
        self._v147_escape_consecutive = 0
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v143_bad_pattern_streak = 0
        self._v147_state["last_real_progress_at"] = now
        self._v146_progress_state["last_progress_at"] = now
        if self._v147_escape_history:
            self._v147_escape_history[-1]["success"] = True
            self._v147_escape_history[-1]["validation"] = dict(validation)

        self._v141_log("V148 escape validado en 2D", validation=validation)
        self._post_ui(
            "v148_escape_validated",
            validation["cross_growth_m"],
            validation["recent_ratio_2d"],
        )
        return True

    def _handle_ui_event(self, kind, payload):
        if kind == "v147_escape_done":
            result = super()._handle_ui_event(kind, payload)
            if self._v147_escape_history:
                self._v147_escape_history[-1]["movement_executed"] = True
                self._v147_escape_history[-1]["success"] = None
                self._v147_escape_history[-1]["validation"] = "pendiente 2D V148"
            self._set_banner(
                "Escape físico V148 ejecutado · misma sesión · "
                "todavía NO se considera exitoso: validando expansión 2D real."
            )
            return result

        if kind == "v147_escape_started":
            attempt = int(payload[0])
            total = int(payload[1])
            direction = str(payload[2])
            self._set_banner(
                "IA V148 confirmó recorrido repetitivo · "
                f"escape {attempt}/{self.ESCAPE_MAX_CONSECUTIVE} hacia {direction} · "
                "la validación exige expansión 2D real."
            )
            return None

        if kind == "v148_escape_validated":
            cross = float(payload[0])
            ratio = float(payload[1])
            self._set_banner(
                "IA V148 confirmó escape real · "
                f"expansión transversal +{cross:.2f} m · ratio 2D reciente {ratio:.2f} · "
                "continúa el mapeo."
            )
            return None

        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V148-IA ACTIVO · escape 2D + rebase-neutral",
            "===========================================================",
            f"validación escape={self._v148_last_validation or '—'}",
            f"votos éxito 2D={self._v148_success_votes}/{self.ESCAPE_SUCCESS_VOTES}",
            f"rebases bloqueados como progreso={self._v148_rebase_progress_blocks}",
            f"rebases actuales/inicio escape={int(getattr(self, '_v85_rebases', 0) or 0)}/{self._v148_escape_rebases}",
            f"franja 1D persistente hits={self._v148_persistent_strip_hits}",
            "regla V148: desplazamiento neto alto en un solo eje NO valida un escape",
            "regla V148: escape exige crecimiento transversal + ancho + ratio 2D reciente sostenidos",
            "regla V148: tres evaluaciones 2D consecutivas son necesarias para poner consecutivos=0",
            "regla V148: cualquier rebase V85 durante la validación invalida ese progreso",
            "regla V148: franja larga/estrecha con reversiones y revisita alta sigue siendo oscilación aunque avance el extremo",
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

import math
import threading
import time

import app_v145
import app_v9


class App(app_v145.App):
    """V146-IA: consenso multiseñal, progreso espacial e histéresis anti-falsos-positivos."""

    AI_BAD_PATTERN_CONFIDENCE = 0.93
    AI_BAD_PATTERN_STREAK = 6
    AI_AUTO_ABORT_MIN_SECONDS = 90.0
    AI_AUTO_ABORT_MIN_PATH_M = 7.0

    AI_PROGRESS_CELL = 0.35
    AI_PROGRESS_UNIQUE_GAIN = 2
    AI_PROGRESS_DIAG_GAIN = 0.35
    AI_PROGRESS_RECENT_SPAN_M = 1.15
    AI_PROGRESS_NET_DISPLACEMENT_M = 0.85

    AI_STUCK_NO_PROGRESS_SECONDS = 28.0
    AI_LOOP_NO_PROGRESS_SECONDS = 65.0
    AI_LOOP_MIN_RECENT_PATH_M = 4.0
    AI_LOOP_MAX_RECENT_SPAN_M = 1.15
    AI_STUCK_MAX_RECENT_SPAN_M = 0.38

    def __init__(self):
        self._v146_progress_state = {}
        self._v146_consensus = {}
        self._v146_false_positive_resets = 0
        self._v146_last_good_progress_at = None
        self._v146_last_metrics = {}
        super().__init__()

    @staticmethod
    def _v146_path_length(points):
        total = 0.0
        for a, b in zip(points, points[1:]):
            total += math.hypot(b[0] - a[0], b[1] - a[1])
        return total

    @staticmethod
    def _v146_span(points):
        if not points:
            return 0.0, 0.0, 0.0
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        sx = max(xs) - min(xs)
        sy = max(ys) - min(ys)
        return sx, sy, math.hypot(sx, sy)

    def _v146_cells(self, points):
        cell = max(0.05, float(self.AI_PROGRESS_CELL))
        return {
            (int(round(x / cell)), int(round(y / cell)))
            for x, y in points
        }

    def _v142_classify_path(self, points):
        points = list(points or [])
        if len(points) < 8:
            return {
                "pattern": "insufficient",
                "confidence": 0.0,
                "points": len(points),
                "reasoning": "menos de 8 puntos",
            }

        path = self._v146_path_length(points)
        span_x, span_y, diag = self._v146_span(points)
        cells = self._v146_cells(points)
        revisit = 1.0 - min(1.0, len(cells) / max(1.0, len(points)))

        recent = points[-44:]
        recent_path = self._v146_path_length(recent)
        recent_span_x, recent_span_y, recent_span = self._v146_span(recent)
        recent_cells = self._v146_cells(recent)
        old_cells = self._v146_cells(points[:-44]) if len(points) > 44 else set()
        recent_new_cells = len(recent_cells - old_cells)

        if len(recent) >= 2:
            net_displacement = math.hypot(
                recent[-1][0] - recent[0][0],
                recent[-1][1] - recent[0][1],
            )
        else:
            net_displacement = 0.0

        straightness = (
            min(1.0, net_displacement / recent_path)
            if recent_path > 0.05
            else 0.0
        )

        directional_progress = bool(
            recent_span >= self.AI_PROGRESS_RECENT_SPAN_M
            or net_displacement >= self.AI_PROGRESS_NET_DISPLACEMENT_M
            or recent_new_cells >= self.AI_PROGRESS_UNIQUE_GAIN
        )

        corridor_progress = bool(
            max(recent_span_x, recent_span_y) >= 1.60
            and net_displacement >= 0.70
        )

        stuck_evidence = bool(
            len(recent) >= 24
            and recent_path >= 1.8
            and recent_span <= self.AI_STUCK_MAX_RECENT_SPAN_M
            and len(recent_cells) <= 5
            and net_displacement <= 0.28
            and recent_new_cells <= 1
        )

        loop_evidence = bool(
            len(recent) >= 30
            and recent_path >= self.AI_LOOP_MIN_RECENT_PATH_M
            and recent_span <= self.AI_LOOP_MAX_RECENT_SPAN_M
            and revisit >= 0.70
            and recent_new_cells <= 1
            and net_displacement <= 0.62
            and not corridor_progress
        )

        if stuck_evidence:
            pattern = "stuck"
            confidence = min(
                0.995,
                0.93
                + max(0.0, self.AI_STUCK_MAX_RECENT_SPAN_M - recent_span) * 0.12,
            )
            reasoning = "movimiento acumulado sin expansión espacial"
        elif loop_evidence:
            pattern = "spiral_or_loop"
            confidence = min(0.99, 0.88 + revisit * 0.12)
            reasoning = "recorrido reciente largo, cerrado y sin celdas nuevas"
        elif directional_progress or corridor_progress:
            pattern = "expanding"
            confidence = min(
                0.98,
                0.68
                + min(0.14, recent_span / 16.0)
                + min(0.10, recent_new_cells / 25.0)
                + min(0.06, straightness / 8.0),
            )
            reasoning = "hay expansión, desplazamiento neto o terreno nuevo"
        elif path >= 3.0 and diag >= 1.5 and len(cells) >= 8:
            pattern = "mixed_progress"
            confidence = 0.68
            reasoning = "recorrido mixto con cobertura útil"
        else:
            pattern = "mixed"
            confidence = 0.56
            reasoning = "evidencia insuficiente para declarar fallo"

        return {
            "pattern": pattern,
            "confidence": round(confidence, 3),
            "path_m": round(path, 2),
            "span_x": round(span_x, 2),
            "span_y": round(span_y, 2),
            "diag_m": round(diag, 2),
            "unique_cells": len(cells),
            "revisit_ratio": round(revisit, 3),
            "recent_path_m": round(recent_path, 2),
            "recent_span_m": round(recent_span, 2),
            "recent_span_x": round(recent_span_x, 2),
            "recent_span_y": round(recent_span_y, 2),
            "recent_unique_cells": len(recent_cells),
            "recent_new_cells": int(recent_new_cells),
            "net_displacement_m": round(net_displacement, 2),
            "straightness": round(straightness, 3),
            "directional_progress": directional_progress,
            "corridor_progress": corridor_progress,
            "points": len(points),
            "reasoning": reasoning,
        }

    def _v146_reset_progress_state(self):
        now = time.monotonic()
        self._v146_progress_state = {
            "best_unique": 0,
            "best_diag": 0.0,
            "last_progress_at": now,
            "last_eval_at": now,
            "good_streak": 0,
            "bad_streak": 0,
            "last_pattern": None,
            "recent_votes": [],
        }
        self._v146_consensus = {}
        self._v146_false_positive_resets = 0
        self._v146_last_good_progress_at = now
        self._v146_last_metrics = {}

    def _v142_start_mapping_ai(self):
        self._v146_reset_progress_state()
        return super()._v142_start_mapping_ai()

    def _v146_apply_progress_evidence(self, metrics, now):
        state = self._v146_progress_state
        unique = int(metrics.get("unique_cells", 0) or 0)
        diag = float(metrics.get("diag_m", 0.0) or 0.0)

        unique_gain = unique - int(state.get("best_unique", 0) or 0)
        diag_gain = diag - float(state.get("best_diag", 0.0) or 0.0)

        progress_now = bool(
            unique_gain >= self.AI_PROGRESS_UNIQUE_GAIN
            or diag_gain >= self.AI_PROGRESS_DIAG_GAIN
            or bool(metrics.get("directional_progress"))
            or bool(metrics.get("corridor_progress"))
        )

        if progress_now:
            state["best_unique"] = max(
                int(state.get("best_unique", 0) or 0),
                unique,
            )
            state["best_diag"] = max(
                float(state.get("best_diag", 0.0) or 0.0),
                diag,
            )
            state["last_progress_at"] = now
            state["good_streak"] = int(state.get("good_streak", 0) or 0) + 1
            if int(state.get("bad_streak", 0) or 0) > 0:
                self._v146_false_positive_resets += 1
            state["bad_streak"] = 0
            self._v143_bad_pattern_streak = 0
            self._v146_last_good_progress_at = now
        else:
            state["good_streak"] = 0

        no_progress_s = max(
            0.0,
            now - float(state.get("last_progress_at", now) or now),
        )

        metrics["progress_now"] = progress_now
        metrics["unique_gain"] = int(unique_gain)
        metrics["diag_gain_m"] = round(diag_gain, 2)
        metrics["no_progress_s"] = round(no_progress_s, 1)
        metrics["best_unique_cells"] = int(state.get("best_unique", 0) or 0)
        metrics["best_diag_m"] = round(float(state.get("best_diag", 0.0) or 0.0), 2)
        return metrics

    def _v146_bad_evidence(self, metrics):
        pattern = str(metrics.get("pattern") or "")
        confidence = float(metrics.get("confidence", 0.0) or 0.0)
        no_progress_s = float(metrics.get("no_progress_s", 0.0) or 0.0)
        recent_new = int(metrics.get("recent_new_cells", 0) or 0)
        recent_span = float(metrics.get("recent_span_m", 0.0) or 0.0)
        progress_now = bool(metrics.get("progress_now"))

        if progress_now:
            return False, "progreso espacial confirmado"

        if pattern == "stuck":
            bad = bool(
                confidence >= self.AI_BAD_PATTERN_CONFIDENCE
                and no_progress_s >= self.AI_STUCK_NO_PROGRESS_SECONDS
                and recent_span <= self.AI_STUCK_MAX_RECENT_SPAN_M
                and recent_new <= 1
            )
            return bad, "atasco multiseñal" if bad else "atasco sin consenso suficiente"

        if pattern == "spiral_or_loop":
            bad = bool(
                confidence >= self.AI_BAD_PATTERN_CONFIDENCE
                and no_progress_s >= self.AI_LOOP_NO_PROGRESS_SECONDS
                and recent_span <= self.AI_LOOP_MAX_RECENT_SPAN_M
                and recent_new <= 1
                and float(metrics.get("recent_path_m", 0.0) or 0.0)
                >= self.AI_LOOP_MIN_RECENT_PATH_M
            )
            return bad, "bucle multiseñal" if bad else "bucle sin consenso suficiente"

        return False, "patrón no crítico"

    def _v142_mapping_monitor(self, token, serial):
        last_signature = None

        while token == self._v142_mapping_token:
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return
            if not bool(getattr(self, "mapping_active", False)):
                return

            phase = int(getattr(self, "mapping_phase", 0) or 0)
            if phase not in (1, 2):
                time.sleep(1.4)
                continue

            try:
                snapshot = self.local_map.snapshot()
                points = self._v142_xy_points(snapshot, phase=phase)
                metrics = self._v142_classify_path(points[-220:])
                metrics["phase"] = phase

                now = time.monotonic()
                metrics = self._v146_apply_progress_evidence(metrics, now)
                bad, consensus_reason = self._v146_bad_evidence(metrics)
                metrics["bad_consensus"] = bool(bad)
                metrics["consensus_reason"] = consensus_reason

                votes = list(self._v146_progress_state.get("recent_votes") or [])
                votes.append(bool(bad))
                votes = votes[-8:]
                self._v146_progress_state["recent_votes"] = votes
                bad_votes = sum(1 for item in votes if item)
                metrics["bad_votes_8"] = bad_votes

                if phase == 1:
                    if bad:
                        self._v143_bad_pattern_streak += 1
                    else:
                        self._v143_bad_pattern_streak = 0

                    elapsed = 0.0
                    started = getattr(self, "_v74_started_at", None)
                    if started is not None:
                        try:
                            elapsed = max(0.0, now - float(started))
                        except Exception:
                            elapsed = 0.0

                    if str(metrics.get("pattern")) == "stuck":
                        required_no_progress = self.AI_STUCK_NO_PROGRESS_SECONDS
                    else:
                        required_no_progress = self.AI_LOOP_NO_PROGRESS_SECONDS

                    eligible = bool(
                        bad
                        and self._v143_bad_pattern_streak >= self.AI_BAD_PATTERN_STREAK
                        and bad_votes >= 6
                        and elapsed >= self.AI_AUTO_ABORT_MIN_SECONDS
                        and float(metrics.get("path_m", 0.0) or 0.0)
                        >= self.AI_AUTO_ABORT_MIN_PATH_M
                        and float(metrics.get("no_progress_s", 0.0) or 0.0)
                        >= required_no_progress
                    )

                    if eligible:
                        reason = (
                            "IA V146 confirmó "
                            f"{metrics.get('pattern')} por consenso multiseñal "
                            f"(confianza {float(metrics.get('confidence', 0.0)):.2f}, "
                            f"sin progreso {float(metrics.get('no_progress_s', 0.0)):.0f}s)"
                        )
                        self._v143_phase1_invalid_reason = reason

                        if not self._v144_auto_abort_requested:
                            self._v144_auto_abort_requested = True
                            tagged = dict(metrics)
                            tagged["elapsed_s"] = round(elapsed, 1)
                            tagged["bad_streak"] = int(self._v143_bad_pattern_streak)
                            tagged["reason"] = reason
                            self._post_ui(
                                "v144_ai_auto_abort",
                                serial,
                                tagged,
                            )

                signature = (
                    metrics.get("pattern"),
                    metrics.get("unique_cells"),
                    metrics.get("recent_new_cells"),
                    metrics.get("bad_consensus"),
                    int(float(metrics.get("no_progress_s", 0.0) or 0.0) // 5),
                    len(points),
                )
                if signature != last_signature:
                    self._v142_mapping_diag = dict(metrics)
                    self._v146_last_metrics = dict(metrics)
                    last_signature = signature

                self._v146_consensus = {
                    "bad": bool(bad),
                    "reason": consensus_reason,
                    "bad_votes_8": bad_votes,
                    "bad_streak": int(self._v143_bad_pattern_streak),
                    "no_progress_s": metrics.get("no_progress_s"),
                    "progress_now": metrics.get("progress_now"),
                    "recent_new_cells": metrics.get("recent_new_cells"),
                    "recent_span_m": metrics.get("recent_span_m"),
                    "net_displacement_m": metrics.get("net_displacement_m"),
                }
            except Exception as exc:
                self._v142_mapping_diag = {
                    "error": str(exc).strip() or type(exc).__name__,
                    "phase": phase,
                }

            time.sleep(2.0)

    def _v143_phase1_is_valid(self):
        metrics = self._v143_phase1_metrics()
        now = time.monotonic()
        last_progress = float(
            self._v146_progress_state.get("last_progress_at", now) or now
        )
        metrics.update({
            "no_progress_s": round(max(0.0, now - last_progress), 1),
            "consensus": dict(self._v146_consensus or {}),
        })

        reason = None
        if self._v143_manual_return_requested:
            reason = "regreso manual solicitado durante Paso 1"
        elif self._v143_phase1_invalid_reason:
            reason = self._v143_phase1_invalid_reason
        elif metrics.get("pattern") == "insufficient":
            reason = "trayectoria insuficiente para validar Paso 1"
        elif int(metrics.get("unique_cells", 0) or 0) < 8:
            reason = "cobertura insuficiente para validar Paso 1"
        else:
            bad, why = self._v146_bad_evidence(metrics)
            votes = int((self._v146_consensus or {}).get("bad_votes_8", 0) or 0)
            if bad and votes >= 6:
                reason = f"patrón crítico confirmado al cerrar Paso 1: {why}"

        metrics["valid"] = reason is None
        metrics["reason"] = reason
        self._v143_phase1_quality = dict(metrics)
        return reason is None, reason, metrics

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V146-IA ACTIVO · consenso multiseñal + progreso espacial",
            "====================================================================",
            f"consenso={self._v146_consensus or '—'}",
            f"estado progreso={self._v146_progress_state or '—'}",
            f"últimas métricas={self._v146_last_metrics or '—'}",
            f"falsos positivos evitados/reset de racha={self._v146_false_positive_resets}",
            "regla V146: avanzar en X o Y cuenta como progreso aunque el otro eje sea estrecho",
            "regla V146: revisitar celdas por sí solo jamás dispara auto-abort",
            "regla V146: stuck exige confinamiento + casi cero desplazamiento + tiempo sin progreso",
            "regla V146: loop exige recorrido cerrado + casi cero celdas nuevas + mayoría temporal",
            "regla V146: cualquier expansión real reinicia inmediatamente la racha mala",
            "regla V146: auto-abort requiere consenso 6/8 + racha >=6 + >=90 s + >=7 m",
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

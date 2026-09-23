import math
import threading
import time

import app_v146
import app_v9


class App(app_v146.App):
    """V147-IA: detecta oscilación ida/vuelta y escapa sin perder la sesión."""

    OSC_WINDOW_POINTS = 60
    OSC_MIN_POINTS = 32
    OSC_MIN_RECENT_PATH_M = 4.0
    OSC_MIN_ALONG_SPAN_M = 0.65
    OSC_MAX_CROSS_SPAN_M = 0.45
    OSC_MIN_REVERSALS = 5
    OSC_MAX_NET_DISPLACEMENT_M = 0.55
    OSC_MAX_STRAIGHTNESS = 0.14
    OSC_MAX_PATH_EFFICIENCY = 0.32
    OSC_MIN_REVISIT_RATIO = 0.70
    OSC_MIN_CONFIDENCE = 0.90

    OSC_VOTES_REQUIRED = 5
    OSC_STREAK_REQUIRED = 5
    OSC_MIN_NO_PROGRESS_SECONDS = 30.0
    OSC_MIN_SESSION_SECONDS = 100.0
    OSC_MIN_TOTAL_PATH_M = 7.0

    REAL_ENVELOPE_GROWTH_M = 0.25
    REAL_DIRECTIONAL_NET_M = 0.75
    REAL_UNIQUE_GAIN = 3

    ESCAPE_MAX_CONSECUTIVE = 3
    ESCAPE_MAX_TOTAL = 6
    ESCAPE_GRACE_SECONDS = 50.0
    ESCAPE_SUCCESS_GROWTH_M = 0.45
    ESCAPE_MIN_VALIDATE_SECONDS = 8.0
    ESCAPE_REVERSE_SECONDS = (0.90, 1.15, 1.35)
    ESCAPE_TURN_SECONDS = (0.55, 0.80, 1.05)

    def __init__(self):
        self._v147_state = {}
        self._v147_last_oscillation = {}
        self._v147_escape_history = []
        self._v147_escape_active = False
        self._v147_escape_total = 0
        self._v147_escape_consecutive = 0
        self._v147_escape_grace_until = 0.0
        self._v147_escape_done_at = 0.0
        self._v147_escape_pre_bbox = None
        self._v147_escape_awaiting_validation = False
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v147_escape_error = None
        super().__init__()

    def _v147_reset_state(self):
        self._v147_state = {
            "best_bbox": None,
            "last_real_progress_at": time.monotonic(),
            "last_envelope_growth_m": 0.0,
            "last_real_progress_reason": "inicio de sesión",
        }
        self._v147_last_oscillation = {}
        self._v147_escape_history = []
        self._v147_escape_active = False
        self._v147_escape_total = 0
        self._v147_escape_consecutive = 0
        self._v147_escape_grace_until = 0.0
        self._v147_escape_done_at = 0.0
        self._v147_escape_pre_bbox = None
        self._v147_escape_awaiting_validation = False
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v147_escape_error = None

    def _v142_start_mapping_ai(self):
        self._v147_reset_state()
        return super()._v142_start_mapping_ai()

    @staticmethod
    def _v147_bbox(points):
        if not points:
            return None
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return (min(xs), max(xs), min(ys), max(ys))

    @staticmethod
    def _v147_bbox_growth(current, previous):
        if current is None or previous is None:
            return 0.0
        return (
            max(0.0, float(previous[0]) - float(current[0]))
            + max(0.0, float(current[1]) - float(previous[1]))
            + max(0.0, float(previous[2]) - float(current[2]))
            + max(0.0, float(current[3]) - float(previous[3]))
        )

    @staticmethod
    def _v147_bbox_union(a, b):
        if a is None:
            return tuple(b) if b is not None else None
        if b is None:
            return tuple(a)
        return (
            min(float(a[0]), float(b[0])),
            max(float(a[1]), float(b[1])),
            min(float(a[2]), float(b[2])),
            max(float(a[3]), float(b[3])),
        )

    @staticmethod
    def _v147_corridor_geometry(points, step_epsilon=0.04):
        points = list(points or [])
        if len(points) < 3:
            return None

        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
        ax = math.cos(angle)
        ay = math.sin(angle)
        px = -ay
        py = ax

        along = [(x - mx) * ax + (y - my) * ay for x, y in zip(xs, ys)]
        cross = [(x - mx) * px + (y - my) * py for x, y in zip(xs, ys)]
        along_span = max(along) - min(along)
        cross_span = max(cross) - min(cross)

        signs = []
        for a, b in zip(along, along[1:]):
            delta = b - a
            if abs(delta) < float(step_epsilon):
                continue
            sign = 1 if delta > 0 else -1
            if not signs or signs[-1] != sign:
                signs.append(sign)

        return {
            "along_span": float(along_span),
            "cross_span": float(cross_span),
            "reversals": max(0, len(signs) - 1),
            "axis_angle": float(angle),
        }

    def _v142_classify_path(self, points):
        points = list(points or [])
        metrics = dict(super()._v142_classify_path(points))
        if len(points) < self.OSC_MIN_POINTS:
            metrics.update({
                "oscillation_evidence": False,
                "oscillation_confidence": 0.0,
                "oscillation_reversals": 0,
            })
            return metrics

        recent = points[-self.OSC_WINDOW_POINTS:]
        recent_path = self._v146_path_length(recent)
        bbox = self._v147_bbox(points)
        recent_bbox = self._v147_bbox(recent)
        geometry = self._v147_corridor_geometry(recent)

        if len(recent) >= 2:
            net = math.hypot(
                float(recent[-1][0]) - float(recent[0][0]),
                float(recent[-1][1]) - float(recent[0][1]),
            )
        else:
            net = 0.0

        recent_cells = self._v146_cells(recent)
        recent_revisit = 1.0 - min(
            1.0,
            len(recent_cells) / max(1.0, len(recent)),
        )

        along_span = float((geometry or {}).get("along_span", 0.0) or 0.0)
        cross_span = float((geometry or {}).get("cross_span", 999.0) or 999.0)
        reversals = int((geometry or {}).get("reversals", 0) or 0)
        path_efficiency = (
            min(1.0, along_span / recent_path)
            if recent_path > 0.05
            else 1.0
        )
        straightness = (
            min(1.0, net / recent_path)
            if recent_path > 0.05
            else 1.0
        )

        checks = {
            "enough_path": recent_path >= self.OSC_MIN_RECENT_PATH_M,
            "enough_span": along_span >= self.OSC_MIN_ALONG_SPAN_M,
            "narrow": cross_span <= self.OSC_MAX_CROSS_SPAN_M,
            "reversals": reversals >= self.OSC_MIN_REVERSALS,
            "low_net": net <= self.OSC_MAX_NET_DISPLACEMENT_M,
            "low_straightness": straightness <= self.OSC_MAX_STRAIGHTNESS,
            "low_efficiency": path_efficiency <= self.OSC_MAX_PATH_EFFICIENCY,
            "high_revisit": recent_revisit >= self.OSC_MIN_REVISIT_RATIO,
        }
        positive = sum(1 for value in checks.values() if value)

        oscillation = bool(
            len(recent) >= self.OSC_MIN_POINTS
            and checks["enough_path"]
            and checks["enough_span"]
            and checks["narrow"]
            and checks["reversals"]
            and checks["low_net"]
            and checks["low_straightness"]
            and checks["low_efficiency"]
            and positive >= 7
        )

        confidence = 0.0
        if oscillation:
            confidence = min(
                0.995,
                0.86
                + min(0.06, max(0, reversals - self.OSC_MIN_REVERSALS) * 0.008)
                + min(0.04, max(0.0, recent_revisit - 0.70) * 0.16)
                + min(0.03, max(0.0, 0.14 - straightness) * 0.18),
            )
            metrics["pattern"] = "oscillation_corridor"
            metrics["confidence"] = round(confidence, 3)
            metrics["reasoning"] = (
                "ida/vuelta repetido: mucha distancia, muchas reversiones "
                "y poca expansión útil"
            )
            metrics["directional_progress"] = False
            metrics["corridor_progress"] = False

        metrics.update({
            "bbox": bbox,
            "recent_bbox": recent_bbox,
            "oscillation_evidence": oscillation,
            "oscillation_confidence": round(confidence, 3),
            "oscillation_reversals": reversals,
            "oscillation_along_span_m": round(along_span, 2),
            "oscillation_cross_span_m": round(cross_span, 2),
            "oscillation_path_efficiency": round(path_efficiency, 3),
            "oscillation_recent_revisit": round(recent_revisit, 3),
            "recent_path_m": round(recent_path, 2),
            "net_displacement_m": round(net, 2),
            "straightness": round(straightness, 3),
            "oscillation_checks": checks,
        })
        return metrics

    def _v146_apply_progress_evidence(self, metrics, now):
        state = self._v146_progress_state
        bbox = metrics.get("bbox")
        best_bbox = self._v147_state.get("best_bbox")
        if best_bbox is None and bbox is not None:
            best_bbox = tuple(bbox)
            self._v147_state["best_bbox"] = best_bbox

        envelope_growth = self._v147_bbox_growth(bbox, best_bbox)
        unique = int(metrics.get("unique_cells", 0) or 0)
        diag = float(metrics.get("diag_m", 0.0) or 0.0)
        unique_gain = unique - int(state.get("best_unique", 0) or 0)
        diag_gain = diag - float(state.get("best_diag", 0.0) or 0.0)
        net = float(metrics.get("net_displacement_m", 0.0) or 0.0)
        recent_new = int(metrics.get("recent_new_cells", 0) or 0)
        oscillation = bool(metrics.get("oscillation_evidence"))

        substantial_unique = bool(
            unique_gain >= self.REAL_UNIQUE_GAIN
            and recent_new >= self.REAL_UNIQUE_GAIN
            and (
                net >= 0.45
                or float(metrics.get("recent_span_m", 0.0) or 0.0) >= 0.80
            )
        )
        directional = bool(
            metrics.get("directional_progress")
            and net >= self.REAL_DIRECTIONAL_NET_M
        )
        real_progress = bool(
            not oscillation
            and (
                envelope_growth >= self.REAL_ENVELOPE_GROWTH_M
                or diag_gain >= self.AI_PROGRESS_DIAG_GAIN
                or substantial_unique
                or directional
                or bool(metrics.get("corridor_progress"))
            )
        )

        if real_progress:
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
            state["bad_streak"] = 0
            self._v143_bad_pattern_streak = 0
            self._v146_last_good_progress_at = now
            self._v147_state["last_real_progress_at"] = now
            self._v147_state["last_real_progress_reason"] = (
                f"envelope+{envelope_growth:.2f}m "
                f"diag+{diag_gain:.2f}m unique+{unique_gain} net={net:.2f}m"
            )
            if bbox is not None:
                self._v147_state["best_bbox"] = self._v147_bbox_union(best_bbox, bbox)
        else:
            state["good_streak"] = 0

        last_progress = float(
            self._v147_state.get(
                "last_real_progress_at",
                state.get("last_progress_at", now),
            )
            or now
        )
        no_progress_s = max(0.0, now - last_progress)
        state["last_progress_at"] = last_progress

        metrics["progress_now"] = real_progress
        metrics["real_progress"] = real_progress
        metrics["unique_gain"] = int(unique_gain)
        metrics["diag_gain_m"] = round(diag_gain, 2)
        metrics["envelope_growth_m"] = round(envelope_growth, 2)
        metrics["no_progress_s"] = round(no_progress_s, 1)
        metrics["best_unique_cells"] = int(state.get("best_unique", 0) or 0)
        metrics["best_diag_m"] = round(float(state.get("best_diag", 0.0) or 0.0), 2)
        self._v147_state["last_envelope_growth_m"] = round(envelope_growth, 2)
        return metrics

    def _v146_bad_evidence(self, metrics):
        if str(metrics.get("pattern") or "") == "oscillation_corridor":
            confidence = float(metrics.get("confidence", 0.0) or 0.0)
            no_progress = float(metrics.get("no_progress_s", 0.0) or 0.0)
            reversals = int(metrics.get("oscillation_reversals", 0) or 0)
            bad = bool(
                confidence >= self.OSC_MIN_CONFIDENCE
                and no_progress >= self.OSC_MIN_NO_PROGRESS_SECONDS
                and reversals >= self.OSC_MIN_REVERSALS
                and not bool(metrics.get("real_progress"))
            )
            return (
                bad,
                "oscilación ida/vuelta confirmada"
                if bad
                else "oscilación todavía sin consenso suficiente",
            )
        return super()._v146_bad_evidence(metrics)

    def _v147_escape_success(self, metrics, now):
        if not self._v147_escape_awaiting_validation:
            return False
        if now - float(self._v147_escape_done_at or 0.0) < self.ESCAPE_MIN_VALIDATE_SECONDS:
            return False

        growth = self._v147_bbox_growth(
            metrics.get("bbox"),
            self._v147_escape_pre_bbox,
        )
        net = float(metrics.get("net_displacement_m", 0.0) or 0.0)
        reversals = int(metrics.get("oscillation_reversals", 0) or 0)
        success = bool(
            growth >= self.ESCAPE_SUCCESS_GROWTH_M
            or (
                not bool(metrics.get("oscillation_evidence"))
                and net >= 0.90
                and reversals < self.OSC_MIN_REVERSALS
            )
        )
        if not success:
            return False

        self._v147_escape_awaiting_validation = False
        self._v147_escape_consecutive = 0
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v143_bad_pattern_streak = 0
        self._v147_state["last_real_progress_at"] = now
        self._v146_progress_state["last_progress_at"] = now
        self._v141_log(
            "V147 escape validado",
            growth=round(growth, 2),
            net=round(net, 2),
            reversals=reversals,
        )
        self._post_ui(
            "v147_escape_validated",
            round(growth, 2),
            round(net, 2),
        )
        return True

    def _v147_schedule_escape(self, serial, metrics):
        if self._v147_escape_active:
            return False
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if int(getattr(self, "mapping_phase", 0) or 0) != 1:
            return False
        if self._v147_escape_total >= self.ESCAPE_MAX_TOTAL:
            return False

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False

        self._v147_escape_active = True
        self._v147_escape_total += 1
        self._v147_escape_consecutive += 1
        attempt = self._v147_escape_consecutive
        total = self._v147_escape_total
        self._v147_escape_pre_bbox = metrics.get("bbox")
        self._v147_escape_awaiting_validation = False

        idx = min(max(0, attempt - 1), len(self.ESCAPE_REVERSE_SECONDS) - 1)
        reverse_seconds = float(self.ESCAPE_REVERSE_SECONDS[idx])
        turn_seconds = float(self.ESCAPE_TURN_SECONDS[idx])
        turn = 2 if total % 2 else 3
        direction = "izquierda" if turn == 2 else "derecha"

        record = {
            "attempt": attempt,
            "total": total,
            "reverse_s": reverse_seconds,
            "turn_s": turn_seconds,
            "turn": direction,
            "trigger": dict(metrics),
            "success": None,
            "error": None,
        }
        self._v147_escape_history.append(record)
        self._v147_escape_history = self._v147_escape_history[-12:]

        self._v141_log(
            "V147 escape iniciado",
            attempt=attempt,
            total=total,
            reverse_s=reverse_seconds,
            turn_s=turn_seconds,
            turn=direction,
            reversals=metrics.get("oscillation_reversals"),
            recent_path=metrics.get("recent_path_m"),
            net=metrics.get("net_displacement_m"),
        )
        self._post_ui("v147_escape_started", attempt, total, direction)

        def worker():
            try:
                if (
                    serial != int(getattr(self, "_v74_mapping_serial", -1))
                    or vacuum is not getattr(self, "vacuum", None)
                    or not bool(getattr(self, "mapping_active", False))
                    or int(getattr(self, "mapping_phase", 0) or 0) != 1
                ):
                    raise RuntimeError("la sesión cambió antes del escape")

                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.40)

                vacuum.manual(4)
                time.sleep(reverse_seconds)
                vacuum.manual(5)
                time.sleep(0.25)

                vacuum.manual(turn)
                time.sleep(turn_seconds)
                vacuum.manual(5)
                time.sleep(0.30)

                if (
                    serial != int(getattr(self, "_v74_mapping_serial", -1))
                    or not bool(getattr(self, "mapping_active", False))
                    or int(getattr(self, "mapping_phase", 0) or 0) != 1
                ):
                    raise RuntimeError("la sesión dejó de estar activa durante el escape")

                edge = self._v138_start_factory_edge(
                    vacuum,
                    f"reanudación V147 escape {attempt}",
                )
                if not bool((edge or {}).get("success")):
                    raise RuntimeError(
                        str((edge or {}).get("error") or "EDGE no confirmó movimiento")
                    )

                self._post_ui("v147_escape_done", attempt, total)
            except Exception as exc:
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                self._post_ui(
                    "v147_escape_error",
                    attempt,
                    total,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name=f"AspiradoraV147Escape{total}",
            daemon=True,
        ).start()
        return True

    def _v147_request_abort(self, serial, metrics, reason):
        if self._v144_auto_abort_requested:
            return
        self._v144_auto_abort_requested = True
        tagged = dict(metrics or {})
        tagged["reason"] = str(reason)
        tagged["escape_total"] = int(self._v147_escape_total)
        tagged["escape_consecutive"] = int(self._v147_escape_consecutive)
        tagged["pattern"] = "oscillation_corridor"
        self._post_ui("v144_ai_auto_abort", serial, tagged)

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

                oscillating = bool(metrics.get("oscillation_evidence"))
                self._v147_last_oscillation = dict(metrics)
                self._v147_oscillation_votes.append(bool(oscillating))
                self._v147_oscillation_votes = self._v147_oscillation_votes[-8:]
                osc_votes = sum(1 for item in self._v147_oscillation_votes if item)
                self._v147_oscillation_streak = (
                    self._v147_oscillation_streak + 1 if oscillating else 0
                )
                metrics["oscillation_votes_8"] = osc_votes
                metrics["oscillation_streak"] = self._v147_oscillation_streak

                if self._v147_escape_success(metrics, now):
                    oscillating = False

                if phase == 1:
                    self._v143_bad_pattern_streak = (
                        self._v143_bad_pattern_streak + 1 if bad else 0
                    )

                    started = getattr(self, "_v74_started_at", None)
                    try:
                        elapsed = max(0.0, now - float(started)) if started is not None else 0.0
                    except Exception:
                        elapsed = 0.0
                    metrics["elapsed_s"] = round(elapsed, 1)

                    in_grace = now < float(self._v147_escape_grace_until or 0.0)
                    metrics["escape_grace_s"] = round(
                        max(0.0, float(self._v147_escape_grace_until or 0.0) - now),
                        1,
                    )

                    if (
                        self._v147_escape_awaiting_validation
                        and not in_grace
                        and oscillating
                        and not self._v147_escape_active
                    ):
                        self._v147_escape_awaiting_validation = False
                        self._v141_log(
                            "V147 escape no logró expansión suficiente",
                            consecutive=self._v147_escape_consecutive,
                            total=self._v147_escape_total,
                        )

                    if (
                        oscillating
                        and bad
                        and not self._v147_escape_active
                        and not in_grace
                    ):
                        eligible_escape = bool(
                            osc_votes >= self.OSC_VOTES_REQUIRED
                            and self._v147_oscillation_streak >= self.OSC_STREAK_REQUIRED
                            and elapsed >= self.OSC_MIN_SESSION_SECONDS
                            and float(metrics.get("path_m", 0.0) or 0.0)
                            >= self.OSC_MIN_TOTAL_PATH_M
                            and float(metrics.get("no_progress_s", 0.0) or 0.0)
                            >= self.OSC_MIN_NO_PROGRESS_SECONDS
                        )

                        if eligible_escape:
                            if (
                                self._v147_escape_consecutive
                                >= self.ESCAPE_MAX_CONSECUTIVE
                                or self._v147_escape_total >= self.ESCAPE_MAX_TOTAL
                            ):
                                reason = (
                                    "IA V147 confirmó oscilación persistente después de "
                                    f"{self._v147_escape_consecutive} escapes consecutivos "
                                    f"({self._v147_escape_total} en la sesión)"
                                )
                                self._v143_phase1_invalid_reason = reason
                                self._v147_request_abort(serial, metrics, reason)
                            else:
                                self._v147_schedule_escape(serial, metrics)

                    elif not oscillating and not self._v147_escape_active:
                        # Los votos de oscilación se limpian gradualmente cuando
                        # el robot deja de invertir sobre el mismo eje.
                        if self._v147_oscillation_votes:
                            self._v147_oscillation_votes = self._v147_oscillation_votes[-4:]

                    # Los patrones V146 tradicionales siguen protegidos por su
                    # auto-abort, pero la oscilación nueva usa primero escapes.
                    if (
                        not oscillating
                        and bad
                        and self._v143_bad_pattern_streak >= self.AI_BAD_PATTERN_STREAK
                        and bad_votes >= 6
                        and elapsed >= self.AI_AUTO_ABORT_MIN_SECONDS
                        and float(metrics.get("path_m", 0.0) or 0.0)
                        >= self.AI_AUTO_ABORT_MIN_PATH_M
                    ):
                        pattern = str(metrics.get("pattern") or "")
                        required = (
                            self.AI_STUCK_NO_PROGRESS_SECONDS
                            if pattern == "stuck"
                            else self.AI_LOOP_NO_PROGRESS_SECONDS
                        )
                        if float(metrics.get("no_progress_s", 0.0) or 0.0) >= required:
                            reason = (
                                "IA V147/V146 confirmó "
                                f"{pattern} por consenso multiseñal "
                                f"(sin progreso {float(metrics.get('no_progress_s', 0.0)):.0f}s)"
                            )
                            self._v143_phase1_invalid_reason = reason
                            self._v147_request_abort(serial, metrics, reason)

                signature = (
                    metrics.get("pattern"),
                    metrics.get("oscillation_reversals"),
                    metrics.get("oscillation_evidence"),
                    metrics.get("real_progress"),
                    metrics.get("bad_consensus"),
                    self._v147_escape_total,
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
                    "oscillation": bool(metrics.get("oscillation_evidence")),
                    "oscillation_reversals": metrics.get("oscillation_reversals"),
                    "oscillation_votes_8": osc_votes,
                    "escape_total": int(self._v147_escape_total),
                    "escape_consecutive": int(self._v147_escape_consecutive),
                }
            except Exception as exc:
                self._v142_mapping_diag = {
                    "error": str(exc).strip() or type(exc).__name__,
                    "phase": phase,
                }

            time.sleep(2.0)

    def _handle_ui_event(self, kind, payload):
        if kind == "v147_escape_started":
            attempt = int(payload[0])
            total = int(payload[1])
            direction = str(payload[2])
            self._set_banner(
                "IA V147 detectó ida/vuelta repetido · "
                f"escape {attempt}/{self.ESCAPE_MAX_CONSECUTIVE}: "
                f"retroceso + giro a {direction} · misma sesión de mapa."
            )
            return None

        if kind == "v147_escape_done":
            attempt = int(payload[0])
            total = int(payload[1])
            self._v147_escape_active = False
            now = time.monotonic()
            self._v147_escape_done_at = now
            self._v147_escape_grace_until = now + self.ESCAPE_GRACE_SECONDS
            self._v147_escape_awaiting_validation = True
            self._v147_oscillation_streak = 0
            self._v147_oscillation_votes = []
            self._v143_bad_pattern_streak = 0
            self._v147_state["last_real_progress_at"] = now
            self._v146_progress_state["last_progress_at"] = now
            if self._v147_escape_history:
                self._v147_escape_history[-1]["success"] = True
            self._v141_log(
                "V147 escape físico completado; validando expansión",
                attempt=attempt,
                total=total,
                grace_s=self.ESCAPE_GRACE_SECONDS,
            )
            self._set_banner(
                "Escape V147 ejecutado · EDGE reanudado en la misma sesión · "
                "validando si el robot salió del corredor."
            )
            return None

        if kind == "v147_escape_validated":
            growth = float(payload[0])
            net = float(payload[1])
            self._set_banner(
                "IA V147 confirmó salida del patrón repetitivo · "
                f"expansión +{growth:.2f} m · desplazamiento {net:.2f} m · "
                "continúa el mapeo."
            )
            return None

        if kind == "v147_escape_error":
            attempt = int(payload[0])
            total = int(payload[1])
            error = str(payload[2])
            self._v147_escape_active = False
            self._v147_escape_error = error
            if self._v147_escape_history:
                self._v147_escape_history[-1]["success"] = False
                self._v147_escape_history[-1]["error"] = error
            self._v141_log(
                "V147 escape falló",
                attempt=attempt,
                total=total,
                error=error,
            )
            serial = int(getattr(self, "_v74_mapping_serial", -1))
            metrics = dict(self._v147_last_oscillation or {})
            reason = (
                "V147 no pudo completar la maniobra de escape; "
                "se cierra la sesión y se solicita regreso seguro"
            )
            self._v143_phase1_invalid_reason = reason
            self._v147_request_abort(serial, metrics, reason)
            return None

        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V147-IA ACTIVO · oscilación + escape adaptativo",
            "============================================================",
            f"oscilación={self._v147_last_oscillation or '—'}",
            f"racha/votos={self._v147_oscillation_streak}/{sum(1 for x in self._v147_oscillation_votes if x)} de {len(self._v147_oscillation_votes)}",
            f"escape activo={self._v147_escape_active} · total={self._v147_escape_total}/{self.ESCAPE_MAX_TOTAL} · consecutivos={self._v147_escape_consecutive}/{self.ESCAPE_MAX_CONSECUTIVE}",
            f"esperando validar escape={self._v147_escape_awaiting_validation} · gracia restante={max(0.0, self._v147_escape_grace_until - time.monotonic()):.1f}s",
            f"estado progreso real={self._v147_state or '—'}",
            f"historial escapes={self._v147_escape_history or '—'}",
            f"último error escape={self._v147_escape_error or '—'}",
            "regla V147: celdas nuevas pequeñas NO bastan para declarar progreso si hay ida/vuelta repetido",
            "regla V147: oscilación exige reversiones + baja eficiencia + poco desplazamiento neto + corredor estrecho",
            "regla V147: primer objetivo = escapar y continuar la MISMA sesión; no crea otro build-map",
            "regla V147: escape = stop controlado + retroceso + giro alternado + reanudar EDGE 2/1",
            "regla V147: cada escape debe demostrar expansión real; si no, escala la maniobra",
            "regla V147: tras 3 escapes consecutivos fallidos se cierra Paso1 y vuelve a base",
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

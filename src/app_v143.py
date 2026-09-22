import math
import threading
import time

import app_v141
import app_v142
import app_v9


class App(app_v142.App):
    """V143-IA: una sesión=un aprendizaje + gate físico antes del Paso 2."""

    AI_MAPPING_CELL = 0.35
    AI_BAD_PATTERN_CONFIDENCE = 0.82
    AI_BAD_PATTERN_STREAK = 3

    def __init__(self):
        self._v143_mapping_session_key = None
        self._v143_bad_pattern_streak = 0
        self._v143_phase1_invalid_reason = None
        self._v143_phase1_quality = {}
        self._v143_manual_return_requested = False
        self._v143_session_committed = False
        self._v143_last_commit = {}
        super().__init__()

    # ====================================================== clasificador IA
    def _v142_classify_path(self, points):
        if len(points) < 8:
            return {
                "pattern": "insufficient",
                "confidence": 0.0,
                "points": len(points),
            }

        path = 0.0
        for a, b in zip(points, points[1:]):
            path += math.hypot(b[0] - a[0], b[1] - a[1])

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        diag = math.hypot(span_x, span_y)
        cell = self.AI_MAPPING_CELL
        unique = {
            (int(round(x / cell)), int(round(y / cell)))
            for x, y in points
        }
        revisit = 1.0 - min(1.0, len(unique) / max(1.0, len(points)))

        recent = points[-30:]
        recent_path = 0.0
        for a, b in zip(recent, recent[1:]):
            recent_path += math.hypot(b[0] - a[0], b[1] - a[1])
        rxs = [p[0] for p in recent]
        rys = [p[1] for p in recent]
        recent_span = (
            math.hypot(max(rxs) - min(rxs), max(rys) - min(rys))
            if recent else 0.0
        )

        if (
            len(recent) >= 20
            and recent_path >= 2.0
            and recent_span <= 0.55
        ):
            pattern = "stuck"
            confidence = min(0.99, 0.90 + (0.55 - recent_span) * 0.12)
        elif (
            path >= 5.0
            and revisit >= 0.62
            and diag <= 3.0
        ):
            pattern = "spiral_or_loop"
            confidence = min(0.99, 0.74 + revisit * 0.26)
        elif (
            path >= 8.0
            and revisit >= 0.78
            and len(unique) <= 24
        ):
            pattern = "spiral_or_loop"
            confidence = min(0.99, 0.78 + revisit * 0.22)
        elif diag >= 2.5 and len(unique) >= 10 and revisit < 0.78:
            pattern = "expanding"
            confidence = min(0.96, 0.62 + diag / 15.0)
        else:
            pattern = "mixed"
            confidence = 0.58

        return {
            "pattern": pattern,
            "confidence": round(confidence, 3),
            "path_m": round(path, 2),
            "span_x": round(span_x, 2),
            "span_y": round(span_y, 2),
            "diag_m": round(diag, 2),
            "unique_cells": len(unique),
            "revisit_ratio": round(revisit, 3),
            "recent_path_m": round(recent_path, 2),
            "recent_span_m": round(recent_span, 2),
            "points": len(points),
        }

    def _v143_phase1_metrics(self):
        try:
            snapshot = self.local_map.snapshot()
            points = self._v142_xy_points(snapshot, phase=1)
        except Exception:
            points = []
        metrics = self._v142_classify_path(points[-220:])
        metrics["all_phase1_points"] = len(points)
        return metrics

    def _v143_phase1_is_valid(self):
        metrics = self._v143_phase1_metrics()
        reason = None

        if self._v143_manual_return_requested:
            reason = "regreso manual solicitado durante Paso 1"
        elif self._v143_phase1_invalid_reason:
            reason = self._v143_phase1_invalid_reason
        elif metrics.get("pattern") in ("stuck", "spiral_or_loop") and float(
            metrics.get("confidence", 0.0) or 0.0
        ) >= self.AI_BAD_PATTERN_CONFIDENCE:
            reason = (
                f"patrón {metrics.get('pattern')} "
                f"({float(metrics.get('confidence', 0.0)):.2f})"
            )
        elif metrics.get("pattern") == "insufficient":
            reason = "trayectoria insuficiente para validar Paso 1"
        elif int(metrics.get("unique_cells", 0) or 0) < 8:
            reason = "cobertura insuficiente para validar Paso 1"

        metrics["valid"] = reason is None
        metrics["reason"] = reason
        self._v143_phase1_quality = dict(metrics)
        return reason is None, reason, metrics

    # ============================================== monitor: no multiplica sesión
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
                metrics = self._v142_classify_path(points[-180:])
                metrics["phase"] = phase
                signature = (
                    metrics.get("pattern"),
                    metrics.get("unique_cells"),
                    len(points),
                )
                if signature != last_signature:
                    self._v142_mapping_diag = dict(metrics)
                    last_signature = signature

                if phase == 1:
                    bad = (
                        metrics.get("pattern") in ("stuck", "spiral_or_loop")
                        and float(metrics.get("confidence", 0.0) or 0.0)
                        >= self.AI_BAD_PATTERN_CONFIDENCE
                    )
                    self._v143_bad_pattern_streak = (
                        self._v143_bad_pattern_streak + 1 if bad else 0
                    )
                    if self._v143_bad_pattern_streak >= self.AI_BAD_PATTERN_STREAK:
                        self._v143_phase1_invalid_reason = (
                            "IA detectó "
                            f"{metrics.get('pattern')} sostenido "
                            f"(confianza {float(metrics.get('confidence', 0.0)):.2f})"
                        )
            except Exception as exc:
                self._v142_mapping_diag = {
                    "error": str(exc).strip() or type(exc).__name__,
                    "phase": phase,
                }
            time.sleep(2.0)

    def _v142_start_mapping_ai(self):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        serial = int(getattr(self, "_v74_mapping_serial", -1))
        self._v143_mapping_session_key = f"map-{serial}-{int(time.time())}"
        self._v143_bad_pattern_streak = 0
        self._v143_phase1_invalid_reason = None
        self._v143_phase1_quality = {}
        self._v143_manual_return_requested = False
        self._v143_session_committed = False
        self._v142_mapping_token += 1
        token = self._v142_mapping_token
        threading.Thread(
            target=self._v142_mapping_monitor,
            args=(token, serial),
            name="AspiradoraAIMappingMonitorV143",
            daemon=True,
        ).start()
        return True

    # ============================================ Paso1 -> Paso2 con gate IA
    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        valid, reason, metrics = self._v143_phase1_is_valid()
        self._v141_log(
            "IA valida Paso1",
            valid=valid,
            reason=reason,
            pattern=metrics.get("pattern"),
            confidence=metrics.get("confidence"),
        )

        if not valid:
            self._v137_flow = "phase1-invalid-ai"
            self._v74_watch_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
            try:
                self._sync_mapping_step_buttons()
            except Exception:
                pass
            self._set_banner(
                "Paso 1 rechazado por IA · proceso finalizó. "
                f"{reason}. Paso 2 no fue iniciado."
            )
            self._v143_commit_mapping_session(
                final_reason="phase1_rejected",
                phase1_valid=False,
            )
            return False

        return app_v141.App._v121_request_phase2(
            self,
            vacuum,
            serial,
            source,
            sweep_type,
        )

    def dock(self):
        if (
            bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
        ):
            self._v143_manual_return_requested = True
        return super().dock()

    # ================================================ una sesión = un registro
    def _v143_commit_mapping_session(
        self,
        final_reason,
        phase1_valid=None,
        final_grid_saved=None,
    ):
        if self._v143_session_committed or self._v142_ai is None:
            return False
        key = str(self._v143_mapping_session_key or "")
        if not key:
            return False

        if phase1_valid is None:
            phase1_valid = bool(
                (self._v143_phase1_quality or {}).get("valid", False)
            )
        metrics = dict(self._v142_mapping_diag or {})
        metrics.update({
            "session_key": key,
            "serial": int(getattr(self, "_v74_mapping_serial", -1)),
            "final_reason": str(final_reason),
            "phase1_valid": bool(phase1_valid),
            "phase1_quality": dict(self._v143_phase1_quality or {}),
            "manual_return_requested": bool(self._v143_manual_return_requested),
        })
        if final_grid_saved is not None:
            metrics["final_grid_saved"] = bool(final_grid_saved)

        self._v143_last_commit = self._v142_ai.record_mapping_session(
            key,
            metrics,
        )
        self._v143_session_committed = True
        self._v142_refresh_ai_summary()
        return True

    # ============================================================= eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v107_final_grid_done":
            # Saltamos sólo el registro repetido de V142; el resto de la cadena
            # de finalización sigue ejecutándose desde V141 hacia abajo.
            result = app_v141.App._handle_ui_event(self, kind, payload)
            self._v143_commit_mapping_session(
                final_reason="final_grid_done",
                final_grid_saved=bool(
                    getattr(self, "_v107_final_saved", False)
                ),
            )
            return result

        if kind == "v121_phase2_error":
            result = super()._handle_ui_event(kind, payload)
            self._v143_commit_mapping_session(
                final_reason="phase2_error",
            )
            return result

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        summary = self._v142_refresh_ai_summary()
        lines = [
            "DIAGNÓSTICO V143-IA ACTIVO · gate físico + una sesión=un aprendizaje",
            "====================================================================",
            f"memoria IA={summary}",
            f"clave sesión={self._v143_mapping_session_key or '—'}",
            f"calidad Paso1={self._v143_phase1_quality or '—'}",
            f"invalidez Paso1={self._v143_phase1_invalid_reason or '—'}",
            f"regreso manual Paso1={self._v143_manual_return_requested}",
            f"racha patrón malo={self._v143_bad_pattern_streak}",
            f"commit sesión={self._v143_last_commit or '—'}",
            "regla V143: status=4 por sí solo NO habilita Paso2",
            "regla V143: Paso2 requiere Paso1 sin stuck/spiral-loop de alta confianza y cobertura mínima",
            "regla V143: Volver a base durante Paso1 invalida la transición automática",
            "memoria V143: una clave física de mapeo se guarda una sola vez",
            "migración V143: descarta mapping_sessions ruidosas de V142 y conserva aprendizaje por habitación",
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

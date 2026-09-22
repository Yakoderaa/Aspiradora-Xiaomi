import time

import app_v141
import app_v143
import app_v9


class App(app_v143.App):
    """V144-IA: la IA corta un Paso 1 claramente malo y ordena regreso."""

    AI_AUTO_ABORT_MIN_SECONDS = 45.0
    AI_AUTO_ABORT_MIN_PATH_M = 5.0

    def __init__(self):
        self._v144_auto_abort_requested = False
        self._v144_auto_abort_done = False
        self._v144_auto_return_requested = False
        self._v144_auto_abort_reason = None
        self._v144_auto_abort_metrics = {}
        self._v144_auto_abort_count = 0
        super().__init__()

    def _v142_start_mapping_ai(self):
        self._v144_auto_abort_requested = False
        self._v144_auto_abort_done = False
        self._v144_auto_return_requested = False
        self._v144_auto_abort_reason = None
        self._v144_auto_abort_metrics = {}
        self._v144_auto_abort_count = 0
        return super()._v142_start_mapping_ai()

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

                    elapsed = 0.0
                    started = getattr(self, "_v74_started_at", None)
                    if started is not None:
                        try:
                            elapsed = max(0.0, time.monotonic() - float(started))
                        except Exception:
                            elapsed = 0.0

                    eligible = bool(
                        bad
                        and self._v143_bad_pattern_streak
                        >= self.AI_BAD_PATTERN_STREAK
                        and elapsed >= self.AI_AUTO_ABORT_MIN_SECONDS
                        and float(metrics.get("path_m", 0.0) or 0.0)
                        >= self.AI_AUTO_ABORT_MIN_PATH_M
                    )

                    if eligible:
                        reason = (
                            "IA detectó "
                            f"{metrics.get('pattern')} sostenido "
                            f"(confianza {float(metrics.get('confidence', 0.0)):.2f})"
                        )
                        self._v143_phase1_invalid_reason = reason

                        if not self._v144_auto_abort_requested:
                            self._v144_auto_abort_requested = True
                            tagged = dict(metrics)
                            tagged["elapsed_s"] = round(elapsed, 1)
                            tagged["bad_streak"] = int(
                                self._v143_bad_pattern_streak
                            )
                            tagged["reason"] = reason
                            self._post_ui(
                                "v144_ai_auto_abort",
                                serial,
                                tagged,
                            )
            except Exception as exc:
                self._v142_mapping_diag = {
                    "error": str(exc).strip() or type(exc).__name__,
                    "phase": phase,
                }

            time.sleep(2.0)

    def _v144_execute_auto_abort(self, serial, metrics):
        if self._v144_auto_abort_done:
            return False
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if int(getattr(self, "mapping_phase", 0) or 0) != 1:
            return False

        metrics = dict(metrics or {})
        reason = str(
            metrics.get("reason")
            or self._v143_phase1_invalid_reason
            or "patrón de navegación inválido"
        )
        self._v144_auto_abort_done = True
        self._v144_auto_return_requested = True
        self._v144_auto_abort_reason = reason
        self._v144_auto_abort_metrics = dict(metrics)
        self._v144_auto_abort_count += 1

        quality = dict(metrics)
        quality["valid"] = False
        quality["reason"] = reason
        quality["auto_aborted"] = True
        self._v143_phase1_quality = quality
        self._v143_phase1_invalid_reason = reason

        # Cerramos la máquina de estados ANTES de enviar dock para que una
        # llegada rápida a status=4 jamás pueda disparar Paso 2.
        self._v137_flow = "phase1-auto-abort-ai"
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

        self._v141_log(
            "IA detuvo Paso1 automáticamente",
            reason=reason,
            pattern=metrics.get("pattern"),
            confidence=metrics.get("confidence"),
            path_m=metrics.get("path_m"),
            bad_streak=metrics.get("bad_streak"),
        )

        self._v143_commit_mapping_session(
            final_reason="ai_auto_abort_phase1",
            phase1_valid=False,
        )

        self._set_banner(
            "IA detectó recorrido repetitivo · Paso 1 detenido · "
            "regreso automático a base · proceso finalizó."
        )

        try:
            # Llamamos a V141 directamente para enviar el regreso sin marcarlo
            # como intervención manual de V143.
            app_v141.App.dock(self)
            self._v141_log(
                "regreso automático IA solicitado",
                success=True,
                reason=reason,
            )
            return True
        except Exception as exc:
            self._v141_log(
                "regreso automático IA solicitado",
                success=False,
                reason=reason,
                error=str(exc).strip() or type(exc).__name__,
            )
            self._set_banner(
                "IA detuvo Paso 1 y guardó la sesión · "
                "no pudo ordenar el regreso automático. Proceso finalizó."
            )
            return False

    def _handle_ui_event(self, kind, payload):
        if kind == "v144_ai_auto_abort":
            serial = int(payload[0]) if payload else -1
            metrics = payload[1] if len(payload) > 1 else {}
            self._v144_execute_auto_abort(serial, metrics)
            return None
        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V144-IA ACTIVO · detección + acción autónoma segura",
            "===============================================================",
            f"auto-abort solicitado={self._v144_auto_abort_requested}",
            f"auto-abort ejecutado={self._v144_auto_abort_done}",
            f"regreso automático IA={self._v144_auto_return_requested}",
            f"motivo auto-abort={self._v144_auto_abort_reason or '—'}",
            f"métricas auto-abort={self._v144_auto_abort_metrics or '—'}",
            f"auto-abort count={self._v144_auto_abort_count}",
            "regla V144: 3 detecciones malas consecutivas + >=45 s + >=5 m -> detener Paso1",
            "regla V144: el estado de mapeo se cierra antes de enviar dock, por lo que Paso2 queda bloqueado",
            "regla V144: la sesión fallida se guarda una sola vez antes del regreso automático",
            "regla V144: regreso IA y regreso manual quedan diferenciados en diagnóstico",
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

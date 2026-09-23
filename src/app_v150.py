import math
import threading
import time

import app_v149
import app_v9


class App(app_v149.App):
    """V150-IA: salud de estrategia V82 separada del antiatasco físico."""

    # Detector de "EDGE ejecuta movimiento, pero no explora la vivienda".
    # Usa EXCLUSIVAMENTE la trayectoria corregida V82.
    STRATEGY_MIN_SECONDS = 105.0
    STRATEGY_MIN_SAMPLES = 90
    STRATEGY_MIN_PATH_M = 12.0
    STRATEGY_MIN_ALONG_M = 1.40
    STRATEGY_MAX_CROSS_M = 1.10
    STRATEGY_MAX_2D_RATIO = 0.34
    STRATEGY_MIN_REVERSALS = 10
    STRATEGY_MIN_PATH_TO_ALONG = 3.20

    STRATEGY_RECENT_POINTS = 80
    STRATEGY_RECENT_MIN_PATH_M = 4.0
    STRATEGY_RECENT_MIN_REVERSALS = 4
    STRATEGY_RECENT_MAX_2D_RATIO = 0.55

    STRATEGY_VOTES_REQUIRED = 4
    STRATEGY_MONITOR_INTERVAL = 2.0

    # Cambio físico EDGE -> whole-home. Nunca rearma build-map.
    TRANSITION_STOP_TIMEOUT = 8.0
    TRANSITION_POLL_SECONDS = 0.30

    def __init__(self):
        self._v150_strategy_state = "idle"
        self._v150_strategy_votes = 0
        self._v150_strategy_confirmed = False
        self._v150_strategy_posted = False
        self._v150_strategy_diag = {}
        self._v150_strategy_checks = 0
        self._v150_strategy_blocks = 0
        self._v150_transition_diag = {}
        self._v150_manual_cancel = False
        super().__init__()

    def _v147_reset_state(self):
        result = super()._v147_reset_state()
        self._v150_strategy_state = "edge_observing"
        self._v150_strategy_votes = 0
        self._v150_strategy_confirmed = False
        self._v150_strategy_posted = False
        self._v150_strategy_diag = {}
        self._v150_strategy_checks = 0
        self._v150_strategy_blocks = 0
        self._v150_transition_diag = {}
        self._v150_manual_cancel = False
        return result

    # ================================================= estrategia: sólo V82
    @staticmethod
    def _v150_path_length(samples):
        total = 0.0
        for a, b in zip(samples, samples[1:]):
            try:
                total += math.hypot(
                    float(b[1]) - float(a[1]),
                    float(b[2]) - float(a[2]),
                )
            except Exception:
                continue
        return float(total)

    def _v150_strategy_metrics(self, samples, elapsed_s):
        samples = list(samples or [])
        metrics = {
            "evidence": False,
            "samples": len(samples),
            "elapsed_s": round(float(elapsed_s or 0.0), 1),
            "source": "V82 corrected samples",
        }
        if len(samples) < 3:
            metrics["reason"] = "muestras corregidas insuficientes"
            return metrics

        geometry = self._v77_corridor_geometry(
            samples,
            self.CORRIDOR_STEP_EPSILON,
        ) or {}
        along = float(geometry.get("along_span", 0.0) or 0.0)
        cross = float(geometry.get("cross_span", 0.0) or 0.0)
        reversals = int(geometry.get("reversals", 0) or 0)
        path_m = self._v150_path_length(samples)
        ratio = cross / max(along, 1e-9) if along > 0.0 else 1.0
        path_to_along = path_m / max(along, 1e-9) if along > 0.0 else 0.0

        recent = samples[-self.STRATEGY_RECENT_POINTS:]
        recent_geometry = self._v77_corridor_geometry(
            recent,
            self.CORRIDOR_STEP_EPSILON,
        ) or {}
        recent_along = float(
            recent_geometry.get("along_span", 0.0) or 0.0
        )
        recent_cross = float(
            recent_geometry.get("cross_span", 0.0) or 0.0
        )
        recent_reversals = int(
            recent_geometry.get("reversals", 0) or 0
        )
        recent_path = self._v150_path_length(recent)
        recent_ratio = (
            recent_cross / max(recent_along, 1e-9)
            if recent_along > 0.0
            else 1.0
        )

        checks = {
            "enough_time": float(elapsed_s or 0.0) >= self.STRATEGY_MIN_SECONDS,
            "enough_samples": len(samples) >= self.STRATEGY_MIN_SAMPLES,
            "enough_path": path_m >= self.STRATEGY_MIN_PATH_M,
            "has_extent": along >= self.STRATEGY_MIN_ALONG_M,
            "cross_limited": cross <= self.STRATEGY_MAX_CROSS_M,
            "low_2d_ratio": ratio <= self.STRATEGY_MAX_2D_RATIO,
            "many_reversals": reversals >= self.STRATEGY_MIN_REVERSALS,
            "wasted_distance": path_to_along >= self.STRATEGY_MIN_PATH_TO_ALONG,
            "recent_path": recent_path >= self.STRATEGY_RECENT_MIN_PATH_M,
            "recent_reversals": (
                recent_reversals >= self.STRATEGY_RECENT_MIN_REVERSALS
            ),
            "recent_still_narrow": (
                recent_ratio <= self.STRATEGY_RECENT_MAX_2D_RATIO
            ),
        }
        evidence = all(checks.values())

        metrics.update({
            "evidence": bool(evidence),
            "path_m": round(path_m, 2),
            "along_span_m": round(along, 2),
            "cross_span_m": round(cross, 2),
            "ratio_2d": round(ratio, 3),
            "reversals": reversals,
            "path_to_along": round(path_to_along, 2),
            "recent_path_m": round(recent_path, 2),
            "recent_along_span_m": round(recent_along, 2),
            "recent_cross_span_m": round(recent_cross, 2),
            "recent_ratio_2d": round(recent_ratio, 3),
            "recent_reversals": recent_reversals,
            "checks": checks,
            "reason": (
                "EDGE recorre y revierte, pero no gana dimensión transversal"
                if evidence
                else "todavía no hay evidencia suficiente para abandonar EDGE"
            ),
        })
        return metrics

    def _v150_session_allows_strategy_switch(self, serial):
        return bool(
            serial == int(getattr(self, "_v74_mapping_serial", -1))
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
            and not bool(getattr(self, "mapping_transitioning", False))
            and not bool(getattr(self, "_v145_session_latched", False))
            and not bool(getattr(self, "_v145_reset_guard", False))
            and not bool(getattr(self, "_v143_manual_return_requested", False))
            and not bool(getattr(self, "_v137_manual_cancel", False))
            and not bool(getattr(self, "_v136_manual_abort", False))
            and not bool(getattr(self, "_v74_finish_requested", False))
            and not bool(getattr(self, "_v149_global_requested", False))
            and not bool(getattr(self, "_v147_escape_active", False))
            and not bool(
                getattr(self, "_v147_escape_awaiting_validation", False)
            )
            and not bool(getattr(self, "_v150_manual_cancel", False))
        )

    def _v150_physical_active(self, vacuum):
        try:
            status = self._v67_int(vacuum._value(2, 1))
        except Exception:
            status = None
        return status in (5, 6, 7), status

    def _v150_strategy_monitor(self, token, serial):
        while token == self._v142_mapping_token:
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return
            if not bool(getattr(self, "mapping_active", False)):
                return

            phase = int(getattr(self, "mapping_phase", 0) or 0)
            if phase != 1:
                return

            if not self._v150_session_allows_strategy_switch(serial):
                self._v150_strategy_blocks += 1
                if bool(getattr(self, "_v149_global_requested", False)):
                    return
                time.sleep(self.STRATEGY_MONITOR_INTERVAL)
                continue

            samples = list(getattr(self, "_v82_corrected_samples", ()) or ())
            started = getattr(self, "_v74_started_at", None)
            now = time.monotonic()
            try:
                elapsed = (
                    max(0.0, now - float(started))
                    if started is not None
                    else 0.0
                )
            except Exception:
                elapsed = 0.0

            metrics = self._v150_strategy_metrics(samples, elapsed)
            self._v150_strategy_checks += 1

            if metrics.get("evidence"):
                self._v150_strategy_votes += 1
            else:
                self._v150_strategy_votes = 0

            metrics["votes"] = int(self._v150_strategy_votes)
            metrics["votes_required"] = self.STRATEGY_VOTES_REQUIRED
            self._v150_strategy_diag = dict(metrics)

            if (
                self._v150_strategy_votes >= self.STRATEGY_VOTES_REQUIRED
                and not self._v150_strategy_posted
            ):
                vacuum = getattr(self, "vacuum", None)
                if vacuum is None:
                    return
                active, status = self._v150_physical_active(vacuum)
                metrics["physical_status"] = status
                metrics["physical_active"] = bool(active)
                self._v150_strategy_diag = dict(metrics)

                if not active:
                    # No luchamos contra un retorno, dock o estado inactivo.
                    self._v150_strategy_votes = 0
                    time.sleep(self.STRATEGY_MONITOR_INTERVAL)
                    continue

                if not self._v150_session_allows_strategy_switch(serial):
                    time.sleep(self.STRATEGY_MONITOR_INTERVAL)
                    continue

                self._v150_strategy_posted = True
                self._post_ui(
                    "v150_strategy_confirmed",
                    int(serial),
                    dict(metrics),
                )
                return

            time.sleep(self.STRATEGY_MONITOR_INTERVAL)

    def _v142_start_mapping_ai(self):
        result = super()._v142_start_mapping_ai()
        if not result:
            return result

        token = int(getattr(self, "_v142_mapping_token", 0) or 0)
        serial = int(getattr(self, "_v74_mapping_serial", -1))
        threading.Thread(
            target=self._v150_strategy_monitor,
            args=(token, serial),
            name="AspiradoraStrategyMonitorV150",
            daemon=True,
        ).start()
        return result

    # V149 pedía v148_persistent_strip. V150 permite además la evidencia
    # independiente de estrategia V82. El gate de sesión sigue siendo estricto.
    def _v149_can_switch_global(self, serial, metrics):
        session_ok = bool(
            serial == int(getattr(self, "_v74_mapping_serial", -1))
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 1
            and not bool(getattr(self, "mapping_transitioning", False))
            and not bool(getattr(self, "_v145_session_latched", False))
            and not bool(getattr(self, "_v145_reset_guard", False))
            and not bool(getattr(self, "_v143_manual_return_requested", False))
            and not bool(getattr(self, "_v137_manual_cancel", False))
            and not bool(getattr(self, "_v136_manual_abort", False))
            and not bool(getattr(self, "_v74_finish_requested", False))
            and not bool(getattr(self, "_v150_manual_cancel", False))
        )
        if not session_ok:
            return False

        strategy_evidence = bool(
            self._v150_strategy_confirmed
            or (metrics or {}).get("v150_strategy_evidence")
        )
        physical_escape_evidence = bool(
            (metrics or {}).get("v148_persistent_strip")
            and str((metrics or {}).get("pattern") or "")
            == "oscillation_corridor"
        )
        return bool(strategy_evidence or physical_escape_evidence)

    # ================================================= transición física aislada
    def _v150_transition_session_valid(self, serial, vacuum):
        return bool(
            serial == int(getattr(self, "_v74_mapping_serial", -1))
            and vacuum is getattr(self, "vacuum", None)
            and bool(getattr(self, "mapping_active", False))
            and int(getattr(self, "mapping_phase", 0) or 0) == 2
            and str(getattr(self, "_v121_stage", "")) == "transition"
            and not bool(getattr(self, "_v145_session_latched", False))
            and not bool(getattr(self, "_v145_reset_guard", False))
            and not bool(getattr(self, "_v150_manual_cancel", False))
        )

    def _v150_request_phase2(self, vacuum, serial, reason):
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if vacuum is not getattr(self, "vacuum", None):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if self._v121_phase2_requested:
            return False
        if (
            bool(getattr(self, "_v145_session_latched", False))
            or bool(getattr(self, "_v145_reset_guard", False))
            or bool(getattr(self, "_v150_manual_cancel", False))
        ):
            return False

        self._v121_phase2_requested = True
        self._v121_stage = "transition"
        self._v137_flow = "transition"
        self.mapping_phase = 2
        self.mapping_transitioning = True
        self.mapping_step1_complete = True
        self._v121_phase2_attempts += 1
        self._v137_phase2_starts += 1
        self._v150_strategy_state = "transition_stopping_edge"

        requested_at = time.monotonic()
        diag = {
            "source": "V150 corrected trajectory",
            "reason": str(reason),
            "requested_at": round(requested_at, 3),
            "arm_new_map_called": False,
            "same_build_map": True,
            "status_before": None,
            "sweep_before": None,
            "stop_sent": False,
            "stop_response": None,
            "status_after_stop": None,
            "whole_home_called": False,
            "status_after": None,
            "sweep_type_after": None,
            "success": False,
            "error": None,
            "route": (
                "EDGE activo -> STOP confirmado -> V123 whole-home "
                "7/3 ['',0,1] -> 2/3 sólo si dock"
            ),
        }
        self._v150_transition_diag = dict(diag)

        def worker():
            try:
                before = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status_before = self._v67_int(before.get("status"))
                sweep_before = self._v67_int(before.get("sweep_type"))
                diag["status_before"] = status_before
                diag["sweep_before"] = sweep_before
                self._v150_transition_diag = dict(diag)

                if not self._v150_transition_session_valid(serial, vacuum):
                    raise RuntimeError(
                        "sesión cambió antes de detener EDGE"
                    )

                # Si EDGE sigue físicamente activo, lo terminamos primero.
                # V147 ya probó que STOP + reanudación conserva el build-map;
                # acá NO se ejecuta arm_new_map.
                if status_before in (5, 6, 7):
                    response = vacuum.stop()
                    diag["stop_sent"] = True
                    diag["stop_response"] = repr(response)[:300]
                    self._v150_strategy_state = "transition_waiting_stop"

                    deadline = (
                        time.monotonic() + self.TRANSITION_STOP_TIMEOUT
                    )
                    last_status = status_before
                    while time.monotonic() < deadline:
                        if not self._v150_transition_session_valid(
                            serial,
                            vacuum,
                        ):
                            raise RuntimeError(
                                "sesión cancelada mientras se detenía EDGE"
                            )
                        try:
                            last_status = self._v67_int(
                                vacuum._value(2, 1)
                            )
                        except Exception:
                            last_status = None
                        diag["status_after_stop"] = last_status
                        self._v150_transition_diag = dict(diag)
                        if last_status in (0, 1, 4):
                            break
                        if last_status == 3:
                            raise RuntimeError(
                                "el E10 entró en retorno durante la transición"
                            )
                        time.sleep(self.TRANSITION_POLL_SECONDS)

                    if last_status not in (0, 1, 4):
                        raise RuntimeError(
                            "EDGE no confirmó parada antes de whole-home "
                            f"(status={last_status!r})"
                        )
                elif status_before == 3:
                    raise RuntimeError(
                        "el E10 ya estaba regresando; no se inicia whole-home"
                    )
                elif status_before not in (0, 1, 4, None):
                    raise RuntimeError(
                        "estado físico no apto para transición "
                        f"(status={status_before!r})"
                    )

                if not self._v150_transition_session_valid(serial, vacuum):
                    raise RuntimeError(
                        "sesión cancelada antes de whole-home"
                    )

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                self._v150_strategy_state = "transition_starting_global"
                diag["whole_home_called"] = True
                response = vacuum.start_mapping_whole_home(
                    confirm_timeout=self.PHASE2_CONFIRM_TIMEOUT
                )
                native = dict(
                    getattr(
                        vacuum,
                        "_last_mapping_whole_home_diag",
                        {},
                    )
                    or {}
                )
                status_after = self._v67_int(
                    native.get("status_after")
                )
                sweep_after = self._v67_int(
                    native.get("sweep_type_after")
                )
                diag.update({
                    "status_after": status_after,
                    "sweep_type_after": sweep_after,
                    "response": native.get(
                        "response",
                        repr(response)[:500],
                    ),
                    "native": native,
                    "success": bool(
                        native.get("success")
                        and status_after in (5, 6, 7)
                    ),
                })
                self._v150_transition_diag = dict(diag)

                if not diag["success"]:
                    raise RuntimeError(
                        native.get("error")
                        or (
                            "whole-home V150 no confirmó una nueva salida "
                            f"física (status={status_after!r})"
                        )
                    )

                self._v137_phase2_diag = dict(diag)
                self._post_ui(
                    "v121_phase2_started",
                    serial,
                    dict(diag),
                )
            except Exception as exc:
                self._v121_phase2_errors += 1
                diag["success"] = False
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v150_transition_diag = dict(diag)
                self._v137_phase2_diag = dict(diag)
                self._post_ui(
                    "v121_phase2_error",
                    serial,
                    dict(diag),
                )

        threading.Thread(
            target=worker,
            name="AspiradoraV150EdgeToWholeHome",
            daemon=True,
        ).start()
        return True

    def _v149_start_global_now(self, serial, metrics, reason):
        vacuum = getattr(self, "vacuum", None)
        if not self._v149_can_switch_global(serial, metrics):
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "gate V150 rechazó la transición global",
            })
            return False
        if vacuum is None:
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "robot desconectado",
            })
            return False

        self._v149_transition_count += 1
        self._v147_escape_active = False
        self._v147_escape_awaiting_validation = False
        self._v147_oscillation_streak = 0
        self._v147_oscillation_votes = []
        self._v143_bad_pattern_streak = 0

        self._set_banner(
            "V150 confirmó que EDGE no está explorando en 2D · "
            "deteniendo EDGE antes de cambiar a whole-home en el MISMO mapa…"
        )

        accepted = self._v150_request_phase2(
            vacuum,
            int(serial),
            str(reason),
        )
        self._v149_global_diag["phase2_request_accepted"] = bool(
            accepted
        )
        self._v149_global_diag["transition_owner"] = "V150"

        if not accepted:
            self._v149_global_failed = True
            self._v149_global_diag.update({
                "failed": True,
                "error": "V150 rechazó la transición física",
            })
            return False

        self._v141_log(
            "V150 tomó propiedad exclusiva de EDGE -> whole-home",
            serial=int(serial),
            reason=str(reason),
            arm_new_map_called=False,
        )
        return True

    # ====================================================== cancelación/manual
    def dock(self):
        if str(getattr(self, "_v150_strategy_state", "")).startswith(
            "transition_"
        ):
            self._v150_manual_cancel = True
            self._v150_strategy_state = "manual_return"
            try:
                self._v145_latch_session(
                    "manual_return_v150_transition",
                    close_mapping=False,
                )
            except Exception:
                pass
            self._v141_log(
                "V150 canceló transición por Volver a base manual",
                success=True,
            )
        return super().dock()

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v150_strategy_confirmed":
            serial = int(payload[0]) if payload else -1
            metrics = dict(payload[1] or {}) if len(payload) > 1 else {}

            if not self._v150_session_allows_strategy_switch(serial):
                self._v150_strategy_state = "cancelled_before_transition"
                self._v150_strategy_confirmed = False
                return None

            self._v150_strategy_confirmed = True
            self._v150_strategy_state = "transition_requested"
            metrics["v150_strategy_evidence"] = True
            self._v150_strategy_diag = dict(metrics)

            reason = (
                "V150: trayectoria corregida V82 confirma EDGE improductivo "
                f"(largo {metrics.get('along_span_m')} m, "
                f"ancho {metrics.get('cross_span_m')} m, "
                f"ratio {metrics.get('ratio_2d')}, "
                f"reversiones {metrics.get('reversals')})"
            )
            requested = self._v149_request_global_transition(
                serial,
                metrics,
                reason,
            )
            if not requested:
                self._v150_strategy_state = "transition_rejected"
                self._v150_strategy_confirmed = False
                return None

            self._set_banner(
                "V150: EDGE confirmado como estrategia improductiva · "
                "cambio automático a whole-home sin crear otro mapa."
            )
            return None

        result = super()._handle_ui_event(kind, payload)

        if kind == "v121_phase2_started" and self._v149_global_requested:
            self._v150_strategy_state = "global_active"
            self._v150_strategy_confirmed = False
            self._v150_strategy_votes = 0
            self._set_banner(
                "V150: whole-home confirmado después de detener EDGE · "
                "Fase 2/2 activa en el mismo mapa Xiaomi."
            )
            return result

        if kind == "v121_phase2_error" and self._v149_global_requested:
            self._v150_strategy_state = "global_failed"
            return result

        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V150-IA ACTIVO · estrategia V82 aislada",
            "=====================================================",
            f"estado estrategia={self._v150_strategy_state}",
            (
                f"votos estrategia={self._v150_strategy_votes}/"
                f"{self.STRATEGY_VOTES_REQUIRED}"
            ),
            f"confirmada={self._v150_strategy_confirmed}",
            f"checks/bloqueos={self._v150_strategy_checks}/{self._v150_strategy_blocks}",
            f"métricas V82 estrategia={self._v150_strategy_diag or '—'}",
            f"transición física={self._v150_transition_diag or '—'}",
            f"cancelación manual transición={self._v150_manual_cancel}",
            "regla V150: estrategia improductiva se decide sólo con _v82_corrected_samples",
            "regla V150: V146/V147/V148 siguen detectando progreso/atasco, pero no deciden abandonar EDGE",
            "regla V150: atasco físico y fallo de estrategia son estados independientes",
            "regla V150: al confirmar fallo de EDGE se bloquean escapes y auto-aborts competidores",
            "regla V150: transición activa = STOP EDGE -> confirmar estado no activo -> whole-home V123",
            "regla V150: nunca ejecuta arm_new_map durante la transición; conserva el mismo build-map",
            "regla V150: status=3/retorno, cerrojo V145, reset o Volver a base cancelan la transición",
            "regla V150: whole-home sólo se declara iniciado tras una nueva confirmación status 5/6/7",
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

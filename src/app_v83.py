import math
import time
from collections import deque

import app_v82
import app_v9


class App(app_v82.App):
    """V83: giros con avance reales + cambios de carril rápidos + recovery prudente."""

    # V82 congelaba cualquier giro fuerte con pasos de hasta 0.40 m. En el E10
    # eso suprimía traslación real y llegó a separar el mapa >0.5 m de 10/24.
    # V83 sólo congela cuando prácticamente NO hay desplazamiento.
    PURE_TURN_ANGLE = 0.50
    PURE_TURN_MAX_STEP = 0.055
    MOVING_TURN_ANGLE = 0.38

    # Sólo un salto lateral grande durante un giro se considera sospechoso.
    # Si persiste, se acepta enseguida como cambio real de carril.
    TURN_SPIKE_MIN_STEP = 0.20
    TURN_SPIKE_MIN_LATERAL = 0.14
    TURN_SPIKE_LATERAL_RATIO = 1.35
    LANE_SHIFT_CONFIRM_SAMPLES = 3
    LANE_SHIFT_CONFIRM_TRAVEL = 0.10
    LANE_SHIFT_MIN_METERS = 0.12
    MAX_FILTER_ERROR_METERS = 0.22
    LANE_RETURN_EPSILON = 0.07

    # Antiatasco: más lento y más exigente. Ninguna recuperación puede
    # interrumpir exploración que todavía está descubriendo celdas nuevas.
    STALL_GRACE_AFTER_START_SECONDS = 60.0
    STALL_GRACE_AFTER_RECOVERY_SECONDS = 75.0
    STALL_WINDOW_SECONDS = 48.0
    STALL_MIN_SECONDS = 40.0
    STALL_POSITION_SPAN = 0.055
    STALL_MIN_ANGLE_TRAVEL = 10.5
    STALL_MIN_DIRECTION_REVERSALS = 5
    STALL_MIN_POSE_SAMPLES = 18
    STALL_COOLDOWN_SECONDS = 120.0

    CORRIDOR_MAX_WIDTH = 0.24
    CORRIDOR_MIN_SECONDS = 80.0
    CORRIDOR_MIN_SAMPLES = 40
    CORRIDOR_MIN_REVERSALS = 5

    RECOVERY_STATIONARY_NO_NEW_SECONDS = 45.0
    RECOVERY_CORRIDOR_NO_NEW_SECONDS = 70.0
    RECOVERY_GENERAL_NO_NEW_SECONDS = 45.0
    RECOVERY_HARD_COOLDOWN_SECONDS = 120.0

    def __init__(self):
        self._v83_lane_candidate = None
        self._v83_point_seq = 0
        self._v83_decision_counts = {
            "ACEPTADO": 0,
            "GIRO PURO": 0,
            "OFFSET TRANSITORIO": 0,
            "CAMBIO DE CARRIL": 0,
        }
        self._v83_recent_decisions = deque(maxlen=24)
        self._v83_recovery_gate_blocks = 0
        self._v83_recovery_gate_accepts = 0
        self._v83_last_recovery_gate = None
        self._v83_last_recovery_trigger = None
        self._v83_max_output_error = 0.0
        super().__init__()

    def _v74_reset_session(self):
        self._v83_lane_candidate = None
        self._v83_point_seq = 0
        self._v83_decision_counts = {
            "ACEPTADO": 0,
            "GIRO PURO": 0,
            "OFFSET TRANSITORIO": 0,
            "CAMBIO DE CARRIL": 0,
        }
        self._v83_recent_decisions = deque(maxlen=24)
        self._v83_recovery_gate_blocks = 0
        self._v83_recovery_gate_accepts = 0
        self._v83_last_recovery_gate = None
        self._v83_last_recovery_trigger = None
        self._v83_max_output_error = 0.0
        return super()._v74_reset_session()

    # ====================================================== decisiones por punto
    def _v83_record_decision(
        self,
        label,
        raw,
        output,
        step,
        dtheta,
        detail="",
    ):
        if label not in self._v83_decision_counts:
            label = "ACEPTADO"
        self._v83_decision_counts[label] += 1
        self._v83_point_seq += 1

        error = math.hypot(
            float(output[0]) - float(raw[0]),
            float(output[1]) - float(raw[1]),
        )
        self._v83_max_output_error = max(
            float(self._v83_max_output_error or 0.0),
            float(error),
        )
        self._v83_recent_decisions.append({
            "seq": int(self._v83_point_seq),
            "label": str(label),
            "step": float(step),
            "turn": float(dtheta),
            "error": float(error),
            "detail": str(detail or ""),
        })

    def _v83_start_lane_candidate(self, last, previous_angle, x, y):
        axis = self._v82_axis(previous_angle)
        origin = (float(last[0]), float(last[1]))
        _px, _py, along, cross = self._v82_project_to_axis(
            x,
            y,
            origin,
            axis,
        )
        sign = 1 if cross >= 0 else -1
        self._v83_lane_candidate = {
            "origin": origin,
            "axis": axis,
            "sign": sign,
            "points": [(float(cross), float(along))],
        }
        return float(cross), float(along)

    def _v83_update_lane_candidate(self, x, y):
        candidate = self._v83_lane_candidate
        if not candidate:
            return None

        _px, _py, along, cross = self._v82_project_to_axis(
            x,
            y,
            candidate["origin"],
            candidate["axis"],
        )

        if abs(cross) < self.LANE_RETURN_EPSILON:
            self._v83_lane_candidate = None
            return {
                "state": "returned",
                "cross": float(cross),
                "along": float(along),
            }

        sign = 1 if cross >= 0 else -1
        if sign != int(candidate["sign"]):
            self._v83_lane_candidate = None
            return {
                "state": "changed-sign",
                "cross": float(cross),
                "along": float(along),
            }

        candidate["points"].append((float(cross), float(along)))
        points = list(candidate["points"])[-self.LANE_SHIFT_CONFIRM_SAMPLES:]
        along_span = (
            max(item[1] for item in points) - min(item[1] for item in points)
            if len(points) >= 2
            else 0.0
        )
        enough_samples = len(points) >= self.LANE_SHIFT_CONFIRM_SAMPLES
        persistent = (
            enough_samples
            and all(
                (item[0] > 0) == (points[0][0] > 0)
                for item in points
            )
            and min(abs(item[0]) for item in points)
            >= self.LANE_SHIFT_MIN_METERS
        )
        strong_shift = abs(float(cross)) >= self.MAX_FILTER_ERROR_METERS

        if persistent and (
            along_span >= self.LANE_SHIFT_CONFIRM_TRAVEL
            or strong_shift
        ):
            self._v83_lane_candidate = None
            return {
                "state": "confirmed",
                "cross": float(cross),
                "along": float(along),
                "along_span": float(along_span),
            }

        if strong_shift:
            # No permitimos que el filtro se aleje más de 22 cm del 10/24
            # absoluto: ante la duda, el desplazamiento físico gana.
            self._v83_lane_candidate = None
            return {
                "state": "forced",
                "cross": float(cross),
                "along": float(along),
                "along_span": float(along_span),
            }

        return {
            "state": "pending",
            "cross": float(cross),
            "along": float(along),
            "along_span": float(along_span),
        }

    # ================================================= trayectoria V83
    def _v82_apply_lane_lock(self, x, y, angle):
        # V83 elimina el "rail" rígido de V82. La posición absoluta es la
        # referencia y sólo se retiene temporalmente un salto lateral dudoso.
        return float(x), float(y)

    def _v82_correct_absolute(self, absolute):
        x = float(absolute["x"])
        y = float(absolute["y"])
        angle = float(
            absolute.get("phi", absolute.get("angle", 0.0)) or 0.0
        )
        current = (x, y, angle)

        previous_raw = self._v82_previous_raw
        last = self._v82_last_corrected
        out_x, out_y = x, y
        label = "ACEPTADO"
        detail = ""
        step = 0.0
        dtheta = 0.0

        if last is not None and previous_raw is not None:
            px, py, pa = previous_raw
            dx = x - px
            dy = y - py
            step = math.hypot(dx, dy)
            dtheta = abs(self._v73_angle_delta(pa, angle))

            # Si ya había un offset dudoso, primero vemos si persistió.
            candidate_state = self._v83_update_lane_candidate(x, y)
            if candidate_state is not None:
                state = candidate_state["state"]
                if state in ("confirmed", "forced"):
                    out_x, out_y = x, y
                    label = "CAMBIO DE CARRIL"
                    detail = (
                        f"persistente cross={candidate_state['cross']:.2f}m "
                        f"along={candidate_state['along']:.2f}m"
                    )
                    self._v82_lane_changes_confirmed += 1
                elif state == "pending":
                    out_x, out_y = float(last[0]), float(last[1])
                    label = "OFFSET TRANSITORIO"
                    detail = (
                        f"candidato cross={candidate_state['cross']:.2f}m"
                    )
                    self._v82_lane_offsets_suppressed += 1
                else:
                    # Volvió al carril o cambió de lado: no persistió.
                    out_x, out_y = x, y
                    label = "ACEPTADO"
                    detail = "offset no persistente descartado"
            elif (
                dtheta >= self.PURE_TURN_ANGLE
                and step <= self.PURE_TURN_MAX_STEP
            ):
                # Giro realmente sobre el lugar: sólo cambia orientación.
                out_x, out_y = float(last[0]), float(last[1])
                label = "GIRO PURO"
                detail = "sin traslación física"
                self._v82_turn_points_frozen += 1
                self._v82_turn_hold = False
                self._v82_turn_pending = []
            else:
                # Giro con avance: se conserva la traslación. Sólo un salto
                # lateral grande/dominante abre una sospecha temporal.
                ax, ay = self._v82_axis(pa)
                forward = dx * ax + dy * ay
                lateral = dx * (-ay) + dy * ax
                suspicious = (
                    dtheta >= self.MOVING_TURN_ANGLE
                    and step >= self.TURN_SPIKE_MIN_STEP
                    and abs(lateral) >= self.TURN_SPIKE_MIN_LATERAL
                    and abs(lateral)
                    >= max(
                        self.TURN_SPIKE_MIN_LATERAL,
                        abs(forward) * self.TURN_SPIKE_LATERAL_RATIO,
                    )
                )

                if suspicious:
                    cross, along = self._v83_start_lane_candidate(
                        last,
                        pa,
                        x,
                        y,
                    )
                    if abs(cross) >= self.MAX_FILTER_ERROR_METERS:
                        # No sacrificamos fidelidad absoluta por filtrar un
                        # supuesto pico. Se acepta inmediatamente.
                        self._v83_lane_candidate = None
                        out_x, out_y = x, y
                        label = "CAMBIO DE CARRIL"
                        detail = (
                            f"salto lateral grande aceptado cross={cross:.2f}m"
                        )
                        self._v82_lane_changes_confirmed += 1
                    else:
                        out_x, out_y = float(last[0]), float(last[1])
                        label = "OFFSET TRANSITORIO"
                        detail = (
                            f"giro + lateral dudoso cross={cross:.2f}m "
                            f"along={along:.2f}m"
                        )
                        self._v82_lane_offsets_suppressed += 1
                else:
                    out_x, out_y = x, y
                    label = "ACEPTADO"
                    if dtheta >= self.MOVING_TURN_ANGLE and step > self.PURE_TURN_MAX_STEP:
                        detail = "giro con avance conservado"
                    self._v82_turn_hold = False
                    self._v82_turn_pending = []
                    self._v82_lane_origin = None
                    self._v82_lane_axis = None
                    self._v82_lane_pending.clear()

        self._v82_previous_raw = current
        self._v79_previous_absolute = current

        # Guardia final: V83 jamás permite que la corrección se aleje más de
        # MAX_FILTER_ERROR_METERS del 10/24 absoluto.
        error = math.hypot(float(out_x) - x, float(out_y) - y)
        if error > self.MAX_FILTER_ERROR_METERS:
            out_x, out_y = x, y
            label = "CAMBIO DE CARRIL"
            detail = (
                f"guardia absoluta: error {error:.2f}m > "
                f"{self.MAX_FILTER_ERROR_METERS:.2f}m"
            )
            self._v83_lane_candidate = None
            self._v82_lane_changes_confirmed += 1

        filtered = (float(out_x), float(out_y), angle)
        self._v82_last_corrected = filtered
        self._v79_last_filtered = filtered
        self._v77_filter_last_raw = current
        self._v77_filter_last_output = filtered

        final_error = math.hypot(float(out_x) - x, float(out_y) - y)
        self._v79_last_filter_error = float(final_error)
        self._v79_max_filter_error = max(
            float(self._v79_max_filter_error or 0.0),
            float(final_error),
        )

        self._v83_record_decision(
            label,
            current,
            filtered,
            step,
            dtheta,
            detail,
        )

        result = dict(absolute)
        result["x"] = float(out_x)
        result["y"] = float(out_y)
        result["phi"] = angle
        return result

    # ================================================= antiatasco V83
    @staticmethod
    def _v83_recovery_kind(reason):
        text = str(reason or "").lower()
        if (
            "corredor" in text
            or "pasadas ida/vuelta" in text
            or "sector repetido" in text
        ):
            return "corredor"
        if (
            "oscilación" in text
            or "sin avance" in text
            or "estacion" in text
            or "giro repetido" in text
        ):
            return "estacionario"
        return "general"

    def _v83_recovery_gate(self, reason, now=None):
        now = time.monotonic() if now is None else float(now)
        kind = self._v83_recovery_kind(reason)

        if self._v74_finish_requested:
            return False, {
                "kind": kind,
                "reason": "mapeo cerrándose",
                "no_new": 0.0,
                "cooldown": 0.0,
            }

        if bool(getattr(self, "_v73_recovery_active", False)):
            return False, {
                "kind": kind,
                "reason": "recovery ya activo",
                "no_new": 0.0,
                "cooldown": 0.0,
            }

        last_new = getattr(self, "_v74_last_discovery_at", None)
        no_new = (
            max(0.0, now - float(last_new))
            if last_new is not None
            else float("inf")
        )

        threshold = self.RECOVERY_GENERAL_NO_NEW_SECONDS
        if kind == "estacionario":
            threshold = self.RECOVERY_STATIONARY_NO_NEW_SECONDS
        elif kind == "corredor":
            threshold = self.RECOVERY_CORRIDOR_NO_NEW_SECONDS

        if no_new < threshold:
            return False, {
                "kind": kind,
                "reason": (
                    f"todavía descubre área: {no_new:.1f}s "
                    f"< {threshold:.1f}s"
                ),
                "no_new": float(no_new),
                "cooldown": 0.0,
            }

        last_recovery = float(getattr(self, "_v73_last_recovery_at", 0.0) or 0.0)
        cooldown = (
            max(0.0, self.RECOVERY_HARD_COOLDOWN_SECONDS - (now - last_recovery))
            if last_recovery > 0.0
            else 0.0
        )
        if cooldown > 0.0:
            return False, {
                "kind": kind,
                "reason": f"cooldown post-recovery {cooldown:.1f}s",
                "no_new": float(no_new),
                "cooldown": float(cooldown),
            }

        if kind == "corredor":
            geometry = getattr(self, "_v77_corridor_last_geometry", None) or {}
            width = geometry.get("cross_span")
            if width is not None and float(width) > self.CORRIDOR_MAX_WIDTH:
                return False, {
                    "kind": kind,
                    "reason": (
                        f"corredor demasiado ancho {float(width):.2f}m "
                        f"> {self.CORRIDOR_MAX_WIDTH:.2f}m"
                    ),
                    "no_new": float(no_new),
                    "cooldown": 0.0,
                }

        return True, {
            "kind": kind,
            "reason": "condiciones confirmadas",
            "no_new": float(no_new),
            "cooldown": 0.0,
        }

    def _v73_schedule_recovery(self, phase, reason):
        allowed, meta = self._v83_recovery_gate(reason)
        self._v83_last_recovery_gate = dict(meta)

        if not allowed:
            self._v83_recovery_gate_blocks += 1
            return None

        self._v83_recovery_gate_accepts += 1
        self._v83_last_recovery_trigger = (
            f"{meta['kind']} · {reason} · "
            f"sin zona nueva={meta['no_new']:.1f}s"
        )
        return super()._v73_schedule_recovery(phase, reason)

    # ========================================================= texto/diag
    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · giro+avance real · carriles persistentes · "
                        "antiatasco prudente · retorno seguro"
                    )
                )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        gate = dict(self._v83_last_recovery_gate or {})
        last_new = getattr(self, "_v74_last_discovery_at", None)
        now = time.monotonic()
        no_new = (
            max(0.0, now - float(last_new))
            if last_new is not None
            else None
        )

        recent = []
        for item in list(self._v83_recent_decisions)[-12:]:
            detail = f" · {item['detail']}" if item.get("detail") else ""
            recent.append(
                f"#{item['seq']} {item['label']} "
                f"(paso={item['step']:.2f}m, giro={item['turn']:.2f}, "
                f"error={item['error']:.2f}m){detail}"
            )

        lines = [
            "DIAGNÓSTICO V83 ACTIVO · giro+avance + carril real + recovery prudente",
            "========================================================================",
            (
                "decisiones: "
                f"ACEPTADO={self._v83_decision_counts['ACEPTADO']} · "
                f"GIRO PURO={self._v83_decision_counts['GIRO PURO']} · "
                f"OFFSET TRANSITORIO={self._v83_decision_counts['OFFSET TRANSITORIO']} · "
                f"CAMBIO DE CARRIL={self._v83_decision_counts['CAMBIO DE CARRIL']}"
            ),
            (
                "error corrección actual/máximo: "
                f"{float(getattr(self, '_v79_last_filter_error', 0.0) or 0.0):.3f}/"
                f"{float(self._v83_max_output_error or 0.0):.3f} m · "
                f"límite={self.MAX_FILTER_ERROR_METERS:.2f} m"
            ),
            (
                "antiatasco V83: aceptados="
                f"{self._v83_recovery_gate_accepts} · bloqueados="
                f"{self._v83_recovery_gate_blocks} · sin zona nueva="
                + (f"{no_new:.1f}s" if no_new is not None else "—")
            ),
            (
                "último gate recovery: "
                f"{gate.get('kind', '—')} · {gate.get('reason', '—')}"
            ),
            (
                "último recovery autorizado: "
                f"{self._v83_last_recovery_trigger or '—'}"
            ),
            (
                "umbrales recovery: estacionario sin zona nueva≥"
                f"{self.RECOVERY_STATIONARY_NO_NEW_SECONDS:.0f}s · corredor≥"
                f"{self.RECOVERY_CORRIDOR_NO_NEW_SECONDS:.0f}s · cooldown="
                f"{self.RECOVERY_HARD_COOLDOWN_SECONDS:.0f}s · "
                f"ancho corredor≤{self.CORRIDOR_MAX_WIDTH:.2f}m"
            ),
            "decisiones recientes:",
        ]
        lines.extend(
            f"    {item}" for item in recent
        )
        if not recent:
            lines.append("    —")
        lines.extend([
            "regla V83: sólo un giro con desplazamiento casi nulo congela X/Y; giro con avance conserva traslación",
            "regla V83: un offset lateral se retiene sólo de forma temporal; si persiste o supera 0.22 m se acepta como cambio de carril",
            "regla V83: el mapa corregido nunca puede separarse más de 0.22 m de 10/24 absoluto",
            "regla V83: no hay recovery mientras se sigan descubriendo celdas nuevas",
            "regla V83: después de un recovery hay cooldown duro antes de permitir otro pitido/reinicio",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v9._save_crash_log(traceback.format_exc())
        raise

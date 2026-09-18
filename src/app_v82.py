import math
import statistics
import threading
import time
from collections import deque

import app_v81
import app_v70
import app_v9


class App(app_v81.App):
    """V82: trayectoria corregida, exploración 2D real y cierre al cargar."""

    # Durante un giro fuerte, un salto X/Y de 10/24 no se acepta como
    # traslación física. Se mantiene la posición y sólo cambia la orientación.
    TURN_FREEZE_ANGLE = 0.38
    TURN_FREEZE_MAX_STEP = 0.40
    TURN_RELEASE_SAMPLES = 3
    TURN_RELEASE_MIN_TRAVEL = 0.14

    # Tras una inversión de marcha se bloquea el carril previo. Un cambio
    # lateral sólo se acepta si persiste durante varias muestras y además hay
    # avance longitudinal suficiente.
    LANE_HEADING_TOLERANCE = 0.48
    LANE_SHIFT_MIN_METERS = 0.18
    LANE_SHIFT_CONFIRM_SAMPLES = 5
    LANE_SHIFT_CONFIRM_TRAVEL = 0.35

    # La cobertura debe ser realmente bidimensional. El detector de corredor
    # trabaja sobre la trayectoria CORREGIDA, no sobre 10/24 crudo.
    CORRIDOR_MAX_WIDTH = 0.45
    CORRIDOR_MIN_SECONDS = 55.0
    CORRIDOR_MIN_SAMPLES = 30
    CORRIDOR_MIN_LENGTH = 0.75
    CORRIDOR_MIN_REVERSALS = 4

    MIN_2D_RATIO = 0.40
    MIN_2D_CROSS_SPAN = 0.70
    CORRECTED_SAMPLE_EPSILON = 0.02

    def __init__(self):
        self._v82_previous_raw = None
        self._v82_last_corrected = None
        self._v82_last_persisted_xy = None
        self._v82_turn_hold = False
        self._v82_turn_origin = None
        self._v82_turn_axis = None
        self._v82_turn_pending = []
        self._v82_lane_origin = None
        self._v82_lane_axis = None
        self._v82_lane_pending = deque(maxlen=10)

        self._v82_turn_points_frozen = 0
        self._v82_lane_offsets_suppressed = 0
        self._v82_lane_changes_confirmed = 0
        self._v82_corrected_samples = deque(maxlen=2400)
        self._v82_corrected_cells = set()
        self._v82_status4_session_closes = 0
        self._v82_shared_thumb_bounds = None
        super().__init__()

    def _v74_reset_session(self):
        self._v82_previous_raw = None
        self._v82_last_corrected = None
        self._v82_last_persisted_xy = None
        self._v82_turn_hold = False
        self._v82_turn_origin = None
        self._v82_turn_axis = None
        self._v82_turn_pending = []
        self._v82_lane_origin = None
        self._v82_lane_axis = None
        self._v82_lane_pending = deque(maxlen=10)
        self._v82_turn_points_frozen = 0
        self._v82_lane_offsets_suppressed = 0
        self._v82_lane_changes_confirmed = 0
        self._v82_corrected_samples = deque(maxlen=2400)
        self._v82_corrected_cells = set()
        self._v82_status4_session_closes = 0
        self._v82_shared_thumb_bounds = None
        return super()._v74_reset_session()

    # ================================================= trayectoria corregida
    @staticmethod
    def _v82_axis(angle):
        return math.cos(float(angle)), math.sin(float(angle))

    @staticmethod
    def _v82_unoriented_angle_error(a, b):
        delta = abs((float(a) - float(b) + math.pi) % (2.0 * math.pi) - math.pi)
        return min(delta, abs(math.pi - delta))

    @staticmethod
    def _v82_project_to_axis(x, y, origin, axis):
        ox, oy = origin
        ax, ay = axis
        along = (float(x) - ox) * ax + (float(y) - oy) * ay
        cross = (float(x) - ox) * (-ay) + (float(y) - oy) * ax
        return (
            ox + along * ax,
            oy + along * ay,
            float(along),
            float(cross),
        )

    def _v82_apply_lane_lock(self, x, y, angle):
        if self._v82_lane_origin is None or self._v82_lane_axis is None:
            return float(x), float(y)

        axis_angle = math.atan2(
            self._v82_lane_axis[1],
            self._v82_lane_axis[0],
        )
        alignment = self._v82_unoriented_angle_error(angle, axis_angle)
        if alignment > self.LANE_HEADING_TOLERANCE:
            self._v82_lane_origin = None
            self._v82_lane_axis = None
            self._v82_lane_pending.clear()
            return float(x), float(y)

        px, py, along, cross = self._v82_project_to_axis(
            x,
            y,
            self._v82_lane_origin,
            self._v82_lane_axis,
        )

        if abs(cross) < self.LANE_SHIFT_MIN_METERS:
            self._v82_lane_pending.clear()
            if abs(cross) >= 0.03:
                self._v82_lane_offsets_suppressed += 1
            return px, py

        self._v82_lane_pending.append((float(cross), float(along)))
        pending = list(self._v82_lane_pending)
        same_sign = (
            len(pending) >= self.LANE_SHIFT_CONFIRM_SAMPLES
            and (
                all(item[0] > 0 for item in pending[-self.LANE_SHIFT_CONFIRM_SAMPLES:])
                or all(item[0] < 0 for item in pending[-self.LANE_SHIFT_CONFIRM_SAMPLES:])
            )
        )
        along_values = [item[1] for item in pending[-self.LANE_SHIFT_CONFIRM_SAMPLES:]]
        along_span = (
            max(along_values) - min(along_values)
            if len(along_values) >= self.LANE_SHIFT_CONFIRM_SAMPLES
            else 0.0
        )

        if same_sign and along_span >= self.LANE_SHIFT_CONFIRM_TRAVEL:
            crosses = [
                item[0]
                for item in pending[-self.LANE_SHIFT_CONFIRM_SAMPLES:]
            ]
            shift = float(statistics.median(crosses))
            ox, oy = self._v82_lane_origin
            ax, ay = self._v82_lane_axis
            self._v82_lane_origin = (
                ox + shift * (-ay),
                oy + shift * ax,
            )
            self._v82_lane_pending.clear()
            self._v82_lane_changes_confirmed += 1
            px, py, _along, _cross = self._v82_project_to_axis(
                x,
                y,
                self._v82_lane_origin,
                self._v82_lane_axis,
            )
            return px, py

        self._v82_lane_offsets_suppressed += 1
        return px, py

    def _v82_correct_absolute(self, absolute):
        x = float(absolute["x"])
        y = float(absolute["y"])
        angle = float(absolute.get("phi", absolute.get("angle", 0.0)) or 0.0)
        current = (x, y, angle)

        previous_raw = self._v82_previous_raw
        last = self._v82_last_corrected

        if last is None:
            out_x, out_y = x, y
        elif previous_raw is None:
            out_x, out_y = x, y
        else:
            px, py, pa = previous_raw
            step = math.hypot(x - px, y - py)
            dtheta = abs(self._v73_angle_delta(pa, angle))
            strong_turn = (
                dtheta >= self.TURN_FREEZE_ANGLE
                and step <= self.TURN_FREEZE_MAX_STEP
            )

            if strong_turn:
                if not self._v82_turn_hold:
                    self._v82_turn_hold = True
                    self._v82_turn_origin = (
                        float(last[0]),
                        float(last[1]),
                    )
                    self._v82_turn_axis = self._v82_axis(pa)
                    self._v82_turn_pending = []
                self._v82_turn_points_frozen += 1
                self._v82_turn_pending = []
                out_x, out_y = float(last[0]), float(last[1])
            elif self._v82_turn_hold:
                self._v82_turn_pending.append(current)
                pending = self._v82_turn_pending[-self.TURN_RELEASE_SAMPLES:]
                travel = 0.0
                if len(pending) >= self.TURN_RELEASE_SAMPLES:
                    travel = math.hypot(
                        pending[-1][0] - pending[0][0],
                        pending[-1][1] - pending[0][1],
                    )

                if (
                    len(pending) >= self.TURN_RELEASE_SAMPLES
                    and travel >= self.TURN_RELEASE_MIN_TRAVEL
                ):
                    self._v82_turn_hold = False
                    self._v82_lane_origin = self._v82_turn_origin
                    self._v82_lane_axis = self._v82_turn_axis
                    self._v82_lane_pending.clear()
                    self._v82_turn_pending = []
                    out_x, out_y = self._v82_apply_lane_lock(
                        x,
                        y,
                        angle,
                    )
                else:
                    out_x, out_y = float(last[0]), float(last[1])
            elif self._v82_lane_axis is not None:
                out_x, out_y = self._v82_apply_lane_lock(x, y, angle)
            else:
                out_x, out_y = x, y

        self._v82_previous_raw = current
        self._v79_previous_absolute = current
        filtered = (float(out_x), float(out_y), angle)
        self._v82_last_corrected = filtered
        self._v79_last_filtered = filtered
        self._v77_filter_last_raw = current
        self._v77_filter_last_output = filtered

        error = math.hypot(float(out_x) - x, float(out_y) - y)
        self._v79_last_filter_error = float(error)
        self._v79_max_filter_error = max(
            float(self._v79_max_filter_error or 0.0),
            float(error),
        )

        result = dict(absolute)
        result["x"] = float(out_x)
        result["y"] = float(out_y)
        result["phi"] = angle
        return result

    def _v77_filter_metric_point(self, point):
        absolute = self._v79_absolute_metric_point(point)
        if absolute is None:
            return None

        x = float(absolute["x"])
        y = float(absolute["y"])
        angle = float(absolute.get("phi", 0.0) or 0.0)
        current = (x, y, angle)
        self._v79_last_absolute = current

        if not self._v79_initial_gate_open:
            distance = math.hypot(x, y)
            if distance > self.INITIAL_GATE_RADIUS_METERS:
                self._v79_initial_rejected += 1
                self._v77_filter_last_raw = current
                self._v82_previous_raw = current
                return None
            self._v79_initial_gate_open = True

        return self._v82_correct_absolute(absolute)

    def _v82_persistable_point(self, point):
        try:
            xy = (float(point["x"]), float(point["y"]))
        except Exception:
            return None
        previous = self._v82_last_persisted_xy
        if previous is not None:
            if math.hypot(xy[0] - previous[0], xy[1] - previous[1]) < self.CORRECTED_SAMPLE_EPSILON:
                return None
        self._v82_last_persisted_xy = xy
        return dict(point)

    def _v82_note_corrected_sample(self, point):
        try:
            x = float(point["x"])
            y = float(point["y"])
            angle = float(point.get("phi", point.get("angle", 0.0)) or 0.0)
        except Exception:
            return
        self._v82_corrected_samples.append(
            (time.monotonic(), x, y, angle)
        )
        cell = (
            int(round(x / self.MAP_CELL_SIZE)),
            int(round(y / self.MAP_CELL_SIZE)),
        )
        self._v82_corrected_cells.add(cell)

    # ======================================== aplica sólo trayectoria corregida
    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return super()._apply_map_state(state)

        active = bool(getattr(self, "mapping_active", False))
        phase = int(getattr(self, "_v73_session_phase", 0) or 0)
        original_path = [
            dict(point)
            for point in list(state.get("path") or [])
            if isinstance(point, dict)
        ]

        if active and not self._v77_ensure_origin_from_state(state):
            waiting = dict(state)
            waiting["path"] = []
            waiting["robot"] = {"x": 0.0, "y": 0.0, "angle": 0.0}
            waiting["charging_base"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }
            return (
                app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75
                .app_v74.app_v73.app_v72.app_v71.app_v70.App
                ._apply_map_state(self, waiting)
            )

        transformed = dict(state)
        origin = self._v71_session_origin_raw
        if origin is not None:
            new_local = []
            latest_filtered = None

            for point in original_path:
                key = self._v73_point_key(point)
                if key is None or key in self._v73_seen_track_keys:
                    continue
                self._v73_seen_track_keys.add(key)

                filtered = self._v77_filter_metric_point(point)
                if filtered is None:
                    continue
                latest_filtered = filtered

                accepted = self._v80_buffer_initial_point(filtered)
                for item in accepted:
                    clean = self._v82_persistable_point(item)
                    if clean is None:
                        continue
                    self._v82_note_corrected_sample(clean)
                    if active and phase in (1, 2) and not (
                        phase == 2
                        and bool(getattr(self, "mapping_transitioning", False))
                    ):
                        new_local.append(clean)
                    else:
                        self._v73_transit_points += 1

            if active and phase in (1, 2) and new_local:
                self._v77_merge_base_point(phase)
                self._v73_phase_new[phase] += len(new_local)
                self._v71_path_points_seen[phase] = self._v73_phase_new[phase]
                try:
                    added = int(
                        self.local_map.merge_trajectory(
                            new_local,
                            phase=phase,
                        ) or 0
                    )
                except Exception:
                    added = 0
                self._v73_phase_saved[phase] += max(0, added)
                self._v71_path_points_merged[phase] = self._v73_phase_saved[phase]

            parsed_robot = self._v73_parse_pose(state.get("robot"))
            display_robot = None
            if latest_filtered is not None:
                display_robot = {
                    "x": float(latest_filtered["x"]),
                    "y": float(latest_filtered["y"]),
                    "angle": float(latest_filtered.get("phi", 0.0) or 0.0),
                }
            elif self._v82_last_corrected is not None:
                display_robot = {
                    "x": float(self._v82_last_corrected[0]),
                    "y": float(self._v82_last_corrected[1]),
                    "angle": (
                        float(parsed_robot[2])
                        if parsed_robot is not None
                        else float(self._v82_last_corrected[2])
                    ),
                }

            if display_robot is not None:
                transformed["robot"] = display_robot

            if (
                active
                and display_robot is not None
                and self._v80_initial_validated
            ):
                departure = math.hypot(
                    display_robot["x"],
                    display_robot["y"],
                )
                self._v71_session_max_departure = max(
                    float(self._v71_session_max_departure or 0.0),
                    float(departure),
                )
                self._v73_track_motion(display_robot, phase, active)
                self._v77_note_coverage_metric(display_robot)

            transformed["charging_base"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }
            transformed["path"] = []
            transformed["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V82 giro-congelado/carril-persistente"
            )
        elif not active:
            transformed["robot"] = None
            transformed["charging_base"] = None

        return (
            app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75
            .app_v74.app_v73.app_v72.app_v71.app_v70.App
            ._apply_map_state(self, transformed)
        )

    # ====================================== cobertura y completitud 2D reales
    def _v82_exploration_geometry(self):
        samples = list(self._v82_corrected_samples)
        if len(samples) < 3:
            return None
        try:
            return self._v77_corridor_geometry(
                samples,
                self.CORRIDOR_STEP_EPSILON,
            )
        except Exception:
            return None

    def _v81_completion_state(self):
        state = super()._v81_completion_state()
        geometry = self._v82_exploration_geometry() or {}
        along = float(geometry.get("along_span") or 0.0)
        cross = float(geometry.get("cross_span") or 0.0)
        ratio = cross / max(along, 1e-9) if along > 0 else 0.0

        missing = list(state.get("missing") or [])
        if cross < self.MIN_2D_CROSS_SPAN:
            missing.append(
                f"expansión lateral real {cross:.2f}/{self.MIN_2D_CROSS_SPAN:.2f}m"
            )
        if ratio < self.MIN_2D_RATIO:
            missing.append(
                f"exploración 2D {ratio:.2f}/{self.MIN_2D_RATIO:.2f}"
            )

        # V82 usa las celdas creadas por la trayectoria corregida.
        cells = len(self._v82_corrected_cells)
        if cells < self.MIN_COVERAGE_CELLS:
            label = f"cobertura corregida {cells}/{self.MIN_COVERAGE_CELLS} celdas"
            if not any("cobertura corregida" in item for item in missing):
                missing.append(label)

        ready = not missing
        state["cells"] = cells
        state["missing"] = missing
        state["ready"] = ready
        state["along_span"] = along
        state["cross_span"] = cross
        state["dimensionality_ratio"] = ratio
        self._v81_completion_ready = ready
        self._v81_completion_missing = list(missing)
        return state

    def _v77_note_coverage_metric(self, robot):
        # La implementación heredada mantiene temporización/no-new-area,
        # pero recibe exclusivamente la posición corregida V82.
        return super()._v77_note_coverage_metric(robot)

    # ======================================= miniatura = mismo marco del mapa
    @staticmethod
    def _v70_collect_bounds(snapshot, plan):
        bounds = app_v70.App._v70_collect_bounds(snapshot, plan)
        if bounds is None:
            return None

        base = (snapshot or {}).get("charging_base")
        try:
            cx = float(base.get("x", 0.0)) if isinstance(base, dict) else 0.0
            cy = float(base.get("y", 0.0)) if isinstance(base, dict) else 0.0
        except Exception:
            cx, cy = 0.0, 0.0

        left, bottom, right, top = bounds
        half_x = max(abs(left - cx), abs(right - cx), 0.5)
        half_y = max(abs(bottom - cy), abs(top - cy), 0.5)
        return (
            cx - half_x,
            cy - half_y,
            cx + half_x,
            cy + half_y,
        )

    # ===================================== status=4 cierra sesión siempre
    def _v74_watch_mapping_worker(self, vacuum, serial):
        return_samples = 0
        idle_samples = 0
        seen_moving = False
        status4_samples = 0

        while serial == self._v74_mapping_serial and self._v74_watch_active:
            if vacuum is not self.vacuum:
                return
            if not bool(getattr(self, "mapping_active", False)):
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("fault", 2, 2),
                ])
                status = self._v67_int(values.get("status"))
                fault = self._v67_int(values.get("fault"))
            except Exception:
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            self._v74_last_status = status
            mapped_points = int(self._v73_phase_saved.get(2, 0) or 0)
            if status in (5, 6, 7) or mapped_points >= 3:
                seen_moving = True

            if fault in (None, 0) and status == 4 and mapped_points >= 3:
                status4_samples += 1
            else:
                status4_samples = 0
            self._v77_status4_confirmations = status4_samples

            if status4_samples >= self.RETURN_CONFIRM_SAMPLES:
                state = self._v81_completion_state()
                self._v74_finish_requested = True
                self._v82_status4_session_closes += 1
                if state["ready"]:
                    self._post_ui(
                        "v74_mapping_complete",
                        serial,
                        "Mapeo terminado · carga confirmada en la base.",
                    )
                else:
                    reason = (
                        "Mapeo incompleto: el E10 ya está cargando, por lo que "
                        "la sesión se cerró sin inventar cobertura ("
                        + ", ".join(state["missing"])
                        + ")."
                    )
                    self._v81_incomplete_reason = reason
                    self._post_ui(
                        "v81_mapping_incomplete",
                        serial,
                        reason,
                        False,
                    )
                return

            if self._v73_recovery_active:
                return_samples = 0
                idle_samples = 0
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            returning = seen_moving and fault in (None, 0) and status == 3
            return_samples = return_samples + 1 if returning else 0
            self._v74_return_samples = return_samples

            if seen_moving and fault in (None, 0) and status == 1:
                idle_samples += 1
            else:
                idle_samples = 0
            self._v75_idle_samples = idle_samples

            if return_samples >= self.RETURN_CONFIRM_SAMPLES:
                # status=3 sólo indica retorno; no cierra hasta carga real.
                return_samples = self.RETURN_CONFIRM_SAMPLES

            if idle_samples >= self.IDLE_FINISH_SAMPLES:
                state = self._v81_completion_state()
                if state["ready"]:
                    self._v81_finish_complete(
                        "Mapeo terminado · cobertura 2D suficiente; el E10 "
                        "quedó inactivo y fue enviado una sola vez a la base."
                    )
                else:
                    self._v81_stop_incomplete(
                        "Mapeo incompleto: el E10 quedó inactivo sin "
                        "exploración 2D suficiente ("
                        + ", ".join(state["missing"])
                        + ").",
                        send_dock=True,
                    )
                return

            time.sleep(self.STATUS_POLL_SECONDS)

    # ========================================================= texto/diag
    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · trayectoria corregida · cobertura 2D · "
                        "retorno seguro"
                    )
                )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        state = self._v81_completion_state()
        geometry = self._v82_exploration_geometry() or {}
        inherited = super()._diagnostic_text()
        bounds = None
        try:
            snapshot = self.local_map.snapshot()
            bounds = self._v70_collect_bounds(snapshot, {})
        except Exception:
            bounds = None
        self._v82_shared_thumb_bounds = bounds

        lines = [
            "DIAGNÓSTICO V82 ACTIVO · trayectoria corregida + exploración 2D",
            "==================================================================",
            (
                "giros congelados: "
                f"{self._v82_turn_points_frozen} · offsets de carril suprimidos="
                f"{self._v82_lane_offsets_suppressed} · cambios de carril "
                f"confirmados={self._v82_lane_changes_confirmed}"
            ),
            (
                "trayectoria corregida: "
                f"muestras={len(self._v82_corrected_samples)} · "
                f"celdas={len(self._v82_corrected_cells)}"
            ),
            (
                "geometría 2D: "
                f"largo={float(geometry.get('along_span') or 0.0):.2f} m · "
                f"ancho={float(geometry.get('cross_span') or 0.0):.2f} m · "
                f"ratio={float(state.get('dimensionality_ratio') or 0.0):.2f} · "
                f"reversiones={int(geometry.get('reversals') or 0)}"
            ),
            (
                "completitud V82: "
                f"{bool(state.get('ready'))} · faltante="
                + (
                    ", ".join(state.get("missing") or [])
                    if state.get("missing")
                    else "—"
                )
            ),
            (
                "status=4 cerró sesión: "
                f"{self._v82_status4_session_closes} veces"
            ),
            f"marco compartido miniatura/mapa: {bounds!r}",
            "regla V82: durante un giro fuerte X/Y quedan congelados; sólo cambia el ángulo",
            "regla V82: una inversión no crea un carril nuevo salvo desplazamiento lateral persistente",
            "regla V82: cobertura, corredor y completitud usan la trayectoria corregida, no 10/24 crudo",
            "regla V82: muchas celdas alineadas nunca equivalen a una habitación mapeada",
            "regla V82: status=4 confirmado cierra la sesión aunque la UI heredada todavía la creyera activa",
            "regla V82: miniatura y mapa grande comparten el mismo marco mundial alrededor de la base",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v9._save_crash_log(traceback.format_exc())
        raise

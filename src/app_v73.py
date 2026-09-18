import math
import threading
import time
from collections import deque

import app_v72


class App(app_v72.App):
    """V73: fases coherentes, trayectoria incremental y recuperación de atascos."""

    STALL_WINDOW_SECONDS = 14.0
    STALL_MIN_SECONDS = 11.0
    STALL_POSITION_SPAN = 1.5
    STALL_MIN_ANGLE_TRAVEL = 4.0
    STALL_COOLDOWN_SECONDS = 40.0
    MAX_STALL_RECOVERIES = 3

    REPEAT_WINDOW_SECONDS = 180.0
    REPEAT_MIN_SAMPLES = 100
    REPEAT_POSITION_SPAN = 12.0

    DOCK_NEAR_STALL_SAMPLES = 12
    DOCK_MAX_RETRIES = 2
    DOCK_RETRY_REVERSE_SECONDS = 0.85
    DOCK_GUARD_STABLE_SECONDS = 12.0
    DOCK_GUARD_SECONDS = 300.0

    def __init__(self):
        self._v73_session_phase = 0
        self._v73_seen_track_keys = set()
        self._v73_phase_new = {1: 0, 2: 0}
        self._v73_phase_saved = {1: 0, 2: 0}
        self._v73_transit_points = 0
        self._v73_pose_window = deque()
        self._v73_recovery_active = False
        self._v73_recovery_count = 0
        self._v73_last_recovery_at = 0.0
        self._v73_last_recovery_reason = None
        self._v73_repeat_triggered = False
        self._v73_dock_retries = 0
        self._v73_dock_failed = False
        self._v73_last_parsed_return_pose = None
        self._v73_dock_guard_serial = 0
        self._v73_dock_guard_active = False
        self._v73_dock_guard_reason = None
        super().__init__()

    # ====================================================== sesión / fases
    def _v73_reset_session(self):
        self._v73_session_phase = 1
        self._v73_seen_track_keys = set()
        self._v73_phase_new = {1: 0, 2: 0}
        self._v73_phase_saved = {1: 0, 2: 0}
        self._v73_transit_points = 0
        self._v73_pose_window.clear()
        self._v73_recovery_active = False
        self._v73_recovery_count = 0
        self._v73_last_recovery_at = 0.0
        self._v73_last_recovery_reason = None
        self._v73_repeat_triggered = False
        self._v73_dock_retries = 0
        self._v73_dock_failed = False
        self._v73_last_parsed_return_pose = None
        self._v73_dock_guard_serial += 1
        self._v73_dock_guard_active = False
        self._v73_dock_guard_reason = None

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if bool(getattr(self, "mapping_active", False)) and int(
            getattr(self, "mapping_phase", 0) or 0
        ) == 1:
            self._v73_reset_session()
            vacuum = getattr(self, "vacuum", None)
            if vacuum is not None:
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
        return result

    def start_interior_mapping(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is not None:
            try:
                vacuum.reset_live_path_session()
            except Exception:
                pass
        self._v73_seen_track_keys = set()
        self._v73_pose_window.clear()
        result = super().start_interior_mapping()
        if bool(getattr(self, "mapping_active", False)) and int(
            getattr(self, "mapping_phase", 0) or 0
        ) == 2:
            self._v73_session_phase = 2
            self._v73_pose_window.clear()
            self._v73_repeat_triggered = False
        return result

    def _v67_commit_step2_start(self, serial, status, charging, battery, reason):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is not None:
            try:
                vacuum.reset_live_path_session()
            except Exception:
                pass
        self._v73_seen_track_keys = set()
        self._v73_pose_window.clear()
        started = super()._v67_commit_step2_start(
            serial, status, charging, battery, reason
        )
        if started:
            self._v73_session_phase = 2
            self._v73_pose_window.clear()
            self._v73_repeat_triggered = False
        return started

    def _handle_ui_event(self, kind, payload):
        if kind in ("edge_only_complete", "perimeter_complete"):
            # Desde este instante los puntos nuevos pertenecen al tránsito de
            # regreso a base y no pueden reaparecer luego como Paso 2.
            self._v73_session_phase = 0
            self._v73_pose_window.clear()

        if kind in (
            "edge_only_error",
            "mapping_error",
            "auto_step2_error",
            "unstick_abort",
            "v71_phase2_complete",
        ):
            self._v73_session_phase = 0

        if kind == "v71_phase2_complete":
            result = super()._handle_ui_event(kind, payload)
            self._v73_start_dock_guard("fin de Paso 2")
            return result

        if kind == "v73_stall_recovered":
            attempt, phase, reason = payload
            self._v73_recovery_active = False
            self._v73_pose_window.clear()
            if (
                int(phase) == 2
                and bool(getattr(self, "mapping_active", False))
                and int(getattr(self, "mapping_phase", 0) or 0) == 2
            ):
                self._v71_start_phase2_watch()
            self._set_banner(
                f"Recuperación automática {attempt}/{self.MAX_STALL_RECOVERIES}: "
                f"el E10 salió del atasco y retomó el Paso {phase}."
            )
            return

        if kind == "v73_stall_recovery_error":
            attempt, phase, message = payload
            self._v73_recovery_active = False
            self._v73_pose_window.clear()
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(
                f"No pude completar la recuperación automática del Paso {phase}; "
                f"detuve el mapeo y envié el E10 a la base. {message}"
            )
            self._v73_start_dock_guard("fallo de recuperación")
            return

        if kind == "v73_stall_abort":
            reason = str(payload[0])
            self._v73_recovery_active = False
            self._v73_session_phase = 0
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(
                "Mapeo detenido por seguridad: el E10 repitió el atasco varias veces. "
                + reason
            )
            self._v73_start_dock_guard("abortado por atasco repetido")
            return

        if kind == "v73_dock_retry":
            attempt = int(payload[0])
            self._set_banner(
                f"Acople a base sin carga detectada · reintento {attempt}/{self.DOCK_MAX_RETRIES}."
            )
            return

        if kind == "v73_dock_failed":
            self._v73_dock_failed = True
            self._v73_session_phase = 0
            self._v67_watch_running = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._set_banner(
                "No se confirmó carga tras varios intentos de acople. "
                "Detuve las ruedas para evitar agotar la batería."
            )
            return

        if kind == "v73_dock_guard_retry":
            serial, attempt, reason = payload
            if int(serial) != self._v73_dock_guard_serial:
                return
            self._v73_dock_retries = max(self._v73_dock_retries, int(attempt))
            self._set_banner(
                f"Acople sin carga detectado ({reason}) · "
                f"reintento {attempt}/{self.DOCK_MAX_RETRIES}."
            )
            return

        if kind == "v73_dock_guard_done":
            serial = int(payload[0])
            if serial != self._v73_dock_guard_serial:
                return
            self._v73_dock_guard_active = False
            return

        if kind == "v73_dock_guard_failed":
            serial, reason = payload
            if int(serial) != self._v73_dock_guard_serial:
                return
            self._v73_dock_guard_active = False
            self._v73_dock_failed = True
            self._set_banner(
                "El E10 no consiguió hacer contacto de carga. "
                "Detuve las ruedas para evitar que agote la batería. "
                f"Detalle: {reason}"
            )
            return

        return super()._handle_ui_event(kind, payload)

    # ================================================= coordenadas / parser
    @staticmethod
    def _v73_point_key(point):
        if not isinstance(point, dict):
            return None
        try:
            pid = int(point.get("id"))
            x = round(float(point.get("x")), 6)
            y = round(float(point.get("y")), 6)
        except Exception:
            return None
        return pid, x, y

    def _v73_parse_pose(self, value):
        xy = self._v71_xy(value)
        if xy is not None:
            angle = 0.0
            if isinstance(value, dict):
                try:
                    angle = float(
                        value.get("angle", value.get("phi", value.get("yaw", 0.0)))
                        or 0.0
                    )
                except Exception:
                    angle = 0.0
            return float(xy[0]), float(xy[1]), angle

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None or value is None:
            return None
        try:
            parsed = vacuum.parse_position(value)
        except Exception:
            parsed = None
        xy = self._v71_xy(parsed)
        if xy is None:
            return None
        try:
            angle = float(parsed.get("angle", 0.0) or 0.0)
        except Exception:
            angle = 0.0
        return float(xy[0]), float(xy[1]), angle

    def _v71_raw_distance_to_origin(self, raw_robot):
        origin = self._v71_session_origin_raw
        parsed = self._v73_parse_pose(raw_robot)
        if origin is None or parsed is None:
            return None
        self._v73_last_parsed_return_pose = parsed
        return math.hypot(parsed[0] - origin[0], parsed[1] - origin[1])

    # ================================================ trayectoria incremental
    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return app_v72.app_v71.app_v70.App._apply_map_state(self, state)

        active = bool(getattr(self, "mapping_active", False))
        phase = int(self._v73_session_phase or 0)
        original_path = [
            dict(point)
            for point in list(state.get("path") or [])
            if isinstance(point, dict)
        ]
        raw_robot = state.get("robot")

        if self._v71_session_origin_raw is None and active and phase == 1:
            first = self._v71_xy(original_path[0]) if original_path else None
            if first is None:
                pose = self._v73_parse_pose(raw_robot)
                first = (pose[0], pose[1]) if pose is not None else None
            if first is not None:
                self._v71_set_origin(first, "primera pose 10/24 de Paso 1 · V73")

        transformed = dict(state)
        origin = self._v71_session_origin_raw

        if origin is not None:
            parsed_robot = self._v73_parse_pose(raw_robot)
            local_robot = None
            if parsed_robot is not None:
                distance = math.hypot(
                    parsed_robot[0] - origin[0],
                    parsed_robot[1] - origin[1],
                )
                self._v71_session_max_departure = max(
                    float(self._v71_session_max_departure or 0.0),
                    float(distance),
                )
                local_robot = {
                    "x": parsed_robot[0] - origin[0],
                    "y": parsed_robot[1] - origin[1],
                    "angle": parsed_robot[2],
                }
                transformed["robot"] = local_robot
                self._v73_track_motion(local_robot, phase, active)

            transformed["charging_base"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }

            new_local = []
            for point in original_path:
                key = self._v73_point_key(point)
                if key is None or key in self._v73_seen_track_keys:
                    continue
                self._v73_seen_track_keys.add(key)
                local = self._v71_normalize_point(point)
                if local is None:
                    continue
                if active and phase in (1, 2) and not (
                    phase == 2 and bool(getattr(self, "mapping_transitioning", False))
                ):
                    new_local.append(local)
                else:
                    self._v73_transit_points += 1

            if active and phase in (1, 2) and new_local:
                self._v73_phase_new[phase] += len(new_local)
                self._v71_path_points_seen[phase] = self._v73_phase_new[phase]
                try:
                    added = int(
                        self.local_map.merge_trajectory(new_local, phase=phase) or 0
                    )
                except Exception:
                    added = 0
                self._v73_phase_saved[phase] += max(0, added)
                self._v71_path_points_merged[phase] = self._v73_phase_saved[phase]

            # El historial acumulado del controlador queda consumido aquí. Las
            # capas antiguas reciben path vacío para que no puedan reasignar
            # puntos viejos cuando cambia la fase.
            transformed["path"] = []
            transformed["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V73 incremental por llegada/fase"
            )
        elif not active:
            transformed["robot"] = None
            transformed["charging_base"] = None

        # Saltamos únicamente la implementación V71 de _apply_map_state, que
        # mezclaba el path acumulado completo. El resto de la cadena histórica
        # (persistencia de robot/base, render, telemetría) sigue intacta.
        return app_v72.app_v71.app_v70.App._apply_map_state(self, transformed)

    # ============================================ atasco / repetición espacial
    @staticmethod
    def _v73_angle_delta(a, b):
        a = float(a or 0.0)
        b = float(b or 0.0)
        if max(abs(a), abs(b)) > 4.0 * math.pi:
            a = math.radians(a)
            b = math.radians(b)
        return (b - a + math.pi) % (2.0 * math.pi) - math.pi

    @staticmethod
    def _v73_span(samples):
        if not samples:
            return 0.0
        xs = [item[1] for item in samples]
        ys = [item[2] for item in samples]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    def _v73_track_motion(self, robot, phase, active):
        now = time.monotonic()
        # El atasco observado ocurrió en el recorrido interior. En Paso 1 no
        # interferimos con el watchdog EDGE para no convertir una maniobra de
        # escape en un falso "fin de perímetro".
        if not active or phase != 2:
            self._v73_pose_window.clear()
            return
        if bool(getattr(self, "mapping_transitioning", False)):
            self._v73_pose_window.clear()
            return

        try:
            sample = (
                now,
                float(robot["x"]),
                float(robot["y"]),
                float(robot.get("angle", 0.0) or 0.0),
            )
        except Exception:
            return

        self._v73_pose_window.append(sample)
        cutoff = now - max(self.REPEAT_WINDOW_SECONDS + 10.0, 210.0)
        while self._v73_pose_window and self._v73_pose_window[0][0] < cutoff:
            self._v73_pose_window.popleft()

        if self._v73_recovery_active:
            return
        if now - float(self._v73_last_recovery_at or 0.0) < self.STALL_COOLDOWN_SECONDS:
            return

        short = [
            item
            for item in self._v73_pose_window
            if item[0] >= now - self.STALL_WINDOW_SECONDS
        ]
        if len(short) >= 8 and short[-1][0] - short[0][0] >= self.STALL_MIN_SECONDS:
            span = self._v73_span(short)
            angle_travel = sum(
                abs(self._v73_angle_delta(a[3], b[3]))
                for a, b in zip(short, short[1:])
            )
            if span <= self.STALL_POSITION_SPAN and angle_travel >= self.STALL_MIN_ANGLE_TRAVEL:
                self._v73_schedule_recovery(
                    phase,
                    f"giro repetido sin avance (span={span:.2f}, giro={angle_travel:.1f} rad)",
                )
                return

        if phase == 2 and not self._v73_repeat_triggered:
            long_window = [
                item
                for item in self._v73_pose_window
                if item[0] >= now - self.REPEAT_WINDOW_SECONDS
            ]
            if (
                len(long_window) >= self.REPEAT_MIN_SAMPLES
                and long_window[-1][0] - long_window[0][0]
                >= self.REPEAT_WINDOW_SECONDS - 10.0
            ):
                span = self._v73_span(long_window)
                if span <= self.REPEAT_POSITION_SPAN:
                    self._v73_repeat_triggered = True
                    self._v73_schedule_recovery(
                        phase,
                        f"sector repetido durante ~{int(self.REPEAT_WINDOW_SECONDS)} s (span={span:.2f})",
                    )

    def _v73_schedule_recovery(self, phase, reason):
        if int(phase or 0) != 2:
            return
        if self._v73_recovery_active or not self.vacuum:
            return
        self._v73_recovery_active = True
        self._v73_last_recovery_at = time.monotonic()
        self._v73_last_recovery_reason = str(reason)
        self._v73_recovery_count += 1
        attempt = self._v73_recovery_count
        vacuum = self.vacuum

        # Durante la maniobra habrá STOP/manual. Pausamos el watchdog V71 para
        # que esos estados intencionales no se interpreten como fin de Paso 2.
        self._v71_phase2_watch_serial += 1
        self._v71_phase2_watch_active = False

        if attempt > self.MAX_STALL_RECOVERIES:
            def abort_worker():
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.25)
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v73_stall_abort",
                    f"Última detección: {reason}",
                )

            threading.Thread(target=abort_worker, daemon=True).start()
            return

        def worker():
            try:
                # El control manual está documentado por la propia app:
                # 4=retroceder, 2=izquierda, 3=derecha, 5=detener manual.
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.35)

                vacuum.manual(4)
                time.sleep(0.80)
                vacuum.manual(5)
                time.sleep(0.20)

                turn = 2 if attempt % 2 else 3
                vacuum.manual(turn)
                time.sleep(0.65)
                vacuum.manual(5)
                time.sleep(0.25)

                vacuum.start_mapping_interior()

                self._post_ui(
                    "v73_stall_recovered",
                    attempt,
                    int(phase),
                    str(reason),
                )
            except Exception as exc:
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.20)
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v73_stall_recovery_error",
                    attempt,
                    int(phase),
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ========================================= protección general de acople
    def dock(self):
        """Orden manual de regreso + vigilancia de contacto de carga."""
        result = super().dock()
        self._v73_start_dock_guard("orden manual de volver a base")
        return result

    def _v73_start_dock_guard(self, reason):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return
        self._v73_dock_guard_serial += 1
        serial = self._v73_dock_guard_serial
        self._v73_dock_guard_active = True
        self._v73_dock_guard_reason = str(reason)
        threading.Thread(
            target=self._v73_dock_guard_worker,
            args=(vacuum, serial, str(reason)),
            daemon=True,
        ).start()

    def _v73_dock_guard_worker(self, vacuum, serial, reason):
        deadline = time.monotonic() + self.DOCK_GUARD_SECONDS
        direct_samples = 0
        retries = 0
        last_pose_key = None
        stable_since = None
        near_samples = 0

        while time.monotonic() < deadline:
            if serial != self._v73_dock_guard_serial:
                return
            if vacuum is not getattr(self, "vacuum", None):
                return
            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                raw_robot = state.get("robot")
            except Exception:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            now = time.monotonic()
            at_base, _ = self._v67_base_evidence(status, None)
            at_base = bool(at_base and fault == 0)
            direct_samples = direct_samples + 1 if at_base else 0
            if direct_samples >= self.BASE_CONFIRM_SAMPLES:
                self._post_ui("v73_dock_guard_done", serial)
                return

            pose_key = self._v69_pose_key(vacuum, raw_robot)
            if pose_key is not None and pose_key == last_pose_key:
                if stable_since is None:
                    stable_since = now
            else:
                last_pose_key = pose_key
                stable_since = now if pose_key is not None else None

            stable_seconds = (
                now - stable_since
                if stable_since is not None and pose_key is not None
                else 0.0
            )

            distance = self._v71_raw_distance_to_origin(raw_robot)
            threshold = self._v71_return_limit()
            departed_enough = (
                float(self._v71_session_max_departure or 0.0)
                >= self.RETURN_MIN_DEPARTURE
            )
            near_origin = (
                distance is not None
                and departed_enough
                and distance <= threshold
                and fault == 0
            )
            near_samples = near_samples + 1 if near_origin and not at_base else 0

            # Dos firmas del fallo observado: llegó a la zona de base sin
            # cargar, o status=3 permanece en la misma pose mientras las ruedas
            # siguen intentando subir/acoplar.
            stalled_on_dock = (
                status == 3
                and fault == 0
                and (
                    near_samples >= self.DOCK_NEAR_STALL_SAMPLES
                    or stable_seconds >= self.DOCK_GUARD_STABLE_SECONDS
                )
            )
            if not stalled_on_dock:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            if retries >= self.DOCK_MAX_RETRIES:
                try:
                    vacuum.stop()
                except Exception:
                    pass
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                self._post_ui(
                    "v73_dock_guard_failed",
                    serial,
                    f"{reason}; status={status}, sin carga y pose estable",
                )
                return

            retries += 1
            try:
                vacuum.stop()
            except Exception:
                pass
            time.sleep(0.30)
            try:
                vacuum.manual(4)
                time.sleep(self.DOCK_RETRY_REVERSE_SECONDS)
                vacuum.manual(5)
            except Exception:
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
            time.sleep(0.30)
            try:
                vacuum.dock()
            except Exception:
                pass

            self._post_ui(
                "v73_dock_guard_retry",
                serial,
                retries,
                reason,
            )
            direct_samples = 0
            near_samples = 0
            last_pose_key = None
            stable_since = None
            time.sleep(1.0)

        if serial == self._v73_dock_guard_serial:
            self._post_ui("v73_dock_guard_done", serial)

    # =============================================== regreso / acople a base
    def _v67_watch_base_worker(self, vacuum, serial):
        deadline = time.monotonic() + self.BASE_WATCH_SECONDS
        first_probe_at = time.monotonic()
        returning_since = None
        battery_start = None
        dock_sent = False
        direct_samples = 0
        near_no_charge_samples = 0
        last_tuple = None
        dock_retries = 0

        while time.monotonic() < deadline:
            if serial != self._v67_watch_serial or not self._auto_step2_pending:
                return
            if self.mapping_active or vacuum is not self.vacuum:
                return

            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                battery = self._v67_int(state.get("battery"))
                raw_robot = state.get("robot")
            except Exception as exc:
                self._post_ui(
                    "v67_transition_probe_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            now = time.monotonic()
            if status == 3 and returning_since is None:
                returning_since = now
                battery_start = battery

            saw_returning = returning_since is not None
            return_elapsed = (
                now - returning_since if returning_since is not None else 0.0
            )

            distance = self._v71_raw_distance_to_origin(raw_robot)
            if distance is not None:
                self._v71_session_max_departure = max(
                    float(self._v71_session_max_departure or 0.0),
                    float(distance),
                )
            threshold = self._v71_return_limit()
            self._v71_return_distance = distance
            self._v71_return_threshold = threshold

            departed_enough = (
                float(self._v71_session_max_departure or 0.0)
                >= self.RETURN_MIN_DEPARTURE
            )
            near_origin = (
                distance is not None
                and departed_enough
                and distance <= threshold
                and fault == 0
            )

            at_base, direct_reason = self._v67_base_evidence(status, None)
            at_base = bool(at_base and fault == 0)
            direct_samples = direct_samples + 1 if at_base else 0

            # Proximidad ya NO confirma base. Sirve sólo para detectar el caso
            # físico observado: llegó a la rampa, sigue empujando y no carga.
            if near_origin and not at_base and saw_returning:
                near_no_charge_samples += 1
            else:
                near_no_charge_samples = 0
            self._v71_return_near_samples = near_no_charge_samples

            if (
                near_no_charge_samples >= self.DOCK_NEAR_STALL_SAMPLES
                and dock_retries < self.DOCK_MAX_RETRIES
            ):
                dock_retries += 1
                self._v73_dock_retries = dock_retries
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.30)
                try:
                    vacuum.manual(4)
                    time.sleep(self.DOCK_RETRY_REVERSE_SECONDS)
                    vacuum.manual(5)
                except Exception:
                    try:
                        vacuum.manual(5)
                    except Exception:
                        pass
                time.sleep(0.30)
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui(
                        "v67_dock_error",
                        serial,
                        str(exc).strip() or type(exc).__name__,
                    )
                near_no_charge_samples = 0
                self._v71_return_near_samples = 0
                self._post_ui("v73_dock_retry", dock_retries)

            elif (
                near_no_charge_samples >= self.DOCK_NEAR_STALL_SAMPLES
                and dock_retries >= self.DOCK_MAX_RETRIES
            ):
                try:
                    vacuum.stop()
                except Exception:
                    pass
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                self._v73_dock_failed = True
                self._post_ui("v73_dock_failed")
                return

            if (
                saw_returning
                and not dock_sent
                and return_elapsed >= self.RETURN_DOCK_REASSERT_SECONDS
            ):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui(
                        "v67_dock_error",
                        serial,
                        str(exc).strip() or type(exc).__name__,
                    )

            if (
                not saw_returning
                and not dock_sent
                and now - first_probe_at >= 1.5
                and status not in (3, 4)
            ):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui(
                        "v67_dock_error",
                        serial,
                        str(exc).strip() or type(exc).__name__,
                    )

            mode, fallback_reason = self._v69_fallback_reason(
                status=status,
                fault=fault,
                saw_returning=saw_returning,
                return_elapsed=return_elapsed,
                dock_reasserted=dock_sent,
                pose_stable_seconds=0.0,
                battery_start=battery_start,
                battery_now=battery,
            )

            self._v69_transition_diag.update({
                "last_status": status,
                "last_fault": fault,
                "last_charging_state": None,
                "last_battery": battery,
                "dock_sent": bool(dock_sent),
                "dock_reasserted": bool(dock_sent),
                "saw_returning": bool(saw_returning),
                "return_elapsed": round(return_elapsed, 1),
                "fallback_confirmed": False,
                "fallback_mode": None,
                "fallback_reason": None,
                "timeout": False,
            })

            current = (
                status,
                fault,
                battery,
                bool(dock_sent),
                bool(saw_returning),
                None if distance is None else round(distance, 2),
                near_no_charge_samples,
                dock_retries,
            )
            if current != last_tuple:
                self._post_ui(
                    "v67_transition_sample",
                    serial,
                    status,
                    None,
                    battery,
                    dock_sent,
                    saw_returning,
                )
                last_tuple = current

            reason = None
            confirm_mode = None
            if direct_samples >= self.BASE_CONFIRM_SAMPLES:
                reason = direct_reason
                confirm_mode = "status4"
            elif mode == "battery-rise":
                reason = fallback_reason
                confirm_mode = "battery-rise"

            if reason is not None:
                self._v71_return_confirm_mode = confirm_mode
                self._v69_transition_diag.update({
                    "base_confirmed": True,
                    "base_confirmed_by": reason,
                    "fallback_confirmed": confirm_mode != "status4",
                    "fallback_mode": confirm_mode,
                    "fallback_reason": reason,
                    "confirmed_pose_key": self._v69_pose_key(vacuum, raw_robot),
                })
                self._post_ui(
                    "v67_base_confirmed",
                    serial,
                    status,
                    None,
                    battery,
                    reason,
                    dock_sent,
                    saw_returning,
                )
                return

            time.sleep(self.BASE_POLL_SECONDS)

        self._v69_transition_diag["timeout"] = True
        self._post_ui("v67_transition_timeout", serial)

    def _v67_recheck_base_before_step2(self, serial):
        """V73: Paso 2 requiere carga real o subida de batería; nunca proximidad."""
        if serial != self._v67_watch_serial:
            return
        self._v67_start_scheduled = False
        if not self._auto_step2_pending or self.mapping_active or not self.vacuum:
            return

        vacuum = self.vacuum

        def worker():
            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                battery = self._v67_int(state.get("battery"))

                if status == 4 and fault == 0:
                    self._post_ui(
                        "v67_start_step2",
                        serial,
                        status,
                        None,
                        battery,
                        "status=4 cargando",
                    )
                    return

                diag = dict(self._v69_transition_diag or {})
                mode = str(diag.get("fallback_mode") or "")
                confirmed_battery = self._v67_int(diag.get("last_battery"))
                if (
                    mode == "battery-rise"
                    and fault == 0
                    and status in (3, 4)
                    and battery is not None
                    and confirmed_battery is not None
                    and battery >= confirmed_battery
                ):
                    self._post_ui(
                        "v67_start_step2",
                        serial,
                        status,
                        None,
                        battery,
                        "subida de batería revalidada",
                    )
                    return

                self._post_ui(
                    "v67_base_lost",
                    serial,
                    status,
                    None,
                    battery,
                )
            except Exception as exc:
                self._post_ui(
                    "v67_transition_probe_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V73 ACTIVO · fases incrementales + anti-bucle + dock seguro",
            "========================================================================",
            f"fase única V73: {self._v73_session_phase} · mapping_phase heredada={int(getattr(self, 'mapping_phase', 0) or 0)}",
            f"puntos nuevos Paso 1 vistos/guardados: {self._v73_phase_new.get(1, 0)}/{self._v73_phase_saved.get(1, 0)}",
            f"puntos nuevos Paso 2 vistos/guardados: {self._v73_phase_new.get(2, 0)}/{self._v73_phase_saved.get(2, 0)}",
            f"puntos de tránsito consumidos/no reasignados: {self._v73_transit_points}",
            f"claves 10/24 consumidas: {len(self._v73_seen_track_keys)}",
            f"recuperaciones atasco: {self._v73_recovery_count}/{self.MAX_STALL_RECOVERIES} · activa={bool(self._v73_recovery_active)}",
            f"última recuperación: {self._v73_last_recovery_reason or '—'}",
            f"repetición de sector detectada: {bool(self._v73_repeat_triggered)}",
            f"reintentos de acople: {self._v73_dock_retries}/{self.DOCK_MAX_RETRIES} · fallo final={bool(self._v73_dock_failed)}",
            f"guardia de acople general: {bool(self._v73_dock_guard_active)} · motivo={self._v73_dock_guard_reason or '—'}",
            f"pose retorno parseada: {self._v73_last_parsed_return_pose!r}",
            "regla V73: cada punto acumulado 10/24 se consume una sola vez y recibe la fase vigente al llegar",
            "regla V73: los puntos del regreso a base se consumen como tránsito y nunca reaparecen en Paso 2",
            "regla V73: distancia a base parsea también el 10/24 crudo tipo 'x_y_ángulo'",
            "regla V73: proximidad al origen NO autoriza Paso 2; sólo status=4 o subida real de batería",
            "regla V73: en Paso 2, giro sin avance o repetición prolongada dispara escape limitado; tras varios fallos se detiene y vuelve a base",
            "regla V73: cualquier retorno vigilado con acople sin carga retrocede/reintenta y finalmente detiene ruedas para proteger batería",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

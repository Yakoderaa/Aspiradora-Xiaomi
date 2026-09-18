import math
import statistics
import threading
import time
from collections import deque
from tkinter import messagebox

import app_v76


class App(app_v76.App):
    """V77: coordenadas físicas en metros + base 10/22 + filtro cinemático."""

    RAW_TO_METERS = 0.10
    BASE_CAPTURE_SAMPLES = 6
    BASE_CAPTURE_INTERVAL = 0.22
    BASE_MIN_VALID_SAMPLES = 3
    BASE_STABILITY_RAW = 1.0
    RETURN_MIN_DEPARTURE = 0.35

    MAP_CELL_SIZE = 0.25
    MIN_COVERAGE_CELLS = 20
    MIN_MAPPING_SECONDS = 180.0
    NO_NEW_AREA_SECONDS = 150.0

    STALL_POSITION_SPAN = 0.08
    STALL_MIN_SECONDS = 28.0
    REPEAT_WINDOW_SECONDS = 240.0
    REPEAT_POSITION_SPAN = 0.80

    TURN_FILTER_ANGLE = 0.45
    TURN_FILTER_MAX_STEP = 0.30
    TURN_FILTER_MAX_TRANSLATION = 0.03
    POSITION_JITTER_METERS = 0.015

    CORRIDOR_WINDOW_SECONDS = 120.0
    CORRIDOR_MIN_SECONDS = 90.0
    CORRIDOR_MIN_SAMPLES = 45
    CORRIDOR_MIN_LENGTH = 0.80
    CORRIDOR_MAX_WIDTH = 0.25
    CORRIDOR_MIN_REVERSALS = 4
    CORRIDOR_STEP_EPSILON = 0.04
    CORRIDOR_MAX_RECOVERIES = 1

    BASE_POINT_ID = -770000001

    def __init__(self):
        self._v77_base_raw = None
        self._v77_base_capture_valid = 0
        self._v77_base_capture_status = None
        self._v77_base_capture_spread = None

        self._v77_filter_last_raw = None
        self._v77_filter_last_output = None
        self._v77_turn_translations_filtered = 0
        self._v77_jitter_points_filtered = 0
        self._v77_base_point_saved = False

        self._v77_corridor_samples = deque()
        self._v77_corridor_events = 0
        self._v77_corridor_finishing = False
        self._v77_corridor_last_geometry = None

        self._v77_status4_confirmations = 0
        super().__init__()

    # ============================================================= base real
    @staticmethod
    def _v77_valid_base_xy(parsed):
        if not isinstance(parsed, dict):
            return None
        try:
            x = float(parsed.get("x"))
            y = float(parsed.get("y"))
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        # 255_255 es el sentinela observado del B112, no una base física.
        if x >= 250.0 and y >= 250.0:
            return None
        return x, y

    def _v77_capture_base_reference(self, vacuum):
        valid = []
        statuses = []
        for _ in range(self.BASE_CAPTURE_SAMPLES):
            try:
                values = vacuum._get_many([
                    ("charging_base", 10, 22),
                    ("status", 2, 1),
                ])
                parsed = vacuum.parse_position(values.get("charging_base"))
                xy = self._v77_valid_base_xy(parsed)
                if xy is not None:
                    valid.append(xy)
                try:
                    statuses.append(int(values.get("status")))
                except Exception:
                    pass
            except Exception:
                pass
            time.sleep(self.BASE_CAPTURE_INTERVAL)

        self._v77_base_capture_valid = len(valid)
        self._v77_base_capture_status = statuses[-1] if statuses else None
        if len(valid) < self.BASE_MIN_VALID_SAMPLES:
            raise RuntimeError(
                "No pude leer una base estable en 10/22. "
                "Dejá el E10 correctamente acoplado y volvé a iniciar el mapa."
            )

        mx = float(statistics.median([p[0] for p in valid]))
        my = float(statistics.median([p[1] for p in valid]))
        spread = max(math.hypot(x - mx, y - my) for x, y in valid)
        self._v77_base_capture_spread = spread
        if spread > self.BASE_STABILITY_RAW:
            raise RuntimeError(
                "La posición 10/22 de la base cambió durante la captura. "
                "Esperá a que el E10 quede quieto/cargando y volvé a intentar."
            )
        return mx, my

    # ===================================================== sistema en metros
    def _v71_normalize_xy(self, xy):
        origin = self._v71_session_origin_raw
        if origin is None or xy is None:
            return None
        try:
            return (
                (float(xy[0]) - float(origin[0])) * self.RAW_TO_METERS,
                (float(xy[1]) - float(origin[1])) * self.RAW_TO_METERS,
            )
        except Exception:
            return None

    def _v71_normalize_point(self, point):
        xy = self._v71_xy(point)
        local = self._v71_normalize_xy(xy)
        if local is None:
            return None
        result = dict(point)
        result["x"] = float(local[0])
        result["y"] = float(local[1])
        return result

    def _v71_raw_distance_to_origin(self, raw_robot):
        origin = self._v71_session_origin_raw
        parsed = self._v73_parse_pose(raw_robot)
        if origin is None or parsed is None:
            return None
        self._v73_last_parsed_return_pose = parsed
        return math.hypot(
            parsed[0] - origin[0],
            parsed[1] - origin[1],
        ) * self.RAW_TO_METERS

    def _v71_return_limit(self):
        departure = max(0.0, float(self._v71_session_max_departure or 0.0))
        return max(0.12, min(0.40, departure * 0.15))

    # ==================================================== filtro cinemático
    def _v77_reset_metric_filter(self):
        self._v77_filter_last_raw = None
        self._v77_filter_last_output = None
        self._v77_turn_translations_filtered = 0
        self._v77_jitter_points_filtered = 0
        self._v77_base_point_saved = False
        self._v77_corridor_samples.clear()
        self._v77_corridor_events = 0
        self._v77_corridor_finishing = False
        self._v77_corridor_last_geometry = None
        self._v77_status4_confirmations = 0

    def _v74_reset_session(self):
        self._v77_reset_metric_filter()
        self._v77_base_raw = None
        self._v77_base_capture_valid = 0
        self._v77_base_capture_status = None
        self._v77_base_capture_spread = None
        return super()._v74_reset_session()

    def _v77_filter_metric_point(self, point):
        normalized = self._v71_normalize_point(point)
        if normalized is None:
            return None

        try:
            x = float(normalized["x"])
            y = float(normalized["y"])
            angle = float(
                point.get("phi", point.get("angle", point.get("yaw", 0.0))) or 0.0
            )
        except Exception:
            return None

        raw_now = (x, y, angle)
        if self._v77_filter_last_raw is None or self._v77_filter_last_output is None:
            self._v77_filter_last_raw = raw_now
            self._v77_filter_last_output = raw_now
            result = dict(point)
            result["x"], result["y"], result["phi"] = x, y, angle
            return result

        px, py, pa = self._v77_filter_last_raw
        ox, oy, _ = self._v77_filter_last_output
        dx = x - px
        dy = y - py
        step = math.hypot(dx, dy)
        dtheta = abs(self._v73_angle_delta(pa, angle))

        if step < self.POSITION_JITTER_METERS:
            dx = 0.0
            dy = 0.0
            self._v77_jitter_points_filtered += 1
        elif dtheta >= self.TURN_FILTER_ANGLE and step <= self.TURN_FILTER_MAX_STEP:
            # Durante un giro diferencial el centro del robot apenas traslada.
            # Si 10/24 introduce un salto lateral, limitamos esa traslación en
            # vez de dejar que cada vuelta cree un escalón ficticio.
            allowed = min(step, self.TURN_FILTER_MAX_TRANSLATION)
            factor = allowed / step if step > 1e-9 else 0.0
            dx *= factor
            dy *= factor
            if allowed + 1e-9 < step:
                self._v77_turn_translations_filtered += 1

        out = (ox + dx, oy + dy, angle)
        self._v77_filter_last_raw = raw_now
        self._v77_filter_last_output = out

        result = dict(point)
        result["x"] = float(out[0])
        result["y"] = float(out[1])
        result["phi"] = float(angle)
        return result

    # ======================================================= mapeo único V77
    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Primero detené el mapeo actual.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda",
            "Se va a borrar el mapa local seleccionado y comenzar un mapa nuevo.\n\n"
            "V77 tomará la base real desde 10/22 antes de salir, convertirá "
            "toda la telemetría a metros y hará una limpieza normal en ECO "
            "con agua apagada.\n\n"
            "Iniciá con el E10 correctamente acoplado a la base.",
            parent=self,
        )
        if not ok:
            return

        self._v74_reset_session()
        self.local_map.clear_map(keep_rooms=False)
        self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self._v75_origin_waiting = False

        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("V77 · fijando la base real antes de comenzar…")

        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            try:
                base_raw = self._v77_capture_base_reference(vacuum)
                if (
                    serial != self._v74_mapping_serial
                    or vacuum is not self.vacuum
                    or not bool(getattr(self, "mapping_active", False))
                ):
                    return

                self._v77_base_raw = tuple(base_raw)
                self._v71_set_origin(
                    base_raw,
                    "10/22 estable antes del sweep · V77",
                )

                vacuum.arm_new_map(1)
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
                vacuum.start_mapping_interior()
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ================================================= trayectoria/robot/base
    def _v77_ensure_origin_from_state(self, state):
        if self._v71_session_origin_raw is not None:
            return True
        parsed = state.get("charging_base") if isinstance(state, dict) else None
        xy = self._v77_valid_base_xy(parsed)
        if xy is None:
            return False
        self._v77_base_raw = tuple(xy)
        return bool(self._v71_set_origin(xy, "10/22 de telemetría · fallback V77"))

    def _v77_merge_base_point(self, phase):
        if self._v77_base_point_saved:
            return
        try:
            added = int(
                self.local_map.merge_trajectory(
                    [{
                        "id": self.BASE_POINT_ID,
                        "x": 0.0,
                        "y": 0.0,
                        "phi": 0.0,
                        "update": 1,
                    }],
                    phase=phase,
                ) or 0
            )
        except Exception:
            added = 0
        self._v77_base_point_saved = True
        if phase in (1, 2):
            self._v73_phase_saved[phase] += max(0, added)
            self._v71_path_points_merged[phase] = self._v73_phase_saved[phase]

    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.App._apply_map_state(self, state)

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
            waiting["charging_base"] = {"x": 0.0, "y": 0.0, "angle": 0.0}
            return app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.App._apply_map_state(self, waiting)

        transformed = dict(state)
        origin = self._v71_session_origin_raw

        if origin is not None:
            new_local = []
            for point in original_path:
                key = self._v73_point_key(point)
                if key is None or key in self._v73_seen_track_keys:
                    continue
                self._v73_seen_track_keys.add(key)
                filtered = self._v77_filter_metric_point(point)
                if filtered is None:
                    continue
                if active and phase in (1, 2) and not (
                    phase == 2 and bool(getattr(self, "mapping_transitioning", False))
                ):
                    new_local.append(filtered)
                else:
                    self._v73_transit_points += 1

            if active and phase in (1, 2) and new_local:
                self._v77_merge_base_point(phase)
                self._v73_phase_new[phase] += len(new_local)
                self._v71_path_points_seen[phase] = self._v73_phase_new[phase]
                try:
                    added = int(self.local_map.merge_trajectory(new_local, phase=phase) or 0)
                except Exception:
                    added = 0
                self._v73_phase_saved[phase] += max(0, added)
                self._v71_path_points_merged[phase] = self._v73_phase_saved[phase]

            parsed_robot = self._v73_parse_pose(state.get("robot"))
            robot = None
            if self._v77_filter_last_output is not None:
                robot = {
                    "x": float(self._v77_filter_last_output[0]),
                    "y": float(self._v77_filter_last_output[1]),
                    "angle": float(parsed_robot[2]) if parsed_robot is not None else float(self._v77_filter_last_output[2]),
                }
            elif parsed_robot is not None:
                local = self._v71_normalize_xy((parsed_robot[0], parsed_robot[1]))
                if local is not None:
                    robot = {
                        "x": float(local[0]),
                        "y": float(local[1]),
                        "angle": float(parsed_robot[2]),
                    }

            if robot is not None:
                transformed["robot"] = robot
                if active:
                    departure = math.hypot(robot["x"], robot["y"])
                    self._v71_session_max_departure = max(
                        float(self._v71_session_max_departure or 0.0),
                        float(departure),
                    )
                    self._v73_track_motion(robot, phase, active)
                    self._v77_note_coverage_metric(robot)

            transformed["charging_base"] = {"x": 0.0, "y": 0.0, "angle": 0.0}
            transformed["path"] = []
            transformed["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V77 metros/base10-22/filtro cinemático"
            )
        elif not active:
            transformed["robot"] = None
            transformed["charging_base"] = None

        return app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.App._apply_map_state(self, transformed)

    # ===================================================== cobertura en metros
    def _v77_note_coverage_metric(self, robot):
        if (
            self._v74_finish_requested
            or not bool(getattr(self, "mapping_active", False))
            or self._v73_recovery_active
        ):
            return
        try:
            x = float(robot["x"])
            y = float(robot["y"])
        except Exception:
            return
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        cell = (
            int(round(x / self.MAP_CELL_SIZE)),
            int(round(y / self.MAP_CELL_SIZE)),
        )
        now = time.monotonic()
        if cell not in self._v74_coverage_cells:
            self._v74_coverage_cells.add(cell)
            self._v74_last_discovery_at = now
            return

        started = self._v74_started_at
        last_new = self._v74_last_discovery_at
        if started is None or last_new is None:
            return
        elapsed = now - started
        no_new = now - last_new
        if (
            elapsed >= self.MIN_MAPPING_SECONDS
            and no_new >= self.NO_NEW_AREA_SECONDS
            and len(self._v74_coverage_cells) >= self.MIN_COVERAGE_CELLS
        ):
            self._v74_request_finish_for_coverage(no_new)

    # ========================================== corredor ida/vuelta repetido
    @staticmethod
    def _v77_corridor_geometry(samples, step_epsilon=0.04):
        if len(samples) < 3:
            return None
        xs = [float(item[1]) for item in samples]
        ys = [float(item[2]) for item in samples]
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
        reversals = max(0, len(signs) - 1)

        return {
            "along_span": float(along_span),
            "cross_span": float(cross_span),
            "reversals": int(reversals),
            "axis_angle": float(angle),
        }

    def _v77_corridor_finish(self, reason):
        if self._v77_corridor_finishing or self._v74_finish_requested or not self.vacuum:
            return
        self._v77_corridor_finishing = True
        self._v74_finish_requested = True
        self._v74_finish_reason = str(reason)
        self._v75_invalidate_recovery()
        serial = self._v74_mapping_serial
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.stop()
            except Exception:
                pass
            time.sleep(0.35)
            try:
                vacuum.dock()
            except Exception:
                pass
            self._post_ui("v74_mapping_complete", serial, str(reason))

        threading.Thread(target=worker, daemon=True).start()

    def _v73_track_motion(self, robot, phase, active):
        # Conserva el antiatasco puntual V76, ahora con distancias en metros.
        super()._v73_track_motion(robot, phase, active)

        if (
            not active
            or int(phase or 0) != 2
            or self._v73_recovery_active
            or self._v74_finish_requested
        ):
            return

        try:
            sample = (
                time.monotonic(),
                float(robot["x"]),
                float(robot["y"]),
                float(robot.get("angle", 0.0) or 0.0),
            )
        except Exception:
            return

        now = sample[0]
        self._v77_corridor_samples.append(sample)
        cutoff = now - self.CORRIDOR_WINDOW_SECONDS
        while self._v77_corridor_samples and self._v77_corridor_samples[0][0] < cutoff:
            self._v77_corridor_samples.popleft()

        samples = list(self._v77_corridor_samples)
        if len(samples) < self.CORRIDOR_MIN_SAMPLES:
            return
        duration = samples[-1][0] - samples[0][0]
        if duration < self.CORRIDOR_MIN_SECONDS:
            return

        geometry = self._v77_corridor_geometry(samples, self.CORRIDOR_STEP_EPSILON)
        self._v77_corridor_last_geometry = geometry
        if not geometry:
            return

        repeated = (
            geometry["along_span"] >= self.CORRIDOR_MIN_LENGTH
            and geometry["cross_span"] <= self.CORRIDOR_MAX_WIDTH
            and geometry["reversals"] >= self.CORRIDOR_MIN_REVERSALS
        )
        if not repeated:
            return

        self._v77_corridor_events += 1
        self._v77_corridor_samples.clear()
        reason = (
            "pasadas ida/vuelta sobre el mismo corredor "
            f"(largo={geometry['along_span']:.2f} m, "
            f"ancho={geometry['cross_span']:.2f} m, "
            f"reversiones={geometry['reversals']})"
        )

        if self._v77_corridor_events <= self.CORRIDOR_MAX_RECOVERIES:
            self._v73_schedule_recovery(phase, reason)
        else:
            self._v77_corridor_finish(
                "Mapeo finalizado: el E10 volvió a repetir el mismo corredor "
                "después de intentar salir; regresando a la base."
            )

    # ========================================= cierre al volver/cargar de verdad
    def _v74_watch_mapping_worker(self, vacuum, serial):
        return_samples = 0
        idle_samples = 0
        seen_moving = False

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

            if self._v73_recovery_active:
                return_samples = 0
                idle_samples = 0
                self._v77_status4_confirmations = 0
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            returning = seen_moving and fault in (None, 0) and status in (3, 4)
            return_samples = return_samples + 1 if returning else 0
            self._v74_return_samples = return_samples

            if seen_moving and fault in (None, 0) and status == 4:
                self._v77_status4_confirmations += 1
            else:
                self._v77_status4_confirmations = 0

            if seen_moving and fault in (None, 0) and status == 1:
                idle_samples += 1
            else:
                idle_samples = 0
            self._v75_idle_samples = idle_samples

            if (
                return_samples >= self.RETURN_CONFIRM_SAMPLES
                or self._v77_status4_confirmations >= self.RETURN_CONFIRM_SAMPLES
            ):
                self._v74_finish_requested = True
                reason = (
                    "Mapeo terminado · el E10 está cargando en la base."
                    if status == 4
                    else "Mapeo terminado · el E10 regresó a la base."
                )
                self._post_ui("v74_mapping_complete", serial, reason)
                return

            if idle_samples >= self.IDLE_FINISH_SAMPLES:
                self._v74_finish_requested = True
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v74_mapping_complete",
                    serial,
                    "Mapeo terminado · el E10 quedó inactivo de forma estable y fue enviado a la base.",
                )
                return

            time.sleep(self.STATUS_POLL_SECONDS)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        geometry = self._v77_corridor_last_geometry or {}
        lines = [
            "DIAGNÓSTICO V77 ACTIVO · metros reales + base 10/22 + cinemática",
            "===================================================================",
            f"factor raw→m: {self.RAW_TO_METERS:.3f}",
            f"base raw fijada: {self._v77_base_raw!r} · fuente={self._v71_session_origin_source or '—'}",
            f"captura base: válidas={self._v77_base_capture_valid}/{self.BASE_CAPTURE_SAMPLES} · spread raw={self._v77_base_capture_spread!r} · status={self._v77_base_capture_status!r}",
            f"máxima salida física: {float(self._v71_session_max_departure or 0.0):.2f} m",
            f"filtro giros: traslaciones limitadas={self._v77_turn_translations_filtered} · jitter={self._v77_jitter_points_filtered}",
            f"base sintética (0,0) guardada: {bool(self._v77_base_point_saved)}",
            f"cobertura: {len(self._v74_coverage_cells)} celdas de {self.MAP_CELL_SIZE:.2f} m",
            f"corredor repetido: eventos={self._v77_corridor_events} · largo={geometry.get('along_span')} · ancho={geometry.get('cross_span')} · reversiones={geometry.get('reversals')}",
            f"confirmaciones status=4: {self._v77_status4_confirmations}/{self.RETURN_CONFIRM_SAMPLES}",
            "regla V77: 10/22 estable define la base física; 255_255 nunca se usa",
            "regla V77: 10/24 y trayectoria se convierten a metros con 1 raw = 0.10 m antes de persistir/renderizar",
            "regla V77: desplazamiento durante giros fuertes se limita para evitar deriva lateral ficticia",
            "regla V77: repetición ida/vuelta en un corredor estrecho intenta una salida y, si reincide, finaliza y vuelve a base",
            "regla V77: status=4 con recorrido real cierra el mapeo aunque el retorno haya sido solicitado manualmente",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

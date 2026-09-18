import math
import threading
import time

import app_v70


class App(app_v70.App):
    """V71: origen único de sesión, llegada real a base y UI de mapas estable."""

    RETURN_NEAR_CONFIRM_SAMPLES = 6
    RETURN_DOCK_REASSERT_SECONDS = 20.0
    RETURN_MIN_DEPARTURE = 2.0
    PHASE2_POLL_SECONDS = 0.45
    PHASE2_EDGE_CONFIRM_SAMPLES = 3
    PHASE2_IDLE_CONFIRM_SAMPLES = 3
    MAP_CARD_REFRESH_SECONDS = 1.0

    def __init__(self):
        self._v71_session_origin_raw = None
        self._v71_session_origin_source = None
        self._v71_session_max_departure = 0.0
        self._v71_return_distance = None
        self._v71_return_threshold = None
        self._v71_return_near_samples = 0
        self._v71_return_confirm_mode = None
        self._v71_path_points_merged = {1: 0, 2: 0}
        self._v71_path_points_seen = {1: 0, 2: 0}

        self._v71_phase2_watch_serial = 0
        self._v71_phase2_watch_active = False
        self._v71_phase2_seen_interior = False
        self._v71_phase2_edge_samples = 0
        self._v71_phase2_idle_samples = 0
        self._v71_phase2_complete_reason = None

        self._v71_card_widgets = []
        self._v71_last_card_refresh = 0.0
        self._v71_last_card_signature = None

        super().__init__()

    # ====================================================== coordenadas sesión
    @staticmethod
    def _v71_xy(point):
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    def _v71_debug_raw_pose(self):
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        live = dict(state.get("v55_live_track") or {})
        pose = live.get("last_pose")
        if isinstance(pose, (list, tuple)) and len(pose) >= 2:
            try:
                return float(pose[0]), float(pose[1])
            except Exception:
                pass

        raw = state.get("raw_robot")
        vacuum = getattr(self, "vacuum", None)
        if raw is not None and vacuum is not None:
            try:
                parsed = vacuum.parse_position(raw)
                xy = self._v71_xy(parsed)
                if xy is not None:
                    return xy
            except Exception:
                pass

        return self._v71_xy(state.get("robot"))

    def _v71_set_origin(self, xy, source):
        if xy is None:
            return False
        try:
            x, y = float(xy[0]), float(xy[1])
        except Exception:
            return False
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
        self._v71_session_origin_raw = (x, y)
        self._v71_session_origin_source = str(source)
        return True

    def _v71_normalize_xy(self, xy):
        origin = self._v71_session_origin_raw
        if origin is None or xy is None:
            return None
        try:
            return float(xy[0]) - origin[0], float(xy[1]) - origin[1]
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

    def _v71_return_limit(self):
        departure = max(0.0, float(self._v71_session_max_departure or 0.0))
        # El 10/24 del B112 observado usa unidades internas enteras. El umbral
        # queda ligado a la excursión real de esta sesión y nunca supera 4.
        return max(1.0, min(4.0, departure * 0.08))

    def _v71_raw_distance_to_origin(self, raw_robot):
        origin = self._v71_session_origin_raw
        xy = self._v71_xy(raw_robot)
        if origin is None or xy is None:
            return None
        return math.hypot(xy[0] - origin[0], xy[1] - origin[1])

    def start_new_mapping(self):
        self._v71_session_origin_raw = None
        self._v71_session_origin_source = None
        self._v71_session_max_departure = 0.0
        self._v71_return_distance = None
        self._v71_return_threshold = None
        self._v71_return_near_samples = 0
        self._v71_return_confirm_mode = None
        self._v71_path_points_merged = {1: 0, 2: 0}
        self._v71_path_points_seen = {1: 0, 2: 0}
        self._v71_phase2_complete_reason = None

        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(before, "10/24 antes de Paso 1")
        return super().start_new_mapping()

    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return super()._apply_map_state(state)

        phase = int(getattr(self, "mapping_phase", 0) or 0)
        active = bool(getattr(self, "mapping_active", False))
        original_path = [
            dict(p) for p in list(state.get("path") or []) if isinstance(p, dict)
        ]
        raw_robot = state.get("robot")

        # Si el primer sondeo previo no estaba disponible, el primer punto real
        # del track del Paso 1 se convierte en origen de toda la sesión.
        if self._v71_session_origin_raw is None and active and phase == 1:
            first_xy = self._v71_xy(original_path[0]) if original_path else self._v71_xy(raw_robot)
            if first_xy is not None:
                self._v71_set_origin(first_xy, "primera pose 10/24 de Paso 1")

        origin = self._v71_session_origin_raw
        transformed = dict(state)

        if origin is not None:
            robot_xy = self._v71_xy(raw_robot)
            if robot_xy is not None:
                distance = math.hypot(robot_xy[0] - origin[0], robot_xy[1] - origin[1])
                if active and phase == 1:
                    self._v71_session_max_departure = max(
                        float(self._v71_session_max_departure or 0.0),
                        float(distance),
                    )
                local_robot = self._v71_normalize_point(raw_robot)
                if local_robot is not None:
                    transformed["robot"] = local_robot

            # La base visual de este mapa es el punto desde el que arrancó la
            # sesión. Nunca usamos 255_255 ni coordenadas FDS para moverla.
            transformed["charging_base"] = {"x": 0.0, "y": 0.0, "angle": 0.0}

            localized_path = []
            for point in original_path:
                local = self._v71_normalize_point(point)
                if local is not None:
                    localized_path.append(local)

            if active and phase in (1, 2) and localized_path and not (
                phase == 2 and bool(getattr(self, "mapping_transitioning", False))
            ):
                self._v71_path_points_seen[phase] = len(localized_path)
                try:
                    self.local_map.merge_trajectory(localized_path, phase=phase)
                    self._v71_path_points_merged[phase] = len(localized_path)
                except Exception:
                    pass

            # V9 y V18 antiguamente guardaban el mismo path dos veces: una vez
            # crudo y otra restando path[0]. V71 ya lo guardó una sola vez en el
            # espacio de sesión; ocultamos el path a las capas heredadas.
            transformed["path"] = []
            transformed["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V71 origen único de sesión"
            )
        elif not active:
            # Un mapa ya guardado no debe deformarse con coordenadas crudas si
            # todavía no conocemos el origen de una nueva sesión.
            transformed["robot"] = None
            transformed["charging_base"] = None

        return super()._apply_map_state(transformed)

    # ======================================================== retorno a base
    @classmethod
    def _v69_fallback_reason(
        cls,
        *,
        status,
        fault,
        saw_returning,
        return_elapsed,
        dock_reasserted,
        pose_stable_seconds,
        battery_start,
        battery_now,
    ):
        # V71 elimina explícitamente stale-return/settled-idle. Una pose quieta
        # lejos de la base nunca vuelve a autorizar Paso 2.
        status = cls._v67_int(status)
        fault = cls._v67_int(fault)
        battery_start = cls._v67_int(battery_start)
        battery_now = cls._v67_int(battery_now)
        if status == 4:
            return "direct", "status=4 cargando"
        if (
            fault == 0
            and status in (3, 4)
            and battery_start is not None
            and battery_now is not None
            and battery_now >= battery_start + 1
            and float(return_elapsed or 0.0) >= 10.0
        ):
            return (
                "battery-rise",
                f"batería subió {battery_start}→{battery_now} durante retorno",
            )
        return None, None

    def _v67_watch_base_worker(self, vacuum, serial):
        deadline = time.monotonic() + self.BASE_WATCH_SECONDS
        returning_since = None
        battery_start = None
        dock_sent = False
        direct_samples = 0
        near_samples = 0
        last_tuple = None

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
                and status in (0, 1, 3, 4)
            )
            near_samples = near_samples + 1 if near_origin else 0
            self._v71_return_near_samples = near_samples

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

            at_base, direct_reason = self._v67_base_evidence(status, None)
            direct_samples = direct_samples + 1 if at_base else 0

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
                "last_charging_state": None,
                "last_battery": battery,
                "dock_sent": bool(dock_sent),
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
                near_samples,
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
            elif near_samples >= self.RETURN_NEAR_CONFIRM_SAMPLES:
                reason = (
                    "10/24 volvió al origen de sesión "
                    f"(distancia {distance:.2f} ≤ {threshold:.2f})"
                )
                confirm_mode = "session-origin"

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
                raw_robot = state.get("robot")

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

                distance = self._v71_raw_distance_to_origin(raw_robot)
                threshold = self._v71_return_limit()
                mode = self._v71_return_confirm_mode

                if (
                    mode == "session-origin"
                    and fault == 0
                    and status in (0, 1, 3, 4)
                    and distance is not None
                    and distance <= threshold
                ):
                    self._post_ui(
                        "v67_start_step2",
                        serial,
                        status,
                        None,
                        battery,
                        (
                            "origen de sesión revalidado "
                            f"(distancia {distance:.2f} ≤ {threshold:.2f})"
                        ),
                    )
                    return

                diag = dict(self._v69_transition_diag or {})
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

    # ================================================== fin real de Paso 2
    def _v71_start_phase2_watch(self):
        if not self.vacuum:
            return
        self._v71_phase2_watch_serial += 1
        serial = self._v71_phase2_watch_serial
        self._v71_phase2_watch_active = True
        self._v71_phase2_seen_interior = False
        self._v71_phase2_edge_samples = 0
        self._v71_phase2_idle_samples = 0
        vacuum = self.vacuum
        threading.Thread(
            target=self._v71_phase2_watch_worker,
            args=(vacuum, serial),
            daemon=True,
        ).start()

    def _v71_phase2_watch_worker(self, vacuum, serial):
        deadline = time.monotonic() + 2 * 60 * 60
        non_edge_samples = 0
        edge_samples = 0
        idle_samples = 0

        while time.monotonic() < deadline:
            if serial != self._v71_phase2_watch_serial:
                return
            if vacuum is not self.vacuum:
                return
            if not self.mapping_active or int(self.mapping_phase or 0) != 2:
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status = self._v67_int(values.get("status"))
                sweep_type = self._v67_int(values.get("sweep_type"))
            except Exception:
                time.sleep(self.PHASE2_POLL_SECONDS)
                continue

            moving = status in (5, 6, 7)
            if moving and sweep_type != 2:
                non_edge_samples += 1
                if non_edge_samples >= 3:
                    self._v71_phase2_seen_interior = True

            if self._v71_phase2_seen_interior and status in (3, 4):
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v71_phase2_complete",
                    serial,
                    "Paso 2 terminó y el E10 inició el regreso a la base.",
                )
                return

            if self._v71_phase2_seen_interior and moving and sweep_type == 2:
                edge_samples += 1
            else:
                edge_samples = 0
            self._v71_phase2_edge_samples = edge_samples

            if edge_samples >= self.PHASE2_EDGE_CONFIRM_SAMPLES:
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.35)
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v71_phase2_complete",
                    serial,
                    "Paso 2 terminó · se bloqueó un nuevo perímetro automático.",
                )
                return

            if self._v71_phase2_seen_interior and status in (0, 1, 2):
                idle_samples += 1
            else:
                idle_samples = 0
            self._v71_phase2_idle_samples = idle_samples

            if idle_samples >= self.PHASE2_IDLE_CONFIRM_SAMPLES:
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v71_phase2_complete",
                    serial,
                    "Paso 2 terminó · interior completado.",
                )
                return

            time.sleep(self.PHASE2_POLL_SECONDS)

        self._v71_phase2_watch_active = False

    def _v67_commit_step2_start(self, serial, status, charging, battery, reason):
        started = super()._v67_commit_step2_start(
            serial, status, charging, battery, reason
        )
        if started:
            self._v71_start_phase2_watch()
        return started

    def start_interior_mapping(self):
        result = super().start_interior_mapping()
        if self.mapping_active and int(self.mapping_phase or 0) == 2:
            self._v71_start_phase2_watch()
        return result

    def _handle_ui_event(self, kind, payload):
        if kind == "v71_phase2_complete":
            serial, reason = payload
            if int(serial) != self._v71_phase2_watch_serial:
                return
            self._v71_phase2_watch_active = False
            self._v71_phase2_complete_reason = str(reason)
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step2_complete = True
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner(str(reason))
            try:
                threading.Thread(
                    target=self._restore_cleaning_preferences,
                    daemon=True,
                ).start()
            except Exception:
                pass
            self.after(100, self._v70_notify_mapping_complete)
            return

        return super()._handle_ui_event(kind, payload)

    # ======================================================== tarjetas estables
    def _v71_ensure_cards(self):
        frame = getattr(self, "_v70_overview_frame", None)
        if frame is None:
            return
        if len(self._v71_card_widgets) == 4:
            return

        for child in frame.winfo_children():
            child.destroy()
        self._v71_card_widgets = []

        for column in range(4):
            card = app_v70.tk.Frame(
                frame,
                bg=app_v70.SURFACE,
                highlightthickness=1,
                highlightbackground=app_v70.BORDER,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0 if column == 3 else 4),
            )
            head = app_v70.tk.Frame(card, bg=app_v70.SURFACE)
            head.pack(fill="x", padx=9, pady=(8, 5))
            name = app_v70.tk.Label(
                head,
                text=f"Mapa {column + 1}",
                bg=app_v70.SURFACE,
                fg=app_v70.TEXT,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            )
            name.pack(side="left", fill="x", expand=True)
            badge = app_v70.tk.Label(
                head,
                text="LIBRE",
                bg=app_v70.SURFACE_2,
                fg=app_v70.MUTED,
                font=("Segoe UI", 7, "bold"),
                padx=6,
                pady=3,
            )
            badge.pack(side="right")
            canvas = app_v70.tk.Canvas(
                card,
                bg=app_v70.MAP_BG,
                width=175,
                height=88,
                highlightthickness=0,
            )
            canvas.pack(fill="x", padx=8)
            info = app_v70.tk.Label(
                card,
                text="",
                bg=app_v70.SURFACE,
                fg=app_v70.MUTED,
                font=("Segoe UI", 7),
                anchor="w",
            )
            info.pack(fill="x", padx=9, pady=(5, 6))
            button = self._button(card, "+ Crear mapa", lambda: None, compact=True)
            button.pack(fill="x", padx=8, pady=(0, 8))

            self._v71_card_widgets.append({
                "card": card,
                "head": head,
                "name": name,
                "badge": badge,
                "canvas": canvas,
                "info": info,
                "button": button,
                "model_id": None,
            })

    def _v70_refresh_map_overview(self, force=False):
        local_map = getattr(self, "local_map", None)
        frame = getattr(self, "_v70_overview_frame", None)
        if not local_map or frame is None:
            self._v70_update_active_map_labels()
            return

        now = time.monotonic()
        if not force and now - self._v71_last_card_refresh < self.MAP_CARD_REFRESH_SECONDS:
            self._v70_update_active_map_labels()
            return

        try:
            library = local_map.library_snapshot()
        except Exception:
            return
        cards = self._v70_card_models(library)
        signature = tuple(
            (
                card.get("id"),
                bool(card.get("active")),
                int(card.get("points", 0) or 0),
                str(card.get("name") or ""),
            )
            for card in cards
        )
        if not force and signature == self._v71_last_card_signature:
            self._v70_update_active_map_labels()
            return

        self._v71_last_card_refresh = now
        self._v71_last_card_signature = signature
        self._v71_ensure_cards()

        for slot, model in zip(self._v71_card_widgets, cards):
            active = bool(model.get("active"))
            empty = bool(model.get("empty"))
            card = slot["card"]
            name = slot["name"]
            badge = slot["badge"]
            canvas = slot["canvas"]
            info = slot["info"]
            button = slot["button"]

            card.configure(
                highlightthickness=2 if active else 1,
                highlightbackground=app_v70.ACCENT if active else app_v70.BORDER,
            )
            name.configure(
                text=model["name"],
                fg=app_v70.TEXT if not empty else app_v70.MUTED,
            )

            if active:
                badge.configure(
                    text="SELECCIONADO",
                    bg=app_v70.ACCENT_SOFT,
                    fg=app_v70.ACCENT,
                )
            elif empty:
                badge.configure(text="LIBRE", bg=app_v70.SURFACE_2, fg=app_v70.MUTED)
            else:
                badge.configure(text="DISPONIBLE", bg=app_v70.SURFACE_2, fg=app_v70.MUTED)

            canvas.delete("all")
            if empty:
                canvas.create_text(
                    88, 36, text="+", fill=app_v70.ACCENT,
                    font=("Segoe UI", 24, "bold"),
                )
                canvas.create_text(
                    88, 62, text="Espacio disponible", fill=app_v70.MUTED,
                    font=("Segoe UI", 8),
                )
                info.configure(text="Creá otro mapa desde esta pestaña")
                button.configure(
                    text="+ Crear mapa",
                    state="normal",
                    command=self._v70_create_map_from_overview,
                )
            else:
                plan = {}
                plan_store = getattr(self, "plan_store", None)
                if plan_store:
                    try:
                        plan = plan_store.snapshot(model["id"])
                    except Exception:
                        plan = {}
                self._v70_render_thumbnail(canvas, model["snapshot"], plan, active)
                info.configure(
                    text=(
                        f"{model['points']} puntos · "
                        f"{len(plan.get('zones', []) or [])} zonas · "
                        f"{len(plan.get('no_go', []) or [])} bloqueos"
                    )
                )
                if active:
                    button.configure(text="Seleccionado", state="disabled", command=lambda: None)
                else:
                    button.configure(
                        text="Seleccionar",
                        state="normal",
                        command=lambda mid=model["id"]: self._v70_select_map(mid),
                    )

                callback = lambda _event, mid=model["id"]: self._v70_select_map(mid)
                for widget in (card, slot["head"], name, canvas):
                    widget.bind("<Button-1>", callback)

        self._v70_update_active_map_labels()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        origin = self._v71_session_origin_raw
        lines = [
            "DIAGNÓSTICO V71 ACTIVO · origen único + llegada real + UI estable",
            "=================================================================",
            f"origen sesión 10/24: {origin!r} · fuente={self._v71_session_origin_source or '—'}",
            f"máxima salida del origen: {float(self._v71_session_max_departure or 0.0):.2f}",
            f"distancia retorno actual: {self._v71_return_distance!r} · umbral={self._v71_return_threshold!r} · muestras cerca={self._v71_return_near_samples}",
            f"confirmación retorno: {self._v71_return_confirm_mode or '—'}",
            f"puntos Paso 1 vistos/guardados: {self._v71_path_points_seen.get(1, 0)}/{self._v71_path_points_merged.get(1, 0)}",
            f"puntos Paso 2 vistos/guardados: {self._v71_path_points_seen.get(2, 0)}/{self._v71_path_points_merged.get(2, 0)}",
            f"watch Paso 2: {bool(self._v71_phase2_watch_active)} · interior visto={bool(self._v71_phase2_seen_interior)} · edge posterior={self._v71_phase2_edge_samples}",
            f"fin Paso 2: {self._v71_phase2_complete_reason or '—'}",
            "regla V71: status=3 nunca confirma base por tiempo/quietud; debe volver al origen de sesión, cargar o subir batería",
            "regla V71: trayectoria 10/24 se guarda una sola vez y Paso 1/Paso 2 comparten el mismo origen",
            "regla V71: 10/22=255_255 nunca mueve la base visual; la base del mapa de sesión es (0,0)",
            "regla V71: las cuatro tarjetas se crean una vez; sólo se actualiza su contenido, sin destruir el layout",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

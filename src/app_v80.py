import copy
import hashlib
import json
import math
import time

import app_v79
import app_v70


class App(app_v79.App):
    """V80: arranque validado + snapshot único + comparación IJAI."""

    INITIAL_BUFFER_START_RADIUS = 0.35
    INITIAL_BUFFER_MAX_STEP = 0.35
    INITIAL_BUFFER_MIN_POINTS = 4
    INITIAL_BUFFER_MIN_SPAN = 0.10
    INITIAL_BUFFER_MAX_POINTS = 12

    CORRIDOR_MAX_WIDTH = 0.30

    def __init__(self):
        self._v80_initial_buffer = []
        self._v80_initial_validated = False
        self._v80_initial_buffer_rejected = 0
        self._v80_initial_buffer_resets = 0
        self._v80_initial_flush_count = 0

        self._v80_render_snapshot = None
        self._v80_main_points = 0
        self._v80_main_hash = "—"
        self._v80_thumb_points = 0
        self._v80_thumb_hash = "—"

        self._v80_ijai_relative = None
        self._v80_ijai_delta = None
        self._v80_ijai_age = None
        self._v80_ijai_base_source = "—"
        super().__init__()

    # =========================================================== reset sesión
    def _v74_reset_session(self):
        self._v80_initial_buffer = []
        self._v80_initial_validated = False
        self._v80_initial_buffer_rejected = 0
        self._v80_initial_buffer_resets = 0
        self._v80_initial_flush_count = 0
        self._v80_render_snapshot = None
        self._v80_main_points = 0
        self._v80_main_hash = "—"
        self._v80_thumb_points = 0
        self._v80_thumb_hash = "—"
        self._v80_ijai_relative = None
        self._v80_ijai_delta = None
        self._v80_ijai_age = None
        self._v80_ijai_base_source = "—"
        return super()._v74_reset_session()

    # =============================================== buffer inicial validado
    @staticmethod
    def _v80_point_distance(point):
        try:
            return math.hypot(float(point["x"]), float(point["y"]))
        except Exception:
            return float("inf")

    @staticmethod
    def _v80_step(a, b):
        try:
            return math.hypot(
                float(b["x"]) - float(a["x"]),
                float(b["y"]) - float(a["y"]),
            )
        except Exception:
            return float("inf")

    def _v80_buffer_initial_point(self, point):
        """Devuelve la lista que ya puede persistirse.

        Los puntos se consumen en 10/24 aunque todavía no se dibujen. La sesión
        sólo se habilita cuando empieza cerca del dock y mantiene continuidad.
        """
        if self._v80_initial_validated:
            return [point]

        distance = self._v80_point_distance(point)
        if not self._v80_initial_buffer:
            if distance > self.INITIAL_BUFFER_START_RADIUS:
                self._v80_initial_buffer_rejected += 1
                # Un outlier inicial tampoco puede convertirse en referencia
                # del filtro de giro para la muestra siguiente.
                self._v79_previous_absolute = None
                return []
            self._v80_initial_buffer = [dict(point)]
            return []

        step = self._v80_step(self._v80_initial_buffer[-1], point)
        if step > self.INITIAL_BUFFER_MAX_STEP:
            self._v80_initial_buffer_resets += 1
            self._v80_initial_buffer_rejected += 1
            self._v79_previous_absolute = None
            if distance <= self.INITIAL_BUFFER_START_RADIUS:
                self._v80_initial_buffer = [dict(point)]
            else:
                self._v80_initial_buffer = []
            return []

        self._v80_initial_buffer.append(dict(point))
        if len(self._v80_initial_buffer) > self.INITIAL_BUFFER_MAX_POINTS:
            self._v80_initial_buffer = self._v80_initial_buffer[
                -self.INITIAL_BUFFER_MAX_POINTS:
            ]

        max_radius = max(
            self._v80_point_distance(item)
            for item in self._v80_initial_buffer
        )
        enough = len(self._v80_initial_buffer) >= self.INITIAL_BUFFER_MIN_POINTS
        moved = max_radius >= self.INITIAL_BUFFER_MIN_SPAN

        # Si pasó suficiente tiempo girando prácticamente sobre la base, igual
        # validamos: es una secuencia coherente y no puede crear un latigazo.
        quiet_but_safe = (
            len(self._v80_initial_buffer) >= 8
            and max_radius <= self.INITIAL_BUFFER_START_RADIUS
        )

        if enough and (moved or quiet_but_safe):
            flushed = [dict(item) for item in self._v80_initial_buffer]
            self._v80_initial_buffer = []
            self._v80_initial_validated = True
            self._v80_initial_flush_count += len(flushed)
            return flushed

        return []

    # ======================================= trayectoria V79 + buffer V80
    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return (
                app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
                .app_v72.app_v71.app_v70.App._apply_map_state(self, state)
            )

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
                app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
                .app_v72.app_v71.app_v70.App._apply_map_state(self, waiting)
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

                if active and phase in (1, 2) and not (
                    phase == 2
                    and bool(getattr(self, "mapping_transitioning", False))
                ):
                    new_local.extend(accepted)
                else:
                    self._v73_transit_points += max(1, len(accepted))

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
                self._v71_path_points_merged[phase] = (
                    self._v73_phase_saved[phase]
                )

            parsed_robot = self._v73_parse_pose(state.get("robot"))
            absolute_robot = None
            if parsed_robot is not None:
                local = self._v71_normalize_xy(
                    (parsed_robot[0], parsed_robot[1])
                )
                if local is not None:
                    absolute_robot = {
                        "x": float(local[0]),
                        "y": float(local[1]),
                        "angle": float(parsed_robot[2]),
                    }

            display_robot = absolute_robot
            if latest_filtered is not None:
                display_robot = {
                    "x": float(latest_filtered["x"]),
                    "y": float(latest_filtered["y"]),
                    "angle": float(
                        latest_filtered.get(
                            "phi",
                            absolute_robot["angle"]
                            if absolute_robot is not None
                            else 0.0,
                        )
                    ),
                }

            if display_robot is not None:
                transformed["robot"] = display_robot

            # Sólo después de validar el arranque permitimos que cobertura y
            # detectores interpreten la sesión. Así el primer bloque de datos
            # transitorios no puede disparar corredor/antiatasco.
            if (
                active
                and absolute_robot is not None
                and self._v80_initial_validated
            ):
                departure = math.hypot(
                    absolute_robot["x"],
                    absolute_robot["y"],
                )
                self._v71_session_max_departure = max(
                    float(self._v71_session_max_departure or 0.0),
                    float(departure),
                )
                self._v73_track_motion(
                    absolute_robot,
                    phase,
                    active,
                )
                self._v77_note_coverage_metric(absolute_robot)

            transformed["charging_base"] = {
                "x": 0.0,
                "y": 0.0,
                "angle": 0.0,
            }
            transformed["path"] = []
            transformed["path_source"] = (
                str(state.get("path_source") or "10/24")
                + " · V80 buffer-validado/snapshot-unico"
            )
        elif not active:
            transformed["robot"] = None
            transformed["charging_base"] = None

        return (
            app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
            .app_v72.app_v71.app_v70.App._apply_map_state(
                self,
                transformed,
            )
        )

    # ============================================= snapshot único UI
    @staticmethod
    def _v80_snapshot_signature(snapshot):
        points = []
        for point in list((snapshot or {}).get("points") or []):
            if not isinstance(point, dict):
                continue
            try:
                points.append((
                    int(point.get("phase", 0) or 0),
                    int(point.get("id", 0) or 0),
                    round(float(point.get("x", 0.0)), 4),
                    round(float(point.get("y", 0.0)), 4),
                ))
            except Exception:
                continue
        payload = json.dumps(points, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha1(payload.encode("ascii", "strict")).hexdigest()[:12]
        return len(points), digest

    def _v70_card_models(self, library):
        cards = app_v70.App._v70_card_models(library)
        snapshot = self._v80_render_snapshot
        if snapshot is None:
            return cards

        count, digest = self._v80_snapshot_signature(snapshot)
        for card in cards:
            if bool(card.get("active")) and not bool(card.get("empty")):
                card["snapshot"] = copy.deepcopy(snapshot)
                card["points"] = count
                self._v80_thumb_points = count
                self._v80_thumb_hash = digest
                break
        return cards

    def _render_maps(self):
        """Mapa grande y miniatura nacen del mismo snapshot exacto."""
        local_map = getattr(self, "local_map", None)
        if not local_map:
            return

        try:
            snapshot = local_map.snapshot()
        except Exception:
            return

        self._v80_render_snapshot = copy.deepcopy(snapshot)
        self._v80_main_points, self._v80_main_hash = (
            self._v80_snapshot_signature(snapshot)
        )

        for canvas in (
            getattr(self, "home_map_canvas", None),
            getattr(self, "map_canvas", None),
        ):
            if canvas and canvas.winfo_exists():
                self._render_map_canvas(canvas, snapshot)

        points = list(snapshot.get("points") or [])
        rooms = list(snapshot.get("rooms") or [])

        if hasattr(self, "map_points_label"):
            if points:
                self.map_points_label.configure(
                    text=(
                        f"{len(points)} puntos de recorrido · "
                        f"{len(rooms)} habitaciones locales"
                    )
                )
            else:
                self.map_points_label.configure(
                    text="Creá un mapa nuevo para empezar"
                )

        if hasattr(self, "mapping_badge"):
            self.mapping_badge.configure(
                text="● EN VIVO · RECORRIDO" if self.mapping_active else ""
            )

        if hasattr(self, "map_status_label"):
            self.map_status_label.configure(
                text=(
                    "Mapeando en tiempo real · recorrido único"
                    if self.mapping_active
                    else ("Mapa local guardado" if points else "Sin mapa local")
                ),
                fg=app_v70.GREEN if self.mapping_active else app_v70.MUTED,
            )

        if hasattr(self, "live_map_label"):
            self.live_map_label.configure(
                text=(
                    f"● LIVE · {len(points)} puntos · snapshot {self._v80_main_hash}"
                    if self.mapping_active
                    else ""
                ),
                fg=app_v70.GREEN if self.mapping_active else app_v70.MUTED,
            )

        if hasattr(self, "settings_map_label"):
            self.settings_map_label.configure(
                text=(
                    f"Mapa local: {len(points)} puntos · "
                    f"{len(rooms)} habitaciones"
                )
            )

        try:
            self._refresh_room_list(snapshot)
        except Exception:
            pass

        # V71 actualiza las tarjetas sin destruir el layout. Nuestro override
        # de _v70_card_models inyecta este MISMO snapshot en la tarjeta activa.
        try:
            self._v70_refresh_map_overview(force=True)
            self._v70_update_active_map_labels()
        except Exception:
            pass

    # ========================================== comparación diagnóstica IJAI
    @staticmethod
    def _v80_pair(value):
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            x = float(value[0])
            y = float(value[1])
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    def _v80_update_ijai_comparison(self):
        robot = self._v80_pair(getattr(self, "_v40_native_robot", None))
        base = self._v80_pair(getattr(self, "_v40_native_base", None))

        # 25.5,25.5 equivale al sentinela 255_255 escalado. En ese caso
        # comparamos currentPose contra el dock B112 confirmado de 6.0,6.0.
        if base is not None and base[0] < 20.0 and base[1] < 20.0:
            base_ref = base
            self._v80_ijai_base_source = "chargeStation IJAI"
        else:
            base_ref = (6.0, 6.0)
            self._v80_ijai_base_source = "dock B112 6.0,6.0"

        relative = None
        if robot is not None:
            relative = (
                float(robot[0]) - float(base_ref[0]),
                float(robot[1]) - float(base_ref[1]),
            )
        self._v80_ijai_relative = relative

        absolute = self._v79_last_absolute
        if relative is not None and absolute is not None:
            self._v80_ijai_delta = (
                float(relative[0]) - float(absolute[0]),
                float(relative[1]) - float(absolute[1]),
            )
        else:
            self._v80_ijai_delta = None

        upload_date = getattr(self, "_v40_upload_date", None)
        try:
            upload_date = float(upload_date)
            now = time.time()
            if 1_000_000_000 <= upload_date <= now + 86400:
                self._v80_ijai_age = max(0.0, now - upload_date)
            else:
                self._v80_ijai_age = None
        except Exception:
            self._v80_ijai_age = None

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        self._v80_update_ijai_comparison()
        inherited = super()._diagnostic_text()

        snapshots_equal = (
            self._v80_main_points == self._v80_thumb_points
            and self._v80_main_hash == self._v80_thumb_hash
            and self._v80_main_hash != "—"
        )

        lines = [
            "DIAGNÓSTICO V80 ACTIVO · arranque validado + snapshot único + IJAI",
            "===================================================================",
            (
                "buffer inicial: "
                f"validado={self._v80_initial_validated} · "
                f"pendientes={len(self._v80_initial_buffer)} · "
                f"flush={self._v80_initial_flush_count} · "
                f"rechazados={self._v80_initial_buffer_rejected} · "
                f"resets={self._v80_initial_buffer_resets}"
            ),
            (
                "umbrales arranque: "
                f"radio≤{self.INITIAL_BUFFER_START_RADIUS:.2f} m · "
                f"paso≤{self.INITIAL_BUFFER_MAX_STEP:.2f} m · "
                f"mínimo={self.INITIAL_BUFFER_MIN_POINTS} puntos"
            ),
            (
                "snapshot mapa grande: "
                f"{self._v80_main_points} puntos · sha12={self._v80_main_hash}"
            ),
            (
                "snapshot miniatura: "
                f"{self._v80_thumb_points} puntos · sha12={self._v80_thumb_hash}"
            ),
            f"snapshots idénticos: {snapshots_equal}",
            f"corredor ancho máximo V80: {self.CORRIDOR_MAX_WIDTH:.2f} m",
            (
                "IJAI relativo: "
                f"{self._v80_ijai_relative!r} · "
                f"base={self._v80_ijai_base_source} · "
                f"edad={self._v80_ijai_age!r}s"
            ),
            f"IJAI - 10/24 absoluto: {self._v80_ijai_delta!r}",
            "regla V80: ningún punto se persiste hasta validar continuidad física desde el dock",
            "regla V80: mapa grande y tarjeta activa reciben el mismo snapshot y deben compartir cantidad/hash",
            "regla V80: IJAI es sólo diagnóstico; no mueve el robot ni corrige la trayectoria",
            "regla V80: el detector de corredor acepta hasta 0.30 m de ancho manteniendo tiempo y reversiones",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

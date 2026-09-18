import math

import app_v78


class App(app_v78.App):
    """V79: filtro absoluto sin deriva + recoveries separados."""

    INITIAL_GATE_RADIUS_METERS = 0.80

    def __init__(self):
        self._v79_previous_absolute = None
        self._v79_last_absolute = None
        self._v79_last_filtered = None
        self._v79_last_filter_error = 0.0
        self._v79_max_filter_error = 0.0
        self._v79_initial_gate_open = False
        self._v79_initial_rejected = 0
        self._v79_stationary_recoveries = 0
        self._v79_corridor_recoveries = 0
        super().__init__()

    # =========================================================== reset sesión
    def _v74_reset_session(self):
        self._v79_previous_absolute = None
        self._v79_last_absolute = None
        self._v79_last_filtered = None
        self._v79_last_filter_error = 0.0
        self._v79_max_filter_error = 0.0
        self._v79_initial_gate_open = False
        self._v79_initial_rejected = 0
        self._v79_stationary_recoveries = 0
        self._v79_corridor_recoveries = 0
        return super()._v74_reset_session()

    # ============================================ métrica absoluta + filtro
    def _v79_absolute_metric_point(self, point):
        normalized = self._v71_normalize_point(point)
        if normalized is None:
            return None
        try:
            x = float(normalized["x"])
            y = float(normalized["y"])
            angle = float(
                point.get(
                    "phi",
                    point.get("angle", point.get("yaw", 0.0)),
                ) or 0.0
            )
        except Exception:
            return None

        result = dict(point)
        result["x"] = x
        result["y"] = y
        result["phi"] = angle
        return result

    def _v77_filter_metric_point(self, point):
        """Filtra sólo la muestra actual; jamás integra error.

        V77 hacía out = output_anterior + delta_filtrado. Si una vuelta
        limitaba varios deltas, el error quedaba acumulado para siempre.
        V79 calcula cada muestra desde (raw - base) * 0.10 y usa el filtro
        únicamente para decidir la representación de ESA muestra.
        """
        absolute = self._v79_absolute_metric_point(point)
        if absolute is None:
            return None

        x = float(absolute["x"])
        y = float(absolute["y"])
        angle = float(absolute.get("phi", 0.0) or 0.0)
        current = (x, y, angle)
        self._v79_last_absolute = current

        # Primeros datos: como el robot parte físicamente del dock, no
        # persistimos una muestra inicial imposible de conciliar con la base.
        if not self._v79_initial_gate_open:
            distance = math.hypot(x, y)
            if distance > self.INITIAL_GATE_RADIUS_METERS:
                self._v79_initial_rejected += 1
                self._v77_filter_last_raw = current
                return None
            self._v79_initial_gate_open = True

        previous = self._v79_previous_absolute
        out_x, out_y = x, y

        if previous is not None:
            px, py, pa = previous
            dx = x - px
            dy = y - py
            step = math.hypot(dx, dy)
            dtheta = abs(self._v73_angle_delta(pa, angle))

            if step < self.POSITION_JITTER_METERS:
                # Para esta única muestra conservamos la posición absoluta
                # anterior; la próxima vuelve a calcularse desde raw/base.
                out_x, out_y = px, py
                self._v77_jitter_points_filtered += 1
            elif (
                dtheta >= self.TURN_FILTER_ANGLE
                and step <= self.TURN_FILTER_MAX_STEP
            ):
                allowed = min(step, self.TURN_FILTER_MAX_TRANSLATION)
                factor = allowed / step if step > 1e-9 else 0.0
                out_x = px + dx * factor
                out_y = py + dy * factor
                if allowed + 1e-9 < step:
                    self._v77_turn_translations_filtered += 1

        # Clave V79: el estado de referencia siguiente es SIEMPRE el absoluto,
        # nunca el punto filtrado.
        self._v79_previous_absolute = current
        filtered = (float(out_x), float(out_y), angle)
        self._v79_last_filtered = filtered
        self._v77_filter_last_raw = current
        self._v77_filter_last_output = filtered

        error = math.hypot(out_x - x, out_y - y)
        self._v79_last_filter_error = float(error)
        self._v79_max_filter_error = max(
            float(self._v79_max_filter_error or 0.0),
            float(error),
        )

        result = dict(point)
        result["x"] = float(out_x)
        result["y"] = float(out_y)
        result["phi"] = angle
        return result

    # =============================================== recoveries independientes
    @staticmethod
    def _v79_recovery_kind(reason):
        text = str(reason or "").lower()
        if "pasadas ida/vuelta" in text or "sector repetido" in text:
            return "corridor"
        return "stationary"

    def _v73_schedule_recovery(self, phase, reason):
        """Reusa el worker seguro V75, pero con presupuestos separados.

        El worker heredado incrementa _v73_recovery_count de forma sincrónica
        antes de crear su thread. Le presentamos el contador del mecanismo
        correspondiente y después restauramos el total sólo para diagnóstico.
        """
        kind = self._v79_recovery_kind(reason)

        if kind == "corridor":
            selected = int(self._v79_corridor_recoveries or 0)
        else:
            selected = int(self._v79_stationary_recoveries or 0)

        self._v73_recovery_count = selected
        super()._v73_schedule_recovery(phase, reason)
        updated = int(self._v73_recovery_count or selected)

        if kind == "corridor":
            self._v79_corridor_recoveries = max(selected, updated)
        else:
            self._v79_stationary_recoveries = max(selected, updated)

        # Compatibilidad con el diagnóstico histórico V73: muestra total, pero
        # ese total ya no gobierna los límites de cada mecanismo.
        self._v73_recovery_count = (
            int(self._v79_stationary_recoveries or 0)
            + int(self._v79_corridor_recoveries or 0)
        )

    # ====================================== trayectoria + detectores absolutos
    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return (
                app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
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
                app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
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

                # Se consume incluso si el gate inicial lo rechaza: un outlier
                # inicial jamás reaparece después en la miniatura.
                self._v73_seen_track_keys.add(key)

                filtered = self._v77_filter_metric_point(point)
                if filtered is None:
                    continue

                latest_filtered = filtered
                if active and phase in (1, 2) and not (
                    phase == 2
                    and bool(getattr(self, "mapping_transitioning", False))
                ):
                    new_local.append(filtered)
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
                self._v71_path_points_merged[phase] = (
                    self._v73_phase_saved[phase]
                )

            # Posición absoluta del robot: siempre vuelve a raw/base. Los
            # detectores y la cobertura NO reciben la trayectoria suavizada.
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

            if active and absolute_robot is not None:
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
                + " · V79 absoluto/no-drift"
            )
        elif not active:
            transformed["robot"] = None
            transformed["charging_base"] = None

        return (
            app_v78.app_v77.app_v76.app_v75.app_v74.app_v73
            .app_v72.app_v71.app_v70.App._apply_map_state(
                self,
                transformed,
            )
        )

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()

        raw_pos = self._v79_last_absolute
        filtered = self._v79_last_filtered
        lines = [
            "DIAGNÓSTICO V79 ACTIVO · filtro absoluto sin deriva acumulativa",
            "=================================================================",
            f"raw→metros absoluto: {raw_pos!r}",
            f"posición filtrada actual: {filtered!r}",
            f"error filtro actual: {self._v79_last_filter_error:.3f} m · máximo={self._v79_max_filter_error:.3f} m",
            f"gate inicial: abierto={self._v79_initial_gate_open} · rechazados={self._v79_initial_rejected} · radio={self.INITIAL_GATE_RADIUS_METERS:.2f} m",
            f"recoveries separados: estacionario={self._v79_stationary_recoveries} · corredor={self._v79_corridor_recoveries}",
            "regla V79: cada muestra parte siempre de (10/24 - base) * 0.10; ninguna corrección se acumula en la siguiente",
            "regla V79: el filtro sólo puede modificar/rechazar la muestra actual; cobertura y detectores usan coordenadas absolutas",
            "regla V79: puntos iniciales fuera del radio físico del dock se consumen pero no se persisten",
            "regla V79: atasco estacionario y corredor repetido tienen contadores independientes",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

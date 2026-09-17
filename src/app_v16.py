import math
import threading
import time

import app_v15


class App(app_v15.App):
    """v16: mapa de paredes por coordenadas en vivo + EDGE continuo sin reinicios."""

    def __init__(self):
        # Dos fuentes posibles de posición. Cada una usa su propio origen para
        # evitar que una referencia absoluta/reiniciada del firmware desplace
        # visualmente al robot lejos de la base.
        self._coord_origins = {}
        self._coord_prev_local = {}
        self._coord_last_change = {}
        self._coord_active_source = None
        self._coord_global_last = None
        self._coord_motion_history = []
        self._coord_stream_changes = 0

        self._live_point_id = {1: 0, 2: 0}
        self._live_last_point = {1: None, 2: None}
        self._mapping_started_at = 0.0
        super().__init__()

        if hasattr(self, "mapping_steps_info"):
            self.mapping_steps_info.configure(
                text="PAREDES EN VIVO por coordenadas · EDGE continuo · ECO mínimo · Paso 1 → base → Paso 2"
            )

    # ----------------------------------------------------- coordenadas locales
    @staticmethod
    def _pose_from_dict(point, angle_key="angle"):
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            return None
        try:
            x = float(point["x"])
            y = float(point["y"])
            angle = float(point.get(angle_key, point.get("phi", 0)) or 0)
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(angle)):
            return None
        return x, y, angle

    def _coordinate_candidates(self, state):
        result = {}
        if not isinstance(state, dict):
            return result

        robot = self._pose_from_dict(state.get("robot"))
        if robot:
            # Si está cargando, esta posición es la referencia física exacta de
            # la base. Si no hay origen todavía durante el mapeo, la primera
            # muestra también sirve como origen local.
            origin_hint = robot if (self._charging_confirmed or self.mapping_phase == 1) else None
            result["robot"] = (robot, origin_hint)

        path = state.get("path") or []
        if path:
            first = self._pose_from_dict(path[0], angle_key="phi")
            last = self._pose_from_dict(path[-1], angle_key="phi")
            if first and last:
                # La trayectoria trae su propio inicio. Lo usamos como origen,
                # así aunque esté en otra referencia absoluta coincide con 0,0.
                result["path"] = (last, first)

        return result

    def _localize_candidate(self, source, pose, origin_hint):
        origin = self._coord_origins.get(source)
        if origin is None:
            if origin_hint is None:
                # No mostramos una posición absoluta sin referencia: es mejor
                # esperar una muestra válida que dibujar un salto falso.
                return None
            origin = (float(origin_hint[0]), float(origin_hint[1]))
            self._coord_origins[source] = origin

        return (
            float(pose[0]) - origin[0],
            float(pose[1]) - origin[1],
            float(pose[2]),
        )

    def _select_live_pose(self, state):
        now = time.monotonic()
        candidates = self._coordinate_candidates(state)
        localized = {}
        movement = {}

        for source, (pose, origin_hint) in candidates.items():
            local = self._localize_candidate(source, pose, origin_hint)
            if local is None:
                continue
            localized[source] = local
            prev = self._coord_prev_local.get(source)
            if prev is None:
                delta = 0.0
            else:
                delta = math.hypot(local[0] - prev[0], local[1] - prev[1])
            movement[source] = delta
            if delta > 1e-9:
                self._coord_last_change[source] = now
                self._coord_stream_changes += 1
            self._coord_prev_local[source] = local

        if not localized:
            return None

        active = self._coord_active_source
        chosen = None

        # current_path es la fuente preferida cuando realmente avanza, porque
        # representa exactamente la trayectoria. Si queda congelada, usamos la
        # posición instantánea del robot sin esperar a que se cierre el path.
        if "path" in localized and movement.get("path", 0.0) > 1e-9:
            chosen = "path"
        elif "robot" in localized and movement.get("robot", 0.0) > 1e-9:
            chosen = "robot"
        elif active in localized:
            chosen = active
        elif "robot" in localized:
            chosen = "robot"
        else:
            chosen = next(iter(localized))

        point = localized[chosen]

        # Filtro de teletransportes: si una propiedad cambia de referencia de
        # golpe, ignoramos esa muestra en vez de ampliar el mapa cientos de veces.
        if self._coord_global_last is not None:
            jump = math.hypot(
                point[0] - self._coord_global_last[0],
                point[1] - self._coord_global_last[1],
            )
            positive = [d for d in self._coord_motion_history if d > 1e-9]
            if len(positive) >= 5:
                ordered = sorted(positive)
                typical = ordered[len(ordered) // 2]
                if typical > 0 and jump > typical * 18.0:
                    # Probamos la otra fuente antes de descartar la muestra.
                    alternate = "robot" if chosen == "path" else "path"
                    alt = localized.get(alternate)
                    if alt is not None:
                        alt_jump = math.hypot(
                            alt[0] - self._coord_global_last[0],
                            alt[1] - self._coord_global_last[1],
                        )
                        if alt_jump <= typical * 18.0:
                            chosen = alternate
                            point = alt
                            jump = alt_jump
                        else:
                            return None
                    else:
                        return None
            if jump > 1e-9:
                self._coord_motion_history.append(jump)
                self._coord_motion_history = self._coord_motion_history[-24:]

        self._coord_active_source = chosen
        self._coord_global_last = point
        return {
            "x": point[0],
            "y": point[1],
            "angle": point[2],
            "source": chosen,
        }

    def _stable_base_pose(self, live_pose):
        if self._charging_confirmed and live_pose:
            return {
                "x": float(live_pose["x"]),
                "y": float(live_pose["y"]),
                "angle": float(live_pose.get("angle", 0) or 0),
            }

        if self.local_map:
            current = self.local_map.snapshot().get("charging_base")
            if current:
                return current

        # Al iniciar desde la base, el origen relativo es siempre 0,0.
        if self._coord_origins:
            return {"x": 0.0, "y": 0.0, "angle": 0.0}
        return None

    def _append_live_mapping_sample(self, pose):
        if not self.mapping_active or not pose:
            return
        phase = int(self.mapping_phase or 0)
        if phase not in (1, 2):
            return
        if phase == 2 and self.mapping_transitioning:
            return

        current = (float(pose["x"]), float(pose["y"]), float(pose.get("angle", 0) or 0))
        previous = self._live_last_point.get(phase)
        if previous is not None:
            distance = math.hypot(current[0] - previous[0], current[1] - previous[1])
            if distance <= 1e-9:
                return

        self._live_point_id[phase] = int(self._live_point_id.get(phase, 0)) + 1
        point_id = self._live_point_id[phase]
        self.local_map.merge_trajectory(
            [{
                "id": point_id,
                "x": current[0],
                "y": current[1],
                "phi": current[2],
                "update": 1,
            }],
            phase=phase,
        )
        self._live_last_point[phase] = current

    def _apply_map_state(self, state):
        # Elegimos una posición continua y relativa. Durante el mapeo, el mapa se
        # construye muestra a muestra desde esa posición, no esperando a que el
        # firmware entregue una trayectoria completa.
        live_pose = self._select_live_pose(state)
        self._append_live_mapping_sample(live_pose)

        normalized = dict(state or {})
        normalized["path"] = []  # evita mezclar coordenadas absolutas con las relativas
        normalized["robot"] = (
            {"x": live_pose["x"], "y": live_pose["y"], "angle": live_pose.get("angle", 0)}
            if live_pose else None
        )
        normalized["charging_base"] = self._stable_base_pose(live_pose)

        result = super()._apply_map_state(normalized)

        if self.mapping_active and hasattr(self, "map_status_label"):
            source = live_pose.get("source", "coordenadas") if live_pose else "esperando coordenadas"
            points = self.local_map.snapshot().get("points", []) if self.local_map else []
            wall_points = sum(1 for p in points if int(p.get("phase", 0) or 0) == 1)
            self.map_status_label.configure(
                text=f"Paredes en vivo · {wall_points} muestras · fuente: {source}",
                fg=app_v15.app_v14.GREEN,
            )
        return result

    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        # ~4 actualizaciones/s durante mapeo para que la pared se vea crecer.
        delay = 250 if self.mapping_active else (650 if self._last_robot_status in (3, 5, 6, 7) else 2200)
        self.after(delay, self._poll_local_map)

    # ----------------------------------------------------- sesión de mapeo
    def start_new_mapping(self):
        self._live_point_id = {1: 0, 2: 0}
        self._live_last_point = {1: None, 2: None}
        self._coord_motion_history = []
        self._coord_stream_changes = 0
        self._mapping_started_at = time.monotonic()

        # current_path pertenece a cada recorrido, por lo que su origen se
        # reinicia. El origen del robot se conserva si ya fue calibrado cargando.
        self._coord_origins.pop("path", None)
        self._coord_prev_local.pop("path", None)
        self._coord_last_change.pop("path", None)
        if not self._charging_confirmed:
            self._coord_origins.pop("robot", None)
        self._coord_active_source = None
        self._coord_global_last = None
        return super().start_new_mapping()

    # ------------------------------------------ EDGE continuo, sin rearmados
    def _watch_edge_only(self, session):
        vacuum = self.vacuum
        if not vacuum:
            return

        deadline = time.monotonic() + 45 * 60
        seen_edge = False
        seen_moving = False
        non_edge_since = None
        errors = 0
        last_state = None

        while time.monotonic() < deadline:
            if session != self._edge_session or self.mapping_phase != 1:
                return
            vacuum = self.vacuum
            if not vacuum:
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status = int(values.get("status", -1) if values.get("status") is not None else -1)
                sweep_type = int(values.get("sweep_type", -1) if values.get("sweep_type") is not None else -1)
                errors = 0
            except Exception as exc:
                errors += 1
                if errors >= 16:
                    self._edge_log(f"Telemetría EDGE perdida: {exc}")
                    self._post_ui(
                        "edge_only_error",
                        "Perdí la comunicación durante el recorrido de borde. Detuve el Paso 1 por seguridad.",
                    )
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    return
                time.sleep(0.28)
                continue

            state = (status, sweep_type)
            if state != last_state:
                self._edge_log(f"EDGE continuo: status={status} sweep_type={sweep_type}")
                last_state = state

            moving = status in (5, 6, 7)
            if moving and sweep_type == 2:
                seen_edge = True
                seen_moving = True
                non_edge_since = None

            # Si el robot comienza a volver a la base, el perímetro terminó. Lo
            # marcamos antes de registrar ese trayecto de regreso como una pared.
            if seen_edge and seen_moving and status in (0, 1, 2, 3, 4):
                self._post_ui(
                    "edge_only_complete",
                    "Paso 1 terminado · perímetro completo guardado. Volviendo a la base para continuar con Paso 2.",
                )
                return

            # Algunos firmwares muestran un 0 transitorio. No frenamos por una
            # sola lectura: exigimos que dure >1,1 s antes de considerar que está
            # intentando entrar realmente en limpieza global.
            if seen_edge and seen_moving and moving and sweep_type != 2:
                if non_edge_since is None:
                    non_edge_since = time.monotonic()
                elif time.monotonic() - non_edge_since >= 1.1:
                    self._edge_log(
                        f"Transición global persistente: status={status} sweep_type={sweep_type}. STOP."
                    )
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    self._post_ui(
                        "edge_only_complete",
                        "Paso 1 terminado · bloqueé una transición persistente a limpieza global.",
                    )
                    return
            else:
                non_edge_since = None

            # Si en 10 s nunca confirmó EDGE, no dejamos una limpieza distinta
            # corriendo silenciosamente.
            if time.monotonic() - self._mapping_started_at > 10.0 and not seen_edge:
                try:
                    vacuum.stop()
                except Exception:
                    pass
                self._post_ui(
                    "edge_only_error",
                    f"El E10 no confirmó EDGE continuo (sweep_type={sweep_type}). Cancelé el recorrido.",
                )
                return

            time.sleep(0.28)

        try:
            vacuum.stop()
        except Exception:
            pass
        self._post_ui("edge_only_error", "El recorrido de perímetro superó el tiempo máximo y fue detenido.")

    # ---------------------------------------------------------- antibloqueo
    def _anti_stall_observe(self, state):
        # Durante el mapeo NO usamos control remoto automático: era lo que
        # provocaba el pitido, el giro y el reinicio del modo EDGE. El E10 conserva
        # su navegación/evitación de obstáculos nativa sin interrupciones.
        if self.mapping_active:
            self._anti_stall_last_pose = None
            self._anti_stall_last_motion_at = time.monotonic()
            self._anti_stall_attempts = 0
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(
                    text="Antibloqueo · navegación nativa (sin interrumpir EDGE)",
                    fg=app_v15.app_v14.GREEN,
                )
            return

        # Fuera del mapeo sólo habilitamos maniobras automáticas después de
        # comprobar que recibimos una secuencia real de posiciones cambiantes.
        # Así una propiedad congelada no se interpreta como un atasco físico.
        if self._coord_stream_changes < 5:
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(
                    text="Antibloqueo · calibrando coordenadas",
                    fg=app_v15.app_v14.MUTED,
                )
            return
        return super()._anti_stall_observe(state)


if __name__ == "__main__":
    app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

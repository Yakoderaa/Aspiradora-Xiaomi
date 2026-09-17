import math

import app_v33


class App(app_v33.App):
    """v34: posición fija honesta, sin paredes fantasma y robot siempre visible."""

    MOTION_EPSILON = 0.015
    MIN_WALL_POINTS = 3
    LIVE_POINT_ID_BASE = 100000

    def __init__(self):
        self._v34_last_relative = None
        self._v34_motion_confirmed = False
        self._v34_position_changes = 0
        self._v34_point_id = self.LIVE_POINT_ID_BASE
        super().__init__()

    # ------------------------------------------------ sesión / movimiento real
    def start_new_mapping(self):
        result = super().start_new_mapping()
        if getattr(self, "mapping_active", False) and int(getattr(self, "mapping_phase", 0) or 0) == 1:
            self._v34_last_relative = None
            self._v34_motion_confirmed = False
            self._v34_position_changes = 0
            self._v34_point_id = self.LIVE_POINT_ID_BASE
            try:
                self.local_map.set_mapped_walls([])
            except Exception:
                pass
            self._render_maps()
        return result

    @staticmethod
    def _xy_distance(a, b):
        if a is None or b is None:
            return 0.0
        try:
            return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
        except Exception:
            return 0.0

    @classmethod
    def _path_has_real_motion(cls, path):
        previous = None
        for point in path or []:
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if previous is not None and cls._xy_distance(previous, current) >= cls.MOTION_EPSILON:
                return True
            previous = current
        return False

    def _record_relative_motion(self, relative):
        """Guarda trayectoria sólo cuando X/Y cambian de verdad.

        La primera lectura (por ejemplo -1,0) sólo ubica el robot. No es una pared
        ni un recorrido. Recién al recibir una segunda coordenada distinta
        comenzamos la polilínea, incluyendo la muestra anterior como inicio.
        """
        if not self.mapping_active or not self.local_map:
            self._v34_last_relative = (
                float(relative["x"]),
                float(relative["y"]),
                float(relative.get("angle", 0) or 0),
            )
            return 0

        phase = int(self.mapping_phase or 0)
        if phase not in (1, 2) or (phase == 2 and self.mapping_transitioning):
            return 0

        current = (
            float(relative["x"]),
            float(relative["y"]),
            float(relative.get("angle", 0) or 0),
        )
        previous = self._v34_last_relative
        self._v34_last_relative = current
        if previous is None:
            return 0

        distance = self._xy_distance(previous, current)
        if distance < self.MOTION_EPSILON:
            return 0

        self._v34_motion_confirmed = True
        self._v34_position_changes += 1
        samples = []

        # En el primer cambio real agregamos también la pose anterior, para que
        # el recorrido comience donde realmente empezó a cambiar la telemetría.
        if self._v34_position_changes == 1:
            self._v34_point_id += 1
            samples.append({
                "id": self._v34_point_id,
                "x": previous[0],
                "y": previous[1],
                "phi": previous[2],
                "update": 1,
            })

        self._v34_point_id += 1
        samples.append({
            "id": self._v34_point_id,
            "x": current[0],
            "y": current[1],
            "phi": current[2],
            "update": 1,
        })
        return self.local_map.merge_trajectory(samples, phase=phase)

    # ------------------------------------------------ paredes: no inventar
    @classmethod
    def _distinct_wall_points(cls, points):
        distinct = []
        for point in points or []:
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if not distinct or cls._xy_distance(distinct[-1], current) >= cls.MOTION_EPSILON:
                distinct.append(current)
        return distinct

    def _rebuild_mapped_walls(self, force=False):
        if not self.local_map:
            return False
        snapshot = self.local_map.snapshot()
        perimeter = [
            point for point in snapshot.get("points", []) or []
            if int(point.get("phase", 0) or 0) == 1
        ]
        distinct = self._distinct_wall_points(perimeter)

        # Dos puntos sólo forman una línea; no alcanzan para afirmar que existe
        # una pared. Esto elimina el segmento base<->robot que aparecía en v33.
        if not self._v34_motion_confirmed or len(distinct) < self.MIN_WALL_POINTS:
            if snapshot.get("mapped_walls"):
                self.local_map.set_mapped_walls([])
            self._mapped_wall_source_count = len(perimeter)
            return False

        return super()._rebuild_mapped_walls(force=force)

    # ------------------------------------------------ estado -> mapa
    def _apply_map_state(self, state):
        original = dict(state or {})
        real_path = list(original.get("path") or [])
        relative = self._relative_robot_from_state(original)

        if real_path:
            if self._path_has_real_motion(real_path):
                self._v34_motion_confirmed = True
            return super()._apply_map_state(original)

        if relative is None:
            return super()._apply_map_state(original)

        # No dejamos que las capas antiguas vuelvan a reinterpretar esta pose ni
        # que la primera lectura fija se convierta en un punto de trayectoria.
        forwarded = dict(original)
        forwarded["robot"] = None
        forwarded["charging_base"] = None

        # Saltamos únicamente app_v33._apply_map_state. Conservamos diagnóstico,
        # watchdog, actualización visual y demás capas anteriores.
        result = super(app_v33.App, self)._apply_map_state(forwarded)

        if self.local_map:
            self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
            self.local_map.set_robot(relative)
            self._record_relative_motion(relative)
            if self.mapping_active and int(self.mapping_phase or 0) == 1:
                self._rebuild_mapped_walls(force=False)
            self._render_maps()

        if self.mapping_active:
            stale = bool(original.get("position_stale"))
            status = "Posición MIoT fija" if stale else "Posición MIoT"
            try:
                self.map_status_label.configure(
                    text=(
                        f"{status} · X {relative['x']:+.3f} m · Y {relative['y']:+.3f} m "
                        f"· φ {relative['angle']:.3f} · cambios reales {self._v34_position_changes}"
                    )
                )
            except Exception:
                pass
            try:
                if self._v34_motion_confirmed:
                    self.mapping_steps_info.configure(
                        text="Movimiento confirmado · construyendo trayectoria y paredes sólo con posiciones reales"
                    )
                else:
                    self.mapping_steps_info.configure(
                        text="Sin trayectoria en vivo del firmware · no se estiman paredes hasta detectar movimiento real"
                    )
            except Exception:
                pass
        return result

    # ------------------------------------------------ render: robot arriba
    def _render_map_canvas(self, canvas, snapshot):
        source = dict(snapshot or {})

        # Durante un Paso 1 todavía sin movimiento confirmado ocultamos cualquier
        # resto de trayectoria/pared heredado. Base y robot sí siguen visibles.
        if self.mapping_active and int(self.mapping_phase or 0) == 1 and not self._v34_motion_confirmed:
            source["points"] = []
            source["mapped_walls"] = []

        result = super()._render_map_canvas(canvas, source)
        transform = self._map_transforms.get(canvas)
        robot = source.get("robot")
        base = source.get("charging_base")
        if not transform or not isinstance(robot, dict):
            return result

        scale = float(transform["scale"])
        min_x = float(transform["min_x"])
        max_y = float(transform["max_y"])
        pad = float(transform["pad"])
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)

        if canvas is getattr(self, "home_map_canvas", None):
            try:
                hx, hy = self._home_map_pan
                pan_x += float(hx)
                pan_y += float(hy)
            except Exception:
                pass

        def to_screen(point):
            return (
                pad + (float(point["x"]) - min_x) * scale + pan_x,
                pad + (max_y - float(point["y"])) * scale + pan_y,
            )

        # Reponemos la base primero y el robot último. Así ninguna pared, zona o
        # leyenda puede tapar el indicador de posición.
        if isinstance(base, dict):
            bx, by = to_screen(base)
            canvas.create_rectangle(
                bx - 8, by - 8, bx + 8, by + 8,
                fill="#30343a", outline="white", width=2,
                tags=("pose_v34", "base_v34"),
            )
            if canvas is getattr(self, "map_canvas", None):
                canvas.create_text(
                    bx, by - 17, text="Base", fill="#64748b",
                    font=("Segoe UI", 7, "bold"), tags=("pose_v34",),
                )

        rx, ry = to_screen(robot)
        radius = 11
        canvas.create_oval(
            rx - radius, ry - radius, rx + radius, ry + radius,
            fill="#ff6900", outline="white", width=3,
            tags=("pose_v34", "robot_v34"),
        )
        try:
            angle = float(robot.get("angle", 0) or 0)
            hx = rx + math.cos(angle) * 15
            hy = ry - math.sin(angle) * 15
            canvas.create_line(
                rx, ry, hx, hy, fill="white", width=2,
                arrow="last", arrowshape=(5, 6, 3), tags=("pose_v34", "robot_v34"),
            )
        except Exception:
            pass
        if canvas is getattr(self, "map_canvas", None):
            canvas.create_text(
                rx, ry - 20, text="Robot", fill="#ff6900",
                font=("Segoe UI", 8, "bold"), tags=("pose_v34", "robot_v34"),
            )
        try:
            canvas.tag_raise("pose_v34")
            canvas.tag_raise("robot_v34")
        except Exception:
            pass
        return result

    # ------------------------------------------------ diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V34 ACTIVO · render seguro\n"
            "=============================================\n"
            f"movimiento X/Y confirmado: {self._v34_motion_confirmed}\n"
            f"cambios reales registrados: {self._v34_position_changes}\n"
            "paredes: bloqueadas hasta 3 posiciones distintas\n"
            "robot: se dibuja en la capa superior\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

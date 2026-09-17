import math

import app_v34


class App(app_v34.App):
    """v35: no usa el delta fijo 10/24-10/22 como desplazamiento real.

    Mientras no exista movimiento X/Y confirmado, la posición visual del robot
    permanece sobre la base. El delta MIoT crudo sigue disponible en Diagnóstico,
    pero no se convierte en geometría ni en desplazamiento visual.
    """

    def __init__(self):
        self._v35_raw_relative = None
        super().__init__()

    def _apply_map_state(self, state):
        original = dict(state or {})
        self._v35_raw_relative = self._relative_robot_from_state(original)

        result = super()._apply_map_state(original)

        # Un valor fijo como 10/24=59_60 y 10/22=60_60 no demuestra que el robot
        # se haya desplazado un metro. Hasta observar un cambio X/Y real, robot y
        # base deben seguir coincidiendo visualmente en el origen.
        if (
            self.local_map
            and self.mapping_active
            and not bool(getattr(self, "_v34_motion_confirmed", False))
        ):
            self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
            angle = 0.0
            if isinstance(self._v35_raw_relative, dict):
                try:
                    angle = float(self._v35_raw_relative.get("angle", 0.0) or 0.0)
                except Exception:
                    angle = 0.0
            self.local_map.set_robot({"x": 0.0, "y": 0.0, "angle": angle})
            self._render_maps()

            try:
                raw = self._v35_raw_relative or {}
                self.map_status_label.configure(
                    text=(
                        "Sin movimiento confirmado · posición visual X +0.000 m · Y +0.000 m "
                        f"· delta MIoT crudo X {float(raw.get('x', 0.0)):+.3f} · Y {float(raw.get('y', 0.0)):+.3f}"
                    )
                )
            except Exception:
                pass
        return result

    def _render_map_canvas(self, canvas, snapshot):
        source = dict(snapshot or {})

        # Garantía adicional de render: si aún no existe movimiento real, el
        # robot debe dibujarse exactamente sobre la base, aunque haya quedado
        # una pose vieja persistida en el snapshot.
        if (
            self.mapping_active
            and not bool(getattr(self, "_v34_motion_confirmed", False))
            and isinstance(source.get("charging_base"), dict)
        ):
            base = dict(source["charging_base"])
            robot = dict(source.get("robot") or {})
            source["robot"] = {
                "x": float(base.get("x", 0.0)),
                "y": float(base.get("y", 0.0)),
                "angle": float(robot.get("angle", 0.0) or 0.0),
            }

        # Saltamos sólo el renderer de v34, que redibujaba base + rótulo Base.
        # Ejecutamos toda la cadena anterior para conservar mapa, zonas, paredes,
        # base y robot estándar.
        result = super(app_v34.App, self)._render_map_canvas(canvas, source)

        # Las capas modernas posteriores pueden dibujar paredes sobre el robot.
        # Redibujamos únicamente el robot al final; la base NO se vuelve a crear.
        transform = self._map_transforms.get(canvas)
        robot = source.get("robot")
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

        rx = pad + (float(robot["x"]) - min_x) * scale + pan_x
        ry = pad + (max_y - float(robot["y"])) * scale + pan_y
        radius = 11
        canvas.create_oval(
            rx - radius, ry - radius, rx + radius, ry + radius,
            fill="#ff6900", outline="white", width=3,
            tags=("robot_v35",),
        )
        try:
            angle = float(robot.get("angle", 0) or 0)
            hx = rx + math.cos(angle) * 15
            hy = ry - math.sin(angle) * 15
            canvas.create_line(
                rx, ry, hx, hy, fill="white", width=2,
                arrow="last", arrowshape=(5, 6, 3), tags=("robot_v35",),
            )
        except Exception:
            pass
        try:
            canvas.tag_raise("robot_v35")
        except Exception:
            pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        raw = self._v35_raw_relative or {}
        try:
            dx = float(raw.get("x", 0.0))
            dy = float(raw.get("y", 0.0))
            delta = f"X {dx:+.6f} · Y {dy:+.6f}"
        except Exception:
            delta = "—"
        return (
            "DIAGNÓSTICO V35 ACTIVO · origen visual seguro\n"
            "=============================================\n"
            f"delta MIoT crudo: {delta}\n"
            f"movimiento confirmado: {bool(getattr(self, '_v34_motion_confirmed', False))}\n"
            "regla visual: sin movimiento confirmado, robot = base = (0,0)\n"
            "base: una sola capa / un solo rótulo\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

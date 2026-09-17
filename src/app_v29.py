import time

import app_v28


class App(app_v28.App):
    """v29: trayectoria pegajosa + coordenadas estables y movimiento continuo."""

    LIVE_MAP_POLL_MS = 220

    def __init__(self):
        self._live_ui_last_pose = None
        self._live_ui_last_pose_at = 0.0
        super().__init__()

    # ------------------------------------------------ trayectoria por sesión
    def _reset_robot_live_path(self):
        vacuum = getattr(self, "vacuum", None)
        reset = getattr(vacuum, "reset_live_path_session", None) if vacuum else None
        if callable(reset):
            try:
                reset()
            except Exception:
                pass
        self._live_ui_last_pose = None
        self._live_ui_last_pose_at = 0.0

    def start_new_mapping(self):
        self._reset_robot_live_path()
        return super().start_new_mapping()

    def start_interior_mapping(self):
        # El Paso 2 es un recorrido MIoT nuevo y puede reiniciar sus pose-id. No
        # mezclamos la caché cruda del Paso 1 con la del interior.
        self._reset_robot_live_path()
        return super().start_interior_mapping()

    def start_clean(self):
        self._reset_robot_live_path()
        return super().start_clean()

    # ------------------------------------------------ sondeo realmente fluido
    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        if self.mapping_active or self._last_robot_status in (3, 5, 6, 7):
            delay = self.LIVE_MAP_POLL_MS
        else:
            delay = 1500
        self.after(delay, self._poll_local_map)

    # ------------------------------------------------ UI estable / coordenadas
    @staticmethod
    def _format_coord(value):
        try:
            return f"{float(value):+.3f}"
        except Exception:
            return "—"

    @staticmethod
    def _format_phi(value):
        try:
            return f"{float(value):.3f}"
        except Exception:
            return "—"

    def _stable_map_status(self, state):
        if not self.local_map:
            return

        snapshot = self.local_map.snapshot()
        robot = snapshot.get("robot") if isinstance(snapshot, dict) else None
        points = snapshot.get("points", []) if isinstance(snapshot, dict) else []
        phase = int(self.mapping_phase or 0)

        if isinstance(robot, dict) and "x" in robot and "y" in robot:
            self._live_ui_last_pose = dict(robot)
            self._live_ui_last_pose_at = time.monotonic()
        elif self._live_ui_last_pose is not None:
            robot = dict(self._live_ui_last_pose)

        if phase == 1:
            phase_text = "PASO 1 · PERÍMETRO"
            point_count = sum(1 for p in points if int(p.get("phase", 0) or 0) == 1)
        elif phase == 2:
            phase_text = "PASO 2 · INTERIOR"
            point_count = sum(1 for p in points if int(p.get("phase", 0) or 0) == 2)
        else:
            phase_text = "MAPA"
            point_count = len(points)

        source = str((state or {}).get("position_source") or (state or {}).get("path_source") or "telemetría")
        accumulated = int((state or {}).get("accumulated_path_count", 0) or 0)
        new_count = int((state or {}).get("new_path_count", 0) or 0)

        if robot:
            text = (
                f"{phase_text} · EN VIVO  |  "
                f"X {self._format_coord(robot.get('x'))} m  ·  "
                f"Y {self._format_coord(robot.get('y'))} m  ·  "
                f"φ {self._format_phi(robot.get('angle'))}  |  "
                f"{point_count} puntos · fuente: {source}"
            )
        else:
            text = f"{phase_text} · esperando la primera coordenada de trayectoria 10/5…"

        try:
            self.map_status_label.configure(text=text, fg=app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.GREEN)
        except Exception:
            pass

        # Este segundo indicador ya no muestra mensajes que compitan con el
        # estado principal. Sólo informa ritmo y acumulación de trayectoria.
        if hasattr(self, "live_map_label"):
            try:
                if self.mapping_active:
                    self.live_map_label.configure(
                        text=f"● LIVE · {accumulated} poses MIoT · +{new_count} · ~{self.LIVE_MAP_POLL_MS / 1000:.2f} s",
                        fg=app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.GREEN,
                    )
                else:
                    self.live_map_label.configure(text="")
            except Exception:
                pass

        # El texto auxiliar queda fijo por fase. Evitamos mostrar el rango de
        # sondeo 10/12, que era el texto que parecía parpadear frame a frame.
        if hasattr(self, "mapping_steps_info") and self.mapping_active:
            try:
                self.mapping_steps_info.configure(
                    text=(
                        "Trayectoria acumulada 10/5 · 10/12 sólo como respaldo · coordenadas relativas a la base"
                    )
                )
            except Exception:
                pass

    def _apply_map_state(self, state):
        # Toda la cadena heredada sigue construyendo paredes, zonas y la posición
        # localizada. Al final imponemos una única representación visible para
        # que ningún texto intermedio aparezca como un frame alternativo.
        result = super()._apply_map_state(state)
        self._stable_map_status(state)
        return result

    def _render_maps(self):
        result = super()._render_maps()
        # _render_maps heredado escribe textos genéricos. Si ya tenemos la última
        # muestra, restauramos inmediatamente el estado estable de v29.
        if self.mapping_active and self._live_ui_last_pose is not None:
            snapshot = self.local_map.snapshot() if self.local_map else {}
            robot = snapshot.get("robot") if isinstance(snapshot, dict) else None
            if robot:
                phase = int(self.mapping_phase or 0)
                phase_text = "PASO 1 · PERÍMETRO" if phase == 1 else "PASO 2 · INTERIOR"
                points = snapshot.get("points", []) or []
                count = sum(1 for p in points if int(p.get("phase", 0) or 0) == phase)
                try:
                    self.map_status_label.configure(
                        text=(
                            f"{phase_text} · EN VIVO  |  "
                            f"X {self._format_coord(robot.get('x'))} m  ·  "
                            f"Y {self._format_coord(robot.get('y'))} m  ·  "
                            f"φ {self._format_phi(robot.get('angle'))}  |  {count} puntos"
                        ),
                        fg=app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.GREEN,
                    )
                except Exception:
                    pass
        return result


if __name__ == "__main__":
    app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

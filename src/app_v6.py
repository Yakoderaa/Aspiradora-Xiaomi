import math
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v5

APP_BG = app_v5.APP_BG
CARD = app_v5.CARD
TEXT = app_v5.TEXT
MUTED = app_v5.MUTED
ACCENT = app_v5.ACCENT
BLUE = app_v5.BLUE
GREEN = app_v5.GREEN
RED = app_v5.RED
MAP_PATH = app_v5.MAP_PATH


class App(app_v5.App):
    """Interfaz v6: mapeo por perímetro + interior con dibujo en vivo."""

    def __init__(self):
        self.mapping_phase = 0  # 0 ninguno, 1 perímetro, 2 interior
        self.mapping_transitioning = False
        self.map_last_update = 0.0
        super().__init__()

    def _build_map_page(self):
        super()._build_map_page()
        tools = self.map_status_label.master
        self.live_map_label = tk.Label(
            tools,
            text="",
            bg=CARD,
            fg=GREEN,
            font=("Segoe UI", 8, "bold"),
        )
        self.live_map_label.pack(side="left", padx=(12, 0))

    # ------------------------------------------------------- mapeo en vivo
    def _poll_local_map(self):
        if not self.vacuum:
            self.map_polling = False
            return

        def worker():
            try:
                state = self.vacuum.local_map_state()
                if self.local_map:
                    path = state.get("path") or []
                    # Durante el cambio entre fases esperamos a que el E10 empiece
                    # realmente la segunda pasada para no duplicar la trayectoria vieja.
                    if self.mapping_active and path and not (
                        self.mapping_phase == 2 and self.mapping_transitioning
                    ):
                        self.local_map.merge_trajectory(path, phase=self.mapping_phase)
                    self.local_map.set_robot(state.get("robot"))
                    self.local_map.set_charging_base(state.get("charging_base"))
                    self.map_last_update = time.time()
                    self.after(0, self._render_maps)
            except Exception as exc:
                text = f"Telemetría de mapa: {str(exc)[:90]}"
                self.after(
                    0,
                    lambda: self.map_status_label.configure(text=text, fg=RED)
                    if hasattr(self, "map_status_label")
                    else None,
                )
            finally:
                try:
                    if self.winfo_exists() and self.vacuum:
                        # En mapeo se redibuja aproximadamente una vez por segundo.
                        delay = 700 if self.mapping_active else 2200
                        self.after(delay, self._poll_local_map)
                    else:
                        self.map_polling = False
                except tk.TclError:
                    self.map_polling = False

        threading.Thread(target=worker, daemon=True).start()

    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.")
            return
        ok = messagebox.askyesno(
            "Crear mapa desde cero",
            "El mapa local de la PC se va a borrar y se creará de nuevo en dos fases:\n\n"
            "1. PERÍMETRO: el E10 usa su modo real de limpieza de bordes para seguir paredes y límites.\n"
            "2. INTERIOR: al terminar el perímetro, empieza automáticamente una segunda pasada global para completar el piso.\n\n"
            "El gráfico se actualiza en tiempo real mientras se mueve. No se descarga el mapa de Mi Home.",
            parent=self,
        )
        if not ok:
            return

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 1
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.show_page("map")
        self._render_maps()
        self._set_banner("Mapeo 1/2 · recorriendo el perímetro en tiempo real…")

        def worker():
            try:
                self.vacuum.start_mapping_perimeter()
            except Exception as exc:
                msg = str(exc).strip() or "El E10 rechazó el modo de perímetro."
                self.mapping_active = False
                self.mapping_phase = 0
                self.after(0, lambda: messagebox.showerror("No se pudo mapear", msg, parent=self))
                self.after(0, self._render_maps)

        threading.Thread(target=worker, daemon=True).start()

    def _start_interior_phase(self):
        if not self.vacuum or not self.mapping_active:
            return
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = True
        self._set_banner("Mapeo 2/2 · perímetro terminado; iniciando recorrido interior…")
        self._render_maps()

        def worker():
            try:
                # Pequeña pausa para que el firmware cierre por completo la tarea edge.
                time.sleep(1.2)
                if not self.mapping_active:
                    return
                self.vacuum.start_mapping_interior()
            except Exception as exc:
                msg = str(exc).strip() or "El E10 rechazó la segunda fase de mapeo."
                self.mapping_active = False
                self.mapping_phase = 0
                self.mapping_transitioning = False
                self.after(0, lambda: messagebox.showerror("No se pudo completar el mapa", msg, parent=self))
                self.after(0, self._render_maps)

        threading.Thread(target=worker, daemon=True).start()

    def finish_mapping(self):
        if not self.mapping_active:
            self._set_banner("El mapa local ya está guardado en esta PC.")
            return
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self._render_maps()
        if self.vacuum:
            self._run_command("Finalizando recorrido de mapeo…", self.vacuum.stop)

    def _restore_cleaning_preferences(self):
        if not self.vacuum:
            return
        try:
            suction = max(1, min(4, int(self.settings.get("suction", 2) or 2)))
            mop = bool(self.settings.get("mop_enabled", False))
            water = max(1, min(3, int(self.settings.get("mop_water_level", 1) or 1))) if mop else 0
            self.vacuum.set_suction(suction)
            self.vacuum.set_water(water)
            self.vacuum.set_mode(1 if mop else 0)
        except Exception:
            pass

    # ------------------------------------------------------- estado/fases
    def _render_status(self, s):
        self.status_value.configure(text=s.status_name)
        self.battery_value.configure(text=f"{s.battery}%")
        self.battery_header.configure(text=f"Batería {s.battery}%")
        self.area_value.configure(text=f"{s.cleaning_area} m²")
        self.time_value.configure(text=f"{s.cleaning_time} min")
        self.mode_info.configure(text=s.mode_name)
        self.deposit_info.configure(text=s.door_name)
        self.mop_info.configure(text=s.cloth_name)
        self.fault_info.configure(
            text="Sin errores" if s.fault == 0 else f"Código {s.fault}",
            fg=TEXT if s.fault == 0 else RED,
        )

        for widget, remaining in [
            (self.side_brush_info, s.side_brush_life),
            (self.main_brush_info, s.main_brush_life),
            (self.hepa_info, s.hepa_life),
            (self.mop_life_info, s.mop_life),
        ]:
            label, bar = widget
            label.configure(text=f"{remaining}%")
            bar["value"] = remaining

        moving = s.status in (5, 6, 7)
        finished = s.status in (1, 4)

        if self.mapping_active and moving:
            self.mapping_seen_moving = True
            if self.mapping_phase == 2 and self.mapping_transitioning:
                # Ya arrancó una trayectoria nueva: a partir de ahora la guardamos
                # como fase interior, separada de los IDs del perímetro.
                self.mapping_transitioning = False
                self._set_banner("Mapeo 2/2 · completando el interior en tiempo real…")

        if self.mapping_active and self.mapping_seen_moving and finished:
            if self.mapping_phase == 1 and not self.mapping_transitioning:
                self.mapping_transitioning = True
                self.mapping_seen_moving = False
                self._start_interior_phase()
            elif self.mapping_phase == 2 and not self.mapping_transitioning:
                self.mapping_active = False
                self.mapping_phase = 0
                self.mapping_seen_moving = False
                self._set_banner("Mapeo terminado · perímetro e interior guardados en esta PC.")
                self._render_maps()
                threading.Thread(target=self._restore_cleaning_preferences, daemon=True).start()

        if not self.mapping_active:
            if 1 <= int(s.suction or 0) <= 4:
                self.suction_var.set(int(s.suction))
            if 0 <= int(s.water or 0) <= 3:
                self.water_var.set(int(s.water))
            self._refresh_choice_buttons()

        self._set_connection(True, f"Conectado · {self.settings.get('ip', '')}")

    # ------------------------------------------------------- gráfico en vivo
    def _render_maps(self):
        super()._render_maps()
        if not self.local_map:
            return
        snapshot = self.local_map.snapshot()
        points = snapshot.get("points", []) or []
        perimeter = sum(1 for p in points if int(p.get("phase", 0) or 0) == 1)
        interior = sum(1 for p in points if int(p.get("phase", 0) or 0) == 2)

        if self.mapping_active:
            phase_text = "PERÍMETRO · 1/2" if self.mapping_phase == 1 else "INTERIOR · 2/2"
            if hasattr(self, "mapping_badge"):
                self.mapping_badge.configure(text=f"● EN VIVO · {phase_text}", fg=GREEN)
            if hasattr(self, "map_status_label"):
                self.map_status_label.configure(
                    text=f"Mapeando en tiempo real · {phase_text.lower()}",
                    fg=GREEN,
                )
            if hasattr(self, "live_map_label"):
                self.live_map_label.configure(
                    text=f"● LIVE · {len(points)} puntos · ~0,7 s",
                    fg=GREEN,
                )
        else:
            if hasattr(self, "live_map_label"):
                extra = f"Perímetro {perimeter} · Interior {interior}" if (perimeter or interior) else ""
                self.live_map_label.configure(text=extra, fg=MUTED)

    def _render_map_canvas(self, canvas, snapshot):
        # Dibujo base (huella, habitaciones, robot y base).
        super()._render_map_canvas(canvas, snapshot)
        transform = self._map_transforms.get(canvas)
        points = snapshot.get("points", []) or []
        if not transform or not points:
            return

        scale = transform["scale"]
        min_x = transform["min_x"]
        max_y = transform["max_y"]
        pad = transform["pad"]

        def to_screen(x, y):
            return pad + (float(x) - min_x) * scale, pad + (max_y - float(y)) * scale

        # Superponemos las dos fases con colores distintos para que se vea cómo
        # se construye el mapa: naranja = borde, azul = relleno interior.
        for phase, color in ((1, ACCENT), (2, BLUE)):
            phase_points = [p for p in points if int(p.get("phase", 0) or 0) == phase]
            if len(phase_points) < 2:
                continue
            current = [phase_points[0]]
            segments = []
            for point in phase_points[1:]:
                prev = current[-1]
                distance = math.hypot(
                    float(point["x"]) - float(prev["x"]),
                    float(point["y"]) - float(prev["y"]),
                )
                if distance > 1.25:
                    if len(current) > 1:
                        segments.append(current)
                    current = [point]
                else:
                    current.append(point)
            if len(current) > 1:
                segments.append(current)

            for segment in segments:
                coords = []
                for point in segment:
                    coords.extend(to_screen(point["x"], point["y"]))
                if len(coords) >= 4:
                    canvas.create_line(
                        *coords,
                        fill=color,
                        width=3,
                        capstyle=tk.ROUND,
                        joinstyle=tk.ROUND,
                    )

        # Leyenda y pulso visual del robot en la vista principal del mapa.
        if canvas is getattr(self, "map_canvas", None):
            canvas.create_rectangle(12, 12, 210, 42, fill=CARD, outline="#e8eaed")
            canvas.create_line(24, 27, 46, 27, fill=ACCENT, width=3)
            canvas.create_text(52, 27, text="Perímetro", anchor="w", fill=MUTED, font=("Segoe UI", 8, "bold"))
            canvas.create_line(119, 27, 141, 27, fill=BLUE, width=3)
            canvas.create_text(147, 27, text="Interior", anchor="w", fill=MUTED, font=("Segoe UI", 8, "bold"))

            robot = snapshot.get("robot")
            if robot and self.mapping_active:
                x, y = to_screen(robot["x"], robot["y"])
                canvas.create_oval(x - 14, y - 14, x + 14, y + 14, outline=GREEN, width=2)


if __name__ == "__main__":
    App().mainloop()

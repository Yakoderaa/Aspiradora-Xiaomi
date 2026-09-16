import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v7

CARD = app_v7.app_v6.CARD
ACCENT = app_v7.app_v6.ACCENT
MUTED = app_v7.app_v6.MUTED
TEXT = app_v7.app_v6.TEXT
GREEN = app_v7.app_v6.GREEN
RED = app_v7.app_v6.RED


class App(app_v7.App):
    """v8: separa manualmente Paso 1 (perímetro) y Paso 2 (interior)."""

    def __init__(self):
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        super().__init__()
        self.after(150, self._sync_mapping_step_buttons)

    # ------------------------------------------------------------ UI mapeo
    def _build_map_page(self):
        super()._build_map_page()

        page = self._pages.get("map")
        header_parent = None

        def walk(widget):
            nonlocal header_parent
            for child in widget.winfo_children():
                if isinstance(child, tk.Button):
                    try:
                        text = child.cget("text")
                    except tk.TclError:
                        text = ""
                    if text in ("Crear desde cero", "Finalizar"):
                        header_parent = child.master
                        child.destroy()
                walk(child)

        if page:
            walk(page)

        if header_parent is None:
            return

        controls = tk.Frame(header_parent, bg=CARD)
        controls.pack(side="right")

        self.stop_mapping_button = self._button(
            controls,
            "Detener",
            self.finish_mapping,
            compact=True,
        )
        self.stop_mapping_button.pack(side="right", padx=(8, 0))

        self.step2_mapping_button = self._button(
            controls,
            "Paso 2 · Interior",
            self.start_interior_mapping,
            compact=True,
        )
        self.step2_mapping_button.pack(side="right", padx=(8, 0))

        self.step1_mapping_button = self._button(
            controls,
            "Paso 1 · Perímetro",
            self.start_new_mapping,
            accent=True,
            compact=True,
        )
        self.step1_mapping_button.pack(side="right")

        info_parent = self.map_status_label.master
        self.mapping_steps_info = tk.Label(
            info_parent,
            text="Paso 1: borde de habitaciones · Paso 2: completar interior",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.mapping_steps_info.pack(side="left", padx=(12, 0))

    def _has_perimeter_data(self):
        if not self.local_map:
            return False
        points = self.local_map.snapshot().get("points", []) or []
        return any(int(p.get("phase", 0) or 0) == 1 for p in points)

    def _sync_mapping_step_buttons(self):
        if not hasattr(self, "step1_mapping_button"):
            return

        active = bool(self.mapping_active)
        has_perimeter = self.mapping_step1_complete or self._has_perimeter_data()

        self.step1_mapping_button.configure(
            state="disabled" if active else "normal",
            text="Paso 1 · Perímetro" if not self.mapping_step1_complete else "Paso 1 · Rehacer perímetro",
        )
        self.step2_mapping_button.configure(
            state="normal" if (has_perimeter and not active) else "disabled",
            text="Paso 2 · Interior" if not self.mapping_step2_complete else "Paso 2 · Rehacer interior",
        )
        self.stop_mapping_button.configure(state="normal" if active else "disabled")

    # ------------------------------------------------------------ Paso 1
    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if self.mapping_active:
            messagebox.showinfo("Mapeo en curso", "Primero detené el paso actual.", parent=self)
            return

        ok = messagebox.askyesno(
            "Paso 1 · Perímetro",
            "Se va a borrar el mapa local guardado por esta aplicación y empezar desde cero.\n\n"
            "Voy a mandar al E10 el comando real de recorrido de BORDE/PERÍMETRO (edge = 2). "
            "La aspiradora seguirá paredes y límites mientras el gráfico se dibuja en tiempo real.\n\n"
            "El Paso 2 NO arrancará solo: lo iniciás vos cuando quieras.",
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
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 1 · enviando comando EDGE al E10 para recorrer el perímetro…")

        def worker():
            try:
                self.vacuum.start_mapping_perimeter()
                self.after(0, lambda: self._set_banner("Paso 1 · recorriendo bordes y paredes en tiempo real…"))
            except Exception as exc:
                msg = str(exc).strip() or "El E10 rechazó el modo de borde/perímetro."
                self.mapping_active = False
                self.mapping_phase = 0
                self.after(0, self._sync_mapping_step_buttons)
                self.after(0, lambda: messagebox.showerror("No se pudo iniciar el perímetro", msg, parent=self))
                self.after(0, self._render_maps)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ Paso 2
    def start_interior_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if self.mapping_active:
            messagebox.showinfo("Mapeo en curso", "Primero detené o esperá a que termine el paso actual.", parent=self)
            return
        if not (self.mapping_step1_complete or self._has_perimeter_data()):
            messagebox.showinfo(
                "Primero el perímetro",
                "Antes de completar el interior, ejecutá el Paso 1 para registrar los bordes.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Paso 2 · Interior",
            "Ahora voy a mandar al E10 el recorrido GLOBAL (0) para completar las zonas interiores.\n\n"
            "El perímetro del Paso 1 se conserva y el recorrido interior se dibuja encima en tiempo real.",
            parent=self,
        )
        if not ok:
            return

        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        # Evita guardar por error los últimos puntos de la trayectoria del Paso 1
        # hasta que el robot confirme que ya arrancó una tarea nueva.
        self.mapping_transitioning = True
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 2 · iniciando recorrido interior…")

        def worker():
            try:
                time.sleep(0.6)
                self.vacuum.start_mapping_interior()
            except Exception as exc:
                msg = str(exc).strip() or "El E10 rechazó el recorrido interior."
                self.mapping_active = False
                self.mapping_phase = 0
                self.mapping_transitioning = False
                self.after(0, self._sync_mapping_step_buttons)
                self.after(0, lambda: messagebox.showerror("No se pudo iniciar el interior", msg, parent=self))
                self.after(0, self._render_maps)

        threading.Thread(target=worker, daemon=True).start()

    def finish_mapping(self):
        if not self.mapping_active:
            self._set_banner("No hay un paso de mapeo activo.")
            self._sync_mapping_step_buttons()
            return

        phase = self.mapping_phase
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self._sync_mapping_step_buttons()
        self._render_maps()

        if phase == 1 and self._has_perimeter_data():
            self.mapping_step1_complete = True
        elif phase == 2:
            self.mapping_step2_complete = True

        if self.vacuum:
            self._run_command("Deteniendo el paso de mapeo…", self.vacuum.stop)

    # ---------------------------------------------------------- estado/fases
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
                self.mapping_transitioning = False
                self._set_banner("Paso 2 · completando el interior en tiempo real…")

        if self.mapping_active and self.mapping_seen_moving and finished:
            phase = self.mapping_phase
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False

            if phase == 1:
                self.mapping_step1_complete = self._has_perimeter_data()
                self._set_banner("Paso 1 terminado · perímetro guardado. Cuando quieras, iniciá Paso 2.")
            elif phase == 2:
                self.mapping_step2_complete = True
                self._set_banner("Paso 2 terminado · interior completado y mapa guardado.")
                threading.Thread(target=self._restore_cleaning_preferences, daemon=True).start()

            self._sync_mapping_step_buttons()
            self._render_maps()

        if not self.mapping_active:
            if 1 <= int(s.suction or 0) <= 4:
                self.suction_var.set(int(s.suction))
            if 0 <= int(s.water or 0) <= 3:
                self.water_var.set(int(s.water))
            self._refresh_choice_buttons()

        self._set_connection(True, f"Conectado · {self.settings.get('ip', '')}")
        self._sync_mapping_step_buttons()


if __name__ == "__main__":
    App().mainloop()

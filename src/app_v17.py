import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_v16
from cleaning_plan import CleaningPlanStore
from robot_plans import (
    start_point_clean,
    start_whole_clean,
    start_zone_clean,
    sync_virtual_walls,
    wait_for_cleaning_cycle,
)

CARD = "#ffffff"
CARD_ALT = "#f8f9fb"
TEXT = "#17181a"
MUTED = "#7b8088"
BORDER = "#e8eaed"
ACCENT = "#ff6900"
GREEN = "#25a96b"
RED = "#d93025"
BLUE = "#3a8dde"

MODE_LABELS = {
    "Aspirar": "vacuum",
    "Aspirar + trapear": "vacuum_mop",
    "Trapear": "mop",
    "Aspirar y después trapear": "vacuum_then_mop",
}
MODE_NAMES = {value: key for key, value in MODE_LABELS.items()}
DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


class App(app_v16.App):
    """v17: zonas etiquetadas, bloqueos nativos y programador por día/modo."""

    def __init__(self):
        self.plan_store = None
        self._plan_draw_mode = None
        self._plan_drag_start = None
        self._plan_drag_item = None
        self._zone_manager = None
        self._zone_job_running = False
        super().__init__()

        self.plan_store = CleaningPlanStore(self.store.folder)
        plan = self.plan_store.snapshot()
        origin = plan.get("device_origin")
        if isinstance(origin, dict) and "x" in origin and "y" in origin:
            self._coord_origins["robot"] = (float(origin["x"]), float(origin["y"]))

        self._install_map_plan_controls()
        self._build_scheduler_page()
        self.after(200, self._refresh_scheduler_page)
        self.after(250, self._render_maps)

    # ------------------------------------------------------------- navegación
    def show_page(self, page):
        super().show_page(page)
        if page == "scheduler" and hasattr(self, "page_title"):
            self.page_title.configure(text="Programar")
            if self.plan_store:
                self._refresh_scheduler_page()

    def _build_scheduler_page(self):
        page = self._page("scheduler")
        nav_parent = None
        if self._nav_buttons:
            nav_parent = next(iter(self._nav_buttons.values())).master
        if nav_parent is not None:
            self._nav_button(nav_parent, "Programar", "scheduler")

        shell = tk.Frame(page, bg=app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9.APP_BG)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=2)
        shell.grid_columnconfigure(1, weight=3)
        shell.grid_rowconfigure(0, weight=1)

        form = tk.Frame(shell, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)
        listing = tk.Frame(shell, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        listing.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)

        tk.Label(form, text="Nueva programación", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 5))
        tk.Label(
            form,
            text="Podés crear varias limpiezas con días, horarios, modos y zonas distintos.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self.schedule_name_var = tk.StringVar(value="Limpieza")
        self._field_label(form, "Nombre")
        tk.Entry(form, textvariable=self.schedule_name_var, font=("Segoe UI", 9)).pack(fill="x", padx=18, pady=(0, 10))

        self._field_label(form, "Días")
        days = tk.Frame(form, bg=CARD)
        days.pack(fill="x", padx=18, pady=(0, 10))
        self.schedule_day_vars = []
        for index, label in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=index < 5)
            self.schedule_day_vars.append(var)
            tk.Checkbutton(days, text=label, variable=var, bg=CARD, activebackground=CARD, font=("Segoe UI", 8)).pack(side="left")

        row = tk.Frame(form, bg=CARD)
        row.pack(fill="x", padx=18, pady=(0, 10))
        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        right = tk.Frame(row, bg=CARD)
        right.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(left, text="Hora", bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(right, text="Minuto", bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.schedule_hour_var = tk.StringVar(value="10")
        self.schedule_minute_var = tk.StringVar(value="00")
        tk.Entry(left, textvariable=self.schedule_hour_var, width=5).pack(fill="x", pady=(3, 0))
        tk.Entry(right, textvariable=self.schedule_minute_var, width=5).pack(fill="x", pady=(3, 0))

        self._field_label(form, "Modo")
        self.schedule_mode_var = tk.StringVar(value="Aspirar")
        mode_combo = ttk.Combobox(form, textvariable=self.schedule_mode_var, values=list(MODE_LABELS), state="readonly")
        mode_combo.pack(fill="x", padx=18, pady=(0, 10))

        row2 = tk.Frame(form, bg=CARD)
        row2.pack(fill="x", padx=18, pady=(0, 10))
        suction_box = tk.Frame(row2, bg=CARD)
        suction_box.pack(side="left", fill="x", expand=True)
        water_box = tk.Frame(row2, bg=CARD)
        water_box.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(suction_box, text="Succión 1–4", bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(water_box, text="Agua 1–3", bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.schedule_suction_var = tk.StringVar(value="2")
        self.schedule_water_var = tk.StringVar(value="1")
        ttk.Combobox(suction_box, textvariable=self.schedule_suction_var, values=["1", "2", "3", "4"], state="readonly", width=7).pack(fill="x", pady=(3, 0))
        ttk.Combobox(water_box, textvariable=self.schedule_water_var, values=["1", "2", "3"], state="readonly", width=7).pack(fill="x", pady=(3, 0))

        self._field_label(form, "Dónde limpiar")
        target_row = tk.Frame(form, bg=CARD)
        target_row.pack(fill="x", padx=18)
        self.schedule_target_var = tk.StringVar(value="all")
        tk.Radiobutton(target_row, text="Toda la casa", variable=self.schedule_target_var, value="all", bg=CARD, activebackground=CARD).pack(side="left")
        tk.Radiobutton(target_row, text="Solo zonas", variable=self.schedule_target_var, value="zones", bg=CARD, activebackground=CARD).pack(side="left", padx=(10, 0))

        self.schedule_zone_frame = tk.Frame(form, bg=CARD_ALT, padx=8, pady=6)
        self.schedule_zone_frame.pack(fill="x", padx=18, pady=(8, 12))
        self.schedule_zone_vars = {}

        self._button(form, "Guardar programación", self._add_schedule_from_form, accent=True).pack(fill="x", padx=18, pady=(0, 16))

        head = tk.Frame(listing, bg=CARD)
        head.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(head, text="Programaciones", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(head, text="Segundo plano · Windows", bg="#e8f5ee", fg=GREEN, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="right")
        self.schedule_list_frame = tk.Frame(listing, bg=CARD)
        self.schedule_list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    def _field_label(self, parent, text):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(2, 4))

    # ---------------------------------------------------------- controles mapa
    def _install_map_plan_controls(self):
        tools = self.map_status_label.master
        self._button(tools, "Zonas", self.open_zone_manager, compact=True).pack(side="right", padx=(7, 0))
        self._button(tools, "Limpiar zonas…", self.open_zone_clean_dialog, compact=True).pack(side="right", padx=(7, 0))
        self._button(tools, "Bloquear zona", lambda: self._enable_plan_draw("no_go"), compact=True).pack(side="right", padx=(7, 0))
        self._button(tools, "Nueva zona", lambda: self._enable_plan_draw("zone"), compact=True).pack(side="right", padx=(7, 0))
        self._button(tools, "Guardar punto", self.save_selected_point, compact=True).pack(side="right", padx=(7, 0))

    def _enable_plan_draw(self, kind):
        if not self.local_map or not self.local_map.snapshot().get("points"):
            messagebox.showinfo("Mapa", "Primero terminá el mapeo para definir zonas.", parent=self)
            return
        self.room_edit_mode = False
        self._plan_draw_mode = kind
        text = "zona de limpieza" if kind == "zone" else "zona bloqueada"
        self._set_banner(f"Arrastrá un rectángulo sobre el mapa para crear una {text}.")

    def _map_press(self, event):
        if self._plan_draw_mode:
            self._plan_drag_start = (event.x, event.y)
            if self._plan_drag_item:
                try:
                    self.map_canvas.delete(self._plan_drag_item)
                except Exception:
                    pass
            color = GREEN if self._plan_draw_mode == "zone" else RED
            self._plan_drag_item = self.map_canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline=color, width=3, dash=(6, 3)
            )
            return
        return super()._map_press(event)

    def _map_drag(self, event):
        if self._plan_draw_mode and self._plan_drag_start and self._plan_drag_item:
            x0, y0 = self._plan_drag_start
            self.map_canvas.coords(self._plan_drag_item, x0, y0, event.x, event.y)
            return
        return super()._map_drag(event)

    def _map_release(self, event):
        if self._plan_draw_mode and self._plan_drag_start:
            kind = self._plan_draw_mode
            start = self._canvas_to_world(self.map_canvas, *self._plan_drag_start)
            end = self._canvas_to_world(self.map_canvas, event.x, event.y)
            self._plan_draw_mode = None
            self._plan_drag_start = None
            if self._plan_drag_item:
                try:
                    self.map_canvas.delete(self._plan_drag_item)
                except Exception:
                    pass
                self._plan_drag_item = None
            if not start or not end:
                return
            if abs(start[0] - end[0]) < 0.12 or abs(start[1] - end[1]) < 0.12:
                self._set_banner("La zona dibujada es demasiado pequeña.")
                return
            title = "Nueva zona" if kind == "zone" else "Nueva zona bloqueada"
            name = simpledialog.askstring(title, "Nombre o etiqueta:", parent=self)
            if name is None:
                return
            if kind == "zone":
                self.plan_store.add_zone(name, start[0], start[1], end[0], end[1])
                self._set_banner(f"Zona “{name or 'Zona'}” guardada.")
            else:
                self.plan_store.add_no_go(name, start[0], start[1], end[0], end[1])
                self._set_banner(f"Bloqueo “{name or 'Zona bloqueada'}” guardado y sincronizando con el E10…")
                self._sync_no_go_async()
            self._refresh_scheduler_page()
            self._render_maps()
            return
        return super()._map_release(event)

    # -------------------------------------------------------- overlays de mapa
    def _render_map_canvas(self, canvas, snapshot):
        super()._render_map_canvas(canvas, snapshot)
        if not self.plan_store:
            return
        transform = self._map_transforms.get(canvas)
        if not transform:
            return
        plan = self.plan_store.snapshot()
        scale = transform["scale"]
        min_x = transform["min_x"]
        max_y = transform["max_y"]
        pad = transform["pad"]

        def to_screen(x, y):
            return pad + (float(x) - min_x) * scale, pad + (max_y - float(y)) * scale

        for zone in plan.get("zones", []):
            a = to_screen(zone["x0"], zone["y0"])
            b = to_screen(zone["x1"], zone["y1"])
            left, right = sorted((a[0], b[0]))
            top, bottom = sorted((a[1], b[1]))
            canvas.create_rectangle(left, top, right, bottom, outline=GREEN, width=2, dash=(6, 3))
            canvas.create_text((left + right) / 2, top + 12, text=zone.get("name", "Zona"), fill=GREEN, font=("Segoe UI", 8, "bold"))

        for wall in plan.get("no_go", []):
            a = to_screen(wall["x0"], wall["y0"])
            b = to_screen(wall["x1"], wall["y1"])
            left, right = sorted((a[0], b[0]))
            top, bottom = sorted((a[1], b[1]))
            canvas.create_rectangle(left, top, right, bottom, outline=RED, width=3, dash=(4, 3))
            step = 12
            x = left - max(0, bottom - top)
            while x < right:
                canvas.create_line(max(left, x), bottom, min(right, x + (bottom - top)), top, fill="#f4b7b3", width=1)
                x += step
            canvas.create_text((left + right) / 2, top + 12, text=wall.get("name", "Bloqueado"), fill=RED, font=("Segoe UI", 8, "bold"))

        for point in plan.get("points", []):
            x, y = to_screen(point["x"], point["y"])
            canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=BLUE, outline="white", width=2)
            canvas.create_text(x + 8, y - 8, text=point.get("name", "Punto"), anchor="w", fill=BLUE, font=("Segoe UI", 7, "bold"))

    # ---------------------------------------------------- origen coordenadas
    def _apply_map_state(self, state):
        raw_robot = state.get("robot") if isinstance(state, dict) else None
        if self.plan_store and self._charging_confirmed and isinstance(raw_robot, dict):
            try:
                x = float(raw_robot["x"])
                y = float(raw_robot["y"])
                self.plan_store.set_device_origin(x, y)
                self._coord_origins["robot"] = (x, y)
            except Exception:
                pass
        return super()._apply_map_state(state)

    def _on_connected(self, ip):
        result = super()._on_connected(ip)
        self.after(2600, self._sync_no_go_async)
        return result

    # ------------------------------------------------------ paredes virtuales
    def _sync_no_go_async(self):
        if not self.vacuum or not self.plan_store:
            return
        plan = self.plan_store.snapshot()
        if not plan.get("virtual_walls_managed", False):
            return
        vacuum = self.vacuum

        def worker():
            try:
                sync_virtual_walls(vacuum, self.plan_store.snapshot())
                self._post_ui("plan_sync_ok")
            except Exception as exc:
                self._post_ui("plan_sync_error", str(exc).strip() or "No se pudieron sincronizar los bloqueos.")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------ limpieza normal
    def start_clean(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el Xiaomi Vacuum E10.", parent=self)
            return
        mode_label = self.mode_var.get()
        mode = {"Aspirar": "vacuum", "Aspirar + trapear": "vacuum_mop", "Trapear": "mop"}.get(mode_label, "vacuum")
        if not self.mop_enabled_var.get():
            mode = "vacuum"
        suction = int(self.suction_var.get())
        water = int(self.water_var.get())
        vacuum = self.vacuum
        plan = self.plan_store.snapshot() if self.plan_store else {}

        def command():
            sync_virtual_walls(vacuum, plan)
            return start_whole_clean(vacuum, mode, suction, water)

        self._run_command("Sincronizando bloqueos e iniciando limpieza…", command)

    def clean_selected_point(self):
        if not self.selected_point or not self.vacuum or not self.plan_store:
            return
        point = {"x": self.selected_point[0], "y": self.selected_point[1]}
        plan = self.plan_store.snapshot()
        self._run_command(
            "Enviando el E10 al punto seleccionado…",
            lambda: start_point_clean(self.vacuum, point, plan, int(self.suction_var.get())),
        )

    def clean_local_room(self, room):
        if not self.vacuum or not self.plan_store:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        plan = self.plan_store.snapshot()
        self._run_command(
            f"Limpiando {room.get('name', 'habitación')}…",
            lambda: start_zone_clean(self.vacuum, room, plan, "vacuum", int(self.suction_var.get()), 0),
        )

    # ------------------------------------------------------ puntos guardados
    def save_selected_point(self):
        if not self.selected_point or not self.plan_store:
            messagebox.showinfo("Punto", "Primero hacé clic sobre un punto del mapa.", parent=self)
            return
        name = simpledialog.askstring("Guardar punto", "Nombre del punto:", parent=self)
        if name is None:
            return
        self.plan_store.add_point(name, self.selected_point[0], self.selected_point[1])
        self._render_maps()
        self._set_banner(f"Punto “{name or 'Punto'}” guardado.")

    # ------------------------------------------------------ gestor de zonas
    def open_zone_manager(self):
        if not self.plan_store:
            return
        if self._zone_manager and self._zone_manager.winfo_exists():
            self._zone_manager.destroy()
        win = tk.Toplevel(self)
        win.title("Zonas, bloqueos y puntos")
        win.geometry("620x560")
        win.transient(self)
        self._zone_manager = win
        body = tk.Frame(win, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        plan = self.plan_store.snapshot()

        def section(title):
            tk.Label(body, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 5))

        section("Zonas de limpieza")
        if not plan.get("zones"):
            tk.Label(body, text="Todavía no hay zonas etiquetadas.", fg="#777").pack(anchor="w")
        for zone in plan.get("zones", []):
            row = tk.Frame(body)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=zone.get("name", "Zona"), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Limpiar", command=lambda z=dict(zone): self._run_zones_now([z], "vacuum", 2, 1)).pack(side="left", padx=3)
            tk.Button(row, text="Eliminar", command=lambda zid=zone["id"]: self._delete_zone_and_refresh(zid)).pack(side="left")

        section("Zonas bloqueadas")
        if not plan.get("no_go"):
            tk.Label(body, text="No hay bloqueos creados por esta app.", fg="#777").pack(anchor="w")
        for wall in plan.get("no_go", []):
            row = tk.Frame(body)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=wall.get("name", "Bloqueado"), fg=RED, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Eliminar", command=lambda wid=wall["id"]: self._delete_no_go_and_refresh(wid)).pack(side="left")

        section("Puntos guardados")
        if not plan.get("points"):
            tk.Label(body, text="No hay puntos guardados.", fg="#777").pack(anchor="w")
        for point in plan.get("points", []):
            row = tk.Frame(body)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=point.get("name", "Punto"), fg=BLUE, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Ir / limpiar", command=lambda p=dict(point): self._clean_saved_point(p)).pack(side="left", padx=3)
            tk.Button(row, text="Eliminar", command=lambda pid=point["id"]: self._delete_point_and_refresh(pid)).pack(side="left")

    def _delete_zone_and_refresh(self, zone_id):
        self.plan_store.delete_zone(zone_id)
        self._refresh_scheduler_page()
        self._render_maps()
        self.open_zone_manager()

    def _delete_no_go_and_refresh(self, wall_id):
        self.plan_store.delete_no_go(wall_id)
        self._render_maps()
        self._sync_no_go_async()
        self.open_zone_manager()

    def _delete_point_and_refresh(self, point_id):
        self.plan_store.delete_point(point_id)
        self._render_maps()
        self.open_zone_manager()

    def _clean_saved_point(self, point):
        if not self.vacuum:
            return
        plan = self.plan_store.snapshot()
        self._run_command(
            f"Enviando el E10 a {point.get('name', 'punto')}…",
            lambda: start_point_clean(self.vacuum, point, plan, int(self.suction_var.get())),
        )

    # ------------------------------------------------------ limpiar zonas UI
    def open_zone_clean_dialog(self):
        if not self.plan_store:
            return
        zones = self.plan_store.snapshot().get("zones", [])
        if not zones:
            messagebox.showinfo("Zonas", "Primero creá y etiquetá al menos una zona en el mapa.", parent=self)
            return
        win = tk.Toplevel(self)
        win.title("Limpiar zonas")
        win.geometry("430x470")
        win.transient(self)
        frame = tk.Frame(win, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Elegí las zonas", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        vars_by_id = {}
        for zone in zones:
            var = tk.BooleanVar(value=False)
            vars_by_id[zone["id"]] = var
            tk.Checkbutton(frame, text=zone.get("name", "Zona"), variable=var).pack(anchor="w", pady=2)
        tk.Label(frame, text="Modo", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(12, 3))
        mode_var = tk.StringVar(value="Aspirar")
        ttk.Combobox(frame, textvariable=mode_var, values=["Aspirar", "Aspirar + trapear", "Trapear", "Aspirar y después trapear"], state="readonly").pack(fill="x")
        tk.Label(frame, text="Succión", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 3))
        suction_var = tk.StringVar(value=str(max(1, int(self.suction_var.get()))))
        ttk.Combobox(frame, textvariable=suction_var, values=["1", "2", "3", "4"], state="readonly").pack(fill="x")
        tk.Label(frame, text="Agua", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 3))
        water_var = tk.StringVar(value="1")
        ttk.Combobox(frame, textvariable=water_var, values=["1", "2", "3"], state="readonly").pack(fill="x")

        def run():
            selected = [z for z in zones if vars_by_id[z["id"]].get()]
            if not selected:
                messagebox.showinfo("Zonas", "Elegí al menos una zona.", parent=win)
                return
            win.destroy()
            self._run_zones_now(selected, MODE_LABELS[mode_var.get()], int(suction_var.get()), int(water_var.get()))

        self._button(frame, "Iniciar limpieza", run, accent=True).pack(fill="x", pady=(18, 0))

    def _run_zones_now(self, zones, mode, suction, water):
        if not self.vacuum or self._zone_job_running:
            if self._zone_job_running:
                messagebox.showinfo("Limpieza", "Ya hay una limpieza de zonas gestionada por la app.", parent=self)
            return
        self._zone_job_running = True
        vacuum = self.vacuum
        plan = self.plan_store.snapshot()

        def worker():
            try:
                sync_virtual_walls(vacuum, plan)
                passes = ["vacuum", "mop"] if mode == "vacuum_then_mop" else [mode]
                for clean_mode in passes:
                    for zone in zones:
                        self._post_ui("plan_job_stage", f"Limpiando {zone.get('name', 'zona')} · {MODE_NAMES.get(clean_mode, clean_mode)}…")
                        start_zone_clean(vacuum, zone, plan, clean_mode, suction, water)
                        wait_for_cleaning_cycle(vacuum)
                        time.sleep(1.0)
                self._post_ui("plan_job_done", "Limpieza de zonas completada.")
            except Exception as exc:
                self._post_ui("plan_job_error", str(exc).strip() or "No se pudo completar la limpieza de zonas.")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ programador
    def _refresh_scheduler_page(self):
        if not self.plan_store or not hasattr(self, "schedule_zone_frame"):
            return
        plan = self.plan_store.snapshot()

        for child in self.schedule_zone_frame.winfo_children():
            child.destroy()
        previous = {zid: var.get() for zid, var in getattr(self, "schedule_zone_vars", {}).items()}
        self.schedule_zone_vars = {}
        zones = plan.get("zones", [])
        if not zones:
            tk.Label(self.schedule_zone_frame, text="No hay zonas etiquetadas.", bg=CARD_ALT, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        for zone in zones:
            var = tk.BooleanVar(value=previous.get(zone["id"], False))
            self.schedule_zone_vars[zone["id"]] = var
            tk.Checkbutton(
                self.schedule_zone_frame,
                text=zone.get("name", "Zona"),
                variable=var,
                bg=CARD_ALT,
                activebackground=CARD_ALT,
                font=("Segoe UI", 8),
            ).pack(anchor="w")

        for child in self.schedule_list_frame.winfo_children():
            child.destroy()
        schedules = plan.get("schedules", [])
        if not schedules:
            tk.Label(
                self.schedule_list_frame,
                text="Todavía no hay limpiezas programadas.",
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=10)
            return

        zones_by_id = {z["id"]: z.get("name", "Zona") for z in zones}
        for schedule in schedules:
            card = tk.Frame(self.schedule_list_frame, bg=CARD_ALT, highlightthickness=1, highlightbackground=BORDER)
            card.pack(fill="x", pady=4)
            top = tk.Frame(card, bg=CARD_ALT)
            top.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(top, text=schedule.get("name", "Limpieza"), bg=CARD_ALT, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
            enabled = tk.BooleanVar(value=bool(schedule.get("enabled", True)))
            tk.Checkbutton(
                top,
                text="Activa",
                variable=enabled,
                bg=CARD_ALT,
                activebackground=CARD_ALT,
                command=lambda sid=schedule["id"], v=enabled: self._toggle_schedule(sid, v.get()),
            ).pack(side="right")

            days = ", ".join(DAY_NAMES[int(i)] for i in schedule.get("days", []) if 0 <= int(i) < 7)
            target = "Toda la casa"
            if schedule.get("target") == "zones":
                selected_names = [zones_by_id.get(zid, "zona eliminada") for zid in schedule.get("zone_ids", [])]
                target = "Zonas: " + ", ".join(selected_names)
            details = (
                f"{days} · {int(schedule.get('hour', 0)):02d}:{int(schedule.get('minute', 0)):02d} · "
                f"{MODE_NAMES.get(schedule.get('mode'), schedule.get('mode'))} · {target}"
            )
            tk.Label(card, text=details, bg=CARD_ALT, fg=MUTED, font=("Segoe UI", 8), wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(0, 7))
            actions = tk.Frame(card, bg=CARD_ALT)
            actions.pack(fill="x", padx=10, pady=(0, 8))
            tk.Button(actions, text="Ejecutar ahora", command=lambda s=dict(schedule): self._run_schedule_now(s), relief="flat", bg="#e8f5ee", fg=GREEN).pack(side="left")
            tk.Button(actions, text="Eliminar", command=lambda sid=schedule["id"]: self._delete_schedule(sid), relief="flat", bg="#fdeceb", fg=RED).pack(side="right")

    def _add_schedule_from_form(self):
        try:
            hour = int(self.schedule_hour_var.get())
            minute = int(self.schedule_minute_var.get())
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except Exception:
            messagebox.showerror("Programación", "Ingresá una hora válida entre 00:00 y 23:59.", parent=self)
            return
        days = [i for i, var in enumerate(self.schedule_day_vars) if var.get()]
        if not days:
            messagebox.showinfo("Programación", "Elegí al menos un día.", parent=self)
            return
        target = self.schedule_target_var.get()
        zone_ids = [zid for zid, var in self.schedule_zone_vars.items() if var.get()]
        if target == "zones" and not zone_ids:
            messagebox.showinfo("Programación", "Elegí al menos una zona para la limpieza programada.", parent=self)
            return
        item = {
            "name": self.schedule_name_var.get().strip() or "Limpieza",
            "enabled": True,
            "days": days,
            "hour": hour,
            "minute": minute,
            "mode": MODE_LABELS[self.schedule_mode_var.get()],
            "suction": int(self.schedule_suction_var.get()),
            "water": int(self.schedule_water_var.get()),
            "target": target,
            "zone_ids": zone_ids,
        }
        self.plan_store.add_schedule(item)
        self._refresh_scheduler_page()
        self._set_banner("Programación guardada. El agente de Windows la ejecutará aunque cierres esta ventana.")

    def _toggle_schedule(self, schedule_id, enabled):
        self.plan_store.update_schedule(schedule_id, {"enabled": bool(enabled)})

    def _delete_schedule(self, schedule_id):
        self.plan_store.delete_schedule(schedule_id)
        self._refresh_scheduler_page()

    def _run_schedule_now(self, schedule):
        if not self.vacuum or self._zone_job_running:
            return
        plan = self.plan_store.snapshot()
        zones_by_id = {z["id"]: z for z in plan.get("zones", [])}
        target = schedule.get("target", "all")
        zones = [zones_by_id[zid] for zid in schedule.get("zone_ids", []) if zid in zones_by_id]
        vacuum = self.vacuum
        self._zone_job_running = True

        def worker():
            try:
                sync_virtual_walls(vacuum, plan)
                mode = schedule.get("mode", "vacuum")
                passes = ["vacuum", "mop"] if mode == "vacuum_then_mop" else [mode]
                for clean_mode in passes:
                    if target == "all":
                        self._post_ui("plan_job_stage", f"Ejecutando {MODE_NAMES.get(clean_mode, clean_mode)} en toda la casa…")
                        start_whole_clean(vacuum, clean_mode, schedule.get("suction", 1), schedule.get("water", 1))
                        wait_for_cleaning_cycle(vacuum)
                    else:
                        if not zones:
                            raise RuntimeError("La programación no tiene zonas disponibles.")
                        for zone in zones:
                            self._post_ui("plan_job_stage", f"Limpiando {zone.get('name', 'zona')}…")
                            start_zone_clean(vacuum, zone, plan, clean_mode, schedule.get("suction", 1), schedule.get("water", 1))
                            wait_for_cleaning_cycle(vacuum)
                self._post_ui("plan_job_done", "Programación ejecutada correctamente.")
            except Exception as exc:
                self._post_ui("plan_job_error", str(exc).strip() or "No se pudo ejecutar la programación.")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "plan_sync_ok":
            self._set_banner("Zonas bloqueadas sincronizadas con el E10.")
            return
        if kind == "plan_sync_error":
            self._set_banner(f"No pude sincronizar los bloqueos: {payload[0]}")
            return
        if kind == "plan_job_stage":
            self._set_banner(str(payload[0]))
            return
        if kind == "plan_job_done":
            self._zone_job_running = False
            self._set_banner(str(payload[0]))
            return
        if kind == "plan_job_error":
            self._zone_job_running = False
            message = str(payload[0])
            self._set_banner("Error en limpieza planificada: " + message)
            messagebox.showerror("Limpieza planificada", message, parent=self)
            return
        return super()._handle_ui_event(kind, payload)


if __name__ == "__main__":
    app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import tkinter as tk
from tkinter import ttk

import app_v22

BG = app_v22.BG
SURFACE = app_v22.SURFACE
SURFACE_2 = app_v22.SURFACE_2
SIDEBAR = app_v22.SIDEBAR
SIDEBAR_MUTED = app_v22.SIDEBAR_MUTED
TEXT = app_v22.TEXT
MUTED = app_v22.MUTED
BORDER = app_v22.BORDER
ACCENT = app_v22.ACCENT
ACCENT_HOVER = app_v22.ACCENT_HOVER
ACCENT_SOFT = app_v22.ACCENT_SOFT
GREEN = app_v22.GREEN
GREEN_SOFT = app_v22.GREEN_SOFT
RED = app_v22.RED
RED_SOFT = app_v22.RED_SOFT
BLUE = app_v22.BLUE
DAY_NAMES = app_v22.DAY_NAMES
MODE_LABELS = app_v22.MODE_LABELS


class App(app_v22.App):
    """v23: navegación inequívoca, mapa movible en Inicio y Programar rediseñado."""

    def __init__(self):
        # Estado propio de la nueva navegación. v22 recreaba _nav_buttons después
        # de construir el sidebar; esta colección queda fuera de ese ciclo.
        self._v23_nav = {}

        # Pan independiente del mapa pequeño de Inicio. No altera las coordenadas
        # guardadas ni el pan del mapa principal.
        self._home_map_pan = (0.0, 0.0)
        self._home_map_drag_start = None
        self._home_map_pan_origin = (0.0, 0.0)

        self._schedule_day_chip_buttons = []
        self._schedule_mode_buttons = {}
        self._schedule_target_buttons = {}
        self._schedule_summary_label = None
        super().__init__()

    # ------------------------------------------------------- navegación lateral
    def _nav_button_v22(self, parent, text, page, icon):
        row = tk.Frame(parent, bg=SIDEBAR, height=44)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        indicator = tk.Frame(row, bg=SIDEBAR, width=4)
        indicator.pack(side="left", fill="y")

        btn = tk.Button(
            row,
            text=f"  {icon}    {text}",
            command=lambda p=page: self.show_page(p),
            bg=SIDEBAR,
            fg=SIDEBAR_MUTED,
            activebackground="#1f2937",
            activeforeground="white",
            relief="flat",
            bd=0,
            anchor="w",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        btn.pack(side="left", fill="both", expand=True)

        self._v23_nav[page] = (row, indicator, btn)
        # Compatibilidad durante la construcción de v22; si luego se reinicia,
        # show_page usa _v23_nav y no depende de esta colección.
        try:
            self._nav_buttons[page] = btn
        except Exception:
            pass
        return btn

    def show_page(self, page):
        frame = getattr(self, "_pages", {}).get(page)
        if not frame:
            return
        frame.tkraise()
        titles = {
            "home": "Inicio",
            "clean": "Limpiar",
            "map": "Mapa",
            "scheduler": "Programar",
            "robot": "Robot",
            "settings": "Ajustes",
        }
        if hasattr(self, "page_title"):
            self.page_title.configure(text=titles.get(page, page))

        for key, (row, indicator, btn) in self._v23_nav.items():
            selected = key == page
            bg = "#252f42" if selected else SIDEBAR
            try:
                row.configure(bg=bg)
                indicator.configure(bg=ACCENT if selected else SIDEBAR)
                btn.configure(
                    bg=bg,
                    fg="white" if selected else SIDEBAR_MUTED,
                    activebackground="#303b50" if selected else "#1f2937",
                    activeforeground="white",
                    font=("Segoe UI Semibold", 10) if selected else ("Segoe UI", 10, "bold"),
                )
            except Exception:
                pass

        if page in ("home", "map"):
            self.after(40, self._render_maps)
        if page == "scheduler" and self.plan_store:
            self.after(40, self._refresh_scheduler_page)

    # --------------------------------------------------------- mapa en Inicio
    def _build_home_page_v22(self):
        super()._build_home_page_v22()
        if not hasattr(self, "home_map_canvas"):
            return
        self.home_map_canvas.configure(cursor="fleur")
        self.home_map_canvas.bind("<ButtonPress-1>", self._home_map_press)
        self.home_map_canvas.bind("<B1-Motion>", self._home_map_drag)
        self.home_map_canvas.bind("<ButtonRelease-1>", self._home_map_release)

    def _home_map_press(self, event):
        self._home_map_drag_start = (event.x, event.y)
        self._home_map_pan_origin = self._home_map_pan
        return "break"

    def _home_map_drag(self, event):
        if not self._home_map_drag_start:
            return "break"
        sx, sy = self._home_map_drag_start
        ox, oy = self._home_map_pan_origin
        new_pan = (ox + event.x - sx, oy + event.y - sy)
        old_pan = self._home_map_pan
        dx = new_pan[0] - old_pan[0]
        dy = new_pan[1] - old_pan[1]
        if dx or dy:
            self.home_map_canvas.move("all", dx, dy)
            self._home_map_pan = new_pan
        return "break"

    def _home_map_release(self, _event):
        self._home_map_drag_start = None
        return "break"

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        if canvas is getattr(self, "home_map_canvas", None):
            dx, dy = self._home_map_pan
            if dx or dy:
                canvas.move("all", dx, dy)
        return result

    # ------------------------------------------------------- Programar v23
    def _build_scheduler_page(self):
        page = self._pages.get("scheduler") or self._page("scheduler")
        for child in page.winfo_children():
            child.destroy()

        page.grid_columnconfigure(0, weight=5)
        page.grid_columnconfigure(1, weight=7)
        page.grid_rowconfigure(0, weight=1)

        # Editor izquierdo ---------------------------------------------------
        editor_outer, editor = self._surface(page, 22, 20)
        editor_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 8), pady=5)
        self._section_title(
            editor,
            "Crear rutina",
            "Configurá una limpieza automática sin navegar por varias ventanas.",
        )

        self.schedule_name_var = tk.StringVar(value="Limpieza")
        tk.Label(editor, text="NOMBRE", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(20, 6)
        )
        tk.Entry(
            editor,
            textvariable=self.schedule_name_var,
            bg=SURFACE_2,
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            insertbackground=TEXT,
            font=("Segoe UI", 10),
        ).pack(fill="x", ipady=8)

        # Días como chips grandes.
        tk.Label(editor, text="DÍAS", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(18, 7)
        )
        days = tk.Frame(editor, bg=SURFACE)
        days.pack(fill="x")
        self.schedule_day_vars = []
        self._schedule_day_chip_buttons = []
        for index, label in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=index < 5)
            self.schedule_day_vars.append(var)
            btn = tk.Button(
                days,
                text=label,
                command=lambda i=index: self._toggle_schedule_day(i),
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=7,
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0, 4 if index < 6 else 0))
            self._schedule_day_chip_buttons.append(btn)
        self._refresh_schedule_day_chips()

        # Hora muy visible.
        tk.Label(editor, text="HORA", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(18, 7)
        )
        time_card = tk.Frame(editor, bg=SURFACE_2, highlightthickness=1, highlightbackground=BORDER)
        time_card.pack(fill="x")
        self.schedule_hour_var = tk.StringVar(value="10")
        self.schedule_minute_var = tk.StringVar(value="00")
        tk.Entry(
            time_card,
            textvariable=self.schedule_hour_var,
            width=3,
            justify="center",
            bg=SURFACE_2,
            fg=TEXT,
            relief="flat",
            bd=0,
            font=("Segoe UI Semibold", 24),
        ).pack(side="left", fill="x", expand=True, padx=(12, 0), pady=8)
        tk.Label(time_card, text=":", bg=SURFACE_2, fg=MUTED, font=("Segoe UI Semibold", 23)).pack(side="left")
        tk.Entry(
            time_card,
            textvariable=self.schedule_minute_var,
            width=3,
            justify="center",
            bg=SURFACE_2,
            fg=TEXT,
            relief="flat",
            bd=0,
            font=("Segoe UI Semibold", 24),
        ).pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

        # Modo como tarjetas seleccionables.
        tk.Label(editor, text="MODO", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(18, 7)
        )
        self.schedule_mode_var = tk.StringVar(value="Aspirar")
        self._schedule_mode_buttons = {}
        mode_grid = tk.Frame(editor, bg=SURFACE)
        mode_grid.pack(fill="x")
        for index, label in enumerate(MODE_LABELS):
            btn = tk.Button(
                mode_grid,
                text=label,
                command=lambda value=label: self._set_schedule_mode(value),
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=8,
            )
            btn.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 5) if index % 2 == 0 else (5, 0), pady=3)
            mode_grid.grid_columnconfigure(index % 2, weight=1)
            self._schedule_mode_buttons[label] = btn
        self._refresh_schedule_mode_buttons()

        # Intensidad.
        levels = tk.Frame(editor, bg=SURFACE)
        levels.pack(fill="x", pady=(18, 0))
        self.schedule_suction_var = tk.StringVar(value="2")
        self.schedule_water_var = tk.StringVar(value="1")
        self._modern_combo_field(levels, "Succión", self.schedule_suction_var, ["1 · Silenciosa", "2 · Normal", "3 · Fuerte", "4 · Turbo"], raw_values=["1", "2", "3", "4"]).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        self._modern_combo_field(levels, "Agua", self.schedule_water_var, ["1 · Baja", "2 · Media", "3 · Alta"], raw_values=["1", "2", "3"]).pack(
            side="left", fill="x", expand=True, padx=(5, 0)
        )

        # Destino con botones grandes.
        tk.Label(editor, text="DÓNDE", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(18, 7)
        )
        self.schedule_target_var = tk.StringVar(value="all")
        self._schedule_target_buttons = {}
        target_row = tk.Frame(editor, bg=SURFACE)
        target_row.pack(fill="x")
        for value, label in (("all", "Toda la casa"), ("zones", "Solo zonas")):
            btn = tk.Button(
                target_row,
                text=label,
                command=lambda v=value: self._set_schedule_target(v),
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                padx=10,
                pady=9,
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0, 5) if value == "all" else (5, 0))
            self._schedule_target_buttons[value] = btn
        self._refresh_schedule_target_buttons()

        self.schedule_zone_frame = tk.Frame(
            editor,
            bg=SURFACE_2,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=12,
            pady=10,
        )
        self.schedule_zone_frame.pack(fill="x", pady=(10, 0))
        self.schedule_zone_vars = {}

        save = self._button(editor, "Guardar rutina", self._add_schedule_from_form, accent=True)
        save.pack(fill="x", side="bottom", pady=(18, 0))

        # Listado derecho ---------------------------------------------------
        list_outer, listing = self._surface(page, 20, 18)
        list_outer.grid(row=0, column=1, sticky="nsew", padx=(8, 5), pady=5)

        head = tk.Frame(listing, bg=SURFACE)
        head.pack(fill="x", pady=(0, 14))
        text = tk.Frame(head, bg=SURFACE)
        text.pack(side="left")
        tk.Label(text, text="Tus rutinas", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 17)).pack(anchor="w")
        tk.Label(
            text,
            text="Se ejecutan en segundo plano mientras Windows esté iniciado.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))
        self._schedule_summary_label = tk.Label(
            head,
            text="0 activas",
            bg=GREEN_SOFT,
            fg=GREEN,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=5,
        )
        self._schedule_summary_label.pack(side="right")

        self.schedule_list_frame = tk.Frame(listing, bg=SURFACE)
        self.schedule_list_frame.pack(fill="both", expand=True)

    def _modern_combo_field(self, parent, title, variable, display_values, raw_values):
        frame = tk.Frame(parent, bg=SURFACE)
        tk.Label(frame, text=title.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        display = tk.StringVar()
        raw_to_display = dict(zip(raw_values, display_values))
        display_to_raw = dict(zip(display_values, raw_values))
        display.set(raw_to_display.get(str(variable.get()), display_values[0]))
        combo = ttk.Combobox(frame, textvariable=display, values=display_values, state="readonly")
        combo.pack(fill="x")

        def changed(_event=None):
            variable.set(display_to_raw.get(display.get(), raw_values[0]))

        combo.bind("<<ComboboxSelected>>", changed)
        return frame

    def _toggle_schedule_day(self, index):
        var = self.schedule_day_vars[index]
        var.set(not bool(var.get()))
        self._refresh_schedule_day_chips()

    def _refresh_schedule_day_chips(self):
        for index, btn in enumerate(self._schedule_day_chip_buttons):
            active = bool(self.schedule_day_vars[index].get())
            btn.configure(
                bg=ACCENT if active else SURFACE_2,
                fg="white" if active else MUTED,
                activebackground=ACCENT_HOVER if active else "#eef2f6",
                activeforeground="white" if active else TEXT,
                highlightthickness=1,
                highlightbackground=ACCENT if active else BORDER,
            )

    def _set_schedule_mode(self, label):
        self.schedule_mode_var.set(label)
        self._refresh_schedule_mode_buttons()

    def _refresh_schedule_mode_buttons(self):
        selected = self.schedule_mode_var.get()
        for label, btn in self._schedule_mode_buttons.items():
            active = label == selected
            btn.configure(
                bg=ACCENT_SOFT if active else SURFACE_2,
                fg=ACCENT if active else TEXT,
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT if active else TEXT,
                highlightthickness=1,
                highlightbackground=ACCENT if active else BORDER,
            )

    def _set_schedule_target(self, value):
        self.schedule_target_var.set(value)
        self._refresh_schedule_target_buttons()

    def _refresh_schedule_target_buttons(self):
        selected = self.schedule_target_var.get()
        for value, btn in self._schedule_target_buttons.items():
            active = value == selected
            btn.configure(
                bg=ACCENT if active else SURFACE_2,
                fg="white" if active else TEXT,
                activebackground=ACCENT_HOVER if active else "#eef2f6",
                activeforeground="white" if active else TEXT,
                highlightthickness=1,
                highlightbackground=ACCENT if active else BORDER,
            )
        # Las zonas permanecen visibles para que el usuario pueda preseleccionarlas,
        # pero se aclara visualmente cuando "Toda la casa" está activo.
        if hasattr(self, "schedule_zone_frame"):
            try:
                self.schedule_zone_frame.configure(
                    highlightbackground=ACCENT if selected == "zones" else BORDER
                )
            except Exception:
                pass

    def _refresh_scheduler_page(self):
        if not self.plan_store or not hasattr(self, "schedule_zone_frame"):
            return
        plan = self.plan_store.snapshot()

        # Zonas del mapa activo.
        for child in self.schedule_zone_frame.winfo_children():
            child.destroy()
        previous = {zid: var.get() for zid, var in getattr(self, "schedule_zone_vars", {}).items()}
        self.schedule_zone_vars = {}
        zones = plan.get("zones", [])
        if not zones:
            tk.Label(
                self.schedule_zone_frame,
                text="No hay zonas guardadas en este mapa. Podés crear una desde Mapa.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=360,
                justify="left",
            ).pack(anchor="w")
        else:
            tk.Label(
                self.schedule_zone_frame,
                text="Zonas disponibles",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", pady=(0, 5))
            for zone in zones:
                var = tk.BooleanVar(value=previous.get(zone["id"], False))
                self.schedule_zone_vars[zone["id"]] = var
                tk.Checkbutton(
                    self.schedule_zone_frame,
                    text=zone.get("name", "Zona"),
                    variable=var,
                    bg=SURFACE_2,
                    activebackground=SURFACE_2,
                    selectcolor=SURFACE,
                    fg=TEXT,
                    font=("Segoe UI", 8),
                ).pack(anchor="w", pady=1)

        # Tarjetas de rutinas.
        for child in self.schedule_list_frame.winfo_children():
            child.destroy()
        schedules = plan.get("schedules", [])
        active_count = sum(1 for item in schedules if bool(item.get("enabled", True)))
        if self._schedule_summary_label:
            self._schedule_summary_label.configure(
                text=f"{active_count} activa{'s' if active_count != 1 else ''} · {len(schedules)} total"
            )

        if not schedules:
            empty = tk.Frame(
                self.schedule_list_frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            empty.pack(fill="x", pady=8)
            tk.Label(
                empty,
                text="Todavía no hay rutinas",
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI Semibold", 12),
            ).pack(anchor="w", padx=18, pady=(18, 4))
            tk.Label(
                empty,
                text="Creá la primera desde el panel de la izquierda. Después podés pausarla, ejecutarla o eliminarla desde acá.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 9),
                wraplength=620,
                justify="left",
            ).pack(anchor="w", padx=18, pady=(0, 18))
            return

        zones_by_id = {z["id"]: z.get("name", "Zona") for z in zones}
        for schedule in schedules:
            enabled_value = bool(schedule.get("enabled", True))
            card = tk.Frame(
                self.schedule_list_frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=ACCENT if enabled_value else BORDER,
            )
            card.pack(fill="x", pady=5)

            # Hora grande a la izquierda.
            time_box = tk.Frame(card, bg="#f1f5f9", width=112)
            time_box.pack(side="left", fill="y")
            time_box.pack_propagate(False)
            tk.Label(
                time_box,
                text=f"{int(schedule.get('hour', 0)):02d}:{int(schedule.get('minute', 0)):02d}",
                bg="#f1f5f9",
                fg=TEXT,
                font=("Segoe UI Semibold", 18),
            ).pack(pady=(15, 2))
            tk.Label(
                time_box,
                text="ACTIVA" if enabled_value else "PAUSADA",
                bg=GREEN_SOFT if enabled_value else "#e2e8f0",
                fg=GREEN if enabled_value else MUTED,
                font=("Segoe UI", 7, "bold"),
                padx=7,
                pady=3,
            ).pack()

            center = tk.Frame(card, bg=SURFACE_2)
            center.pack(side="left", fill="both", expand=True, padx=14, pady=11)
            tk.Label(
                center,
                text=schedule.get("name", "Limpieza"),
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="w")

            days_text = " · ".join(
                DAY_NAMES[int(i)] for i in schedule.get("days", []) if 0 <= int(i) < 7
            ) or "Sin días"
            tk.Label(
                center,
                text=days_text,
                bg=SURFACE_2,
                fg=ACCENT,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", pady=(4, 2))

            target = "Toda la casa"
            if schedule.get("target") == "zones":
                names = [zones_by_id.get(zid, "zona eliminada") for zid in schedule.get("zone_ids", [])]
                target = "Zonas: " + ", ".join(names)
            mode_name = next(
                (label for label, value in MODE_LABELS.items() if value == schedule.get("mode")),
                str(schedule.get("mode", "Aspirar")),
            )
            tk.Label(
                center,
                text=f"{mode_name}  ·  {target}  ·  Succión {schedule.get('suction', 1)}",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=510,
                justify="left",
            ).pack(anchor="w", pady=(0, 6))

            actions = tk.Frame(center, bg=SURFACE_2)
            actions.pack(fill="x", pady=(2, 0))
            self._button(
                actions,
                "Ejecutar ahora",
                lambda s=dict(schedule): self._run_schedule_now(s),
                compact=True,
                accent=True,
            ).pack(side="left")
            self._button(
                actions,
                "Eliminar",
                lambda sid=schedule["id"]: self._delete_schedule(sid),
                compact=True,
                danger=True,
            ).pack(side="left", padx=(7, 0))

            toggle = tk.Button(
                card,
                text="Pausar" if enabled_value else "Activar",
                command=lambda sid=schedule["id"], state=enabled_value: self._toggle_schedule_v23(sid, not state),
                bg=SURFACE,
                fg=MUTED if enabled_value else GREEN,
                activebackground="#eef2f6",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=7,
            )
            toggle.pack(side="right", padx=12)

    def _toggle_schedule_v23(self, schedule_id, enabled):
        self._toggle_schedule(schedule_id, enabled)
        self._refresh_scheduler_page()


if __name__ == "__main__":
    app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

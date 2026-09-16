import math
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_v2
import app_v3  # aplica el login QR corregido sobre SetupDialog
from local_mapping import LocalMapStore
from version import APP_NAME, VERSION

# Interfaz inspirada en la organización visual de Xiaomi Home, sin copiar assets.
APP_BG = "#f4f5f7"
CARD = "#ffffff"
CARD_ALT = "#f8f9fb"
TEXT = "#17181a"
MUTED = "#7b8088"
BORDER = "#e8eaed"
ACCENT = "#ff6900"
ACCENT_SOFT = "#fff1e7"
BLUE = "#3a8dde"
BLUE_SOFT = "#dceeff"
GREEN = "#25a96b"
RED = "#e74c5b"
SHADOW = "#e7e8ea"
MAP_BG = "#f7f9fb"
MAP_FLOOR = "#dbefff"
MAP_PATH = "#76b9ef"

# El diálogo de configuración del módulo base adopta la misma paleta clara.
app_v2.BG = APP_BG
app_v2.PANEL = CARD
app_v2.PANEL_2 = CARD_ALT
app_v2.TEXT = TEXT
app_v2.MUTED = MUTED
app_v2.ACCENT = ACCENT
app_v2.GREEN = GREEN
app_v2.RED = RED


class App(app_v2.App):
    def __init__(self):
        self.local_map = None
        self.map_polling = False
        self.mapping_active = False
        self.mapping_seen_moving = False
        self.selected_point = None
        self.room_edit_mode = False
        self.room_drag_start = None
        self.room_drag_item = None
        self._map_transforms = {}
        self._nav_buttons = {}
        self._pages = {}
        super().__init__()
        self.local_map = LocalMapStore(self.store.folder)
        self.after(250, self._render_maps)

    # ------------------------------------------------------------------ UI
    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Vacuum.Horizontal.TProgressbar",
            troughcolor="#edf0f2",
            background=ACCENT,
            bordercolor="#edf0f2",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=8,
        )
        style.configure(
            "TCombobox",
            fieldbackground=CARD_ALT,
            background=CARD_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
        )

    def _button(self, parent, text, command, accent=False, compact=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else CARD_ALT,
            fg="white" if accent else TEXT,
            activebackground="#ea5f00" if accent else "#eceef1",
            activeforeground="white" if accent else TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9 if compact else 10, "bold"),
            padx=13 if compact else 16,
            pady=7 if compact else 10,
        )

    def _build_ui(self):
        self.title(f"{APP_NAME} · {VERSION}")
        self.geometry("1260x790")
        self.minsize(1080, 690)
        self.configure(bg=APP_BG)

        self.mode_var = tk.StringVar(value="Aspirar")
        self.suction_var = tk.IntVar(value=max(1, min(4, int(self.settings.get("suction", 2) or 2))))
        self.water_var = tk.IntVar(value=max(0, min(3, int(self.settings.get("mop_water_level", 1) or 1))))
        self.mop_enabled_var = tk.BooleanVar(value=bool(self.settings.get("mop_enabled", False)))

        shell = tk.Frame(self, bg=APP_BG)
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, bg=CARD, width=190, highlightthickness=1, highlightbackground=BORDER)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=CARD)
        brand.pack(fill="x", padx=18, pady=(22, 28))
        logo = tk.Canvas(brand, width=36, height=36, bg=CARD, highlightthickness=0)
        logo.pack(side="left")
        logo.create_rectangle(2, 2, 34, 34, fill=ACCENT, outline=ACCENT)
        logo.create_text(18, 18, text="mi", fill="white", font=("Segoe UI", 11, "bold"))
        text_box = tk.Frame(brand, bg=CARD)
        text_box.pack(side="left", padx=10)
        tk.Label(text_box, text="Mi Vacuum", bg=CARD, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(text_box, text="E10 · PC", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")

        nav = tk.Frame(self.sidebar, bg=CARD)
        nav.pack(fill="x", padx=10)
        self._nav_button(nav, "Inicio", "home")
        self._nav_button(nav, "Mapa local", "map")
        self._nav_button(nav, "Robot", "robot")
        self._nav_button(nav, "Ajustes", "settings")

        footer = tk.Frame(self.sidebar, bg=CARD)
        footer.pack(side="bottom", fill="x", padx=18, pady=18)
        tk.Label(footer, text=f"v{VERSION}", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        tk.Label(footer, text="Windows · control local", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        content = tk.Frame(shell, bg=APP_BG)
        content.pack(side="left", fill="both", expand=True)

        header = tk.Frame(content, bg=APP_BG)
        header.pack(fill="x", padx=28, pady=(20, 8))
        self.page_title = tk.Label(header, text="Inicio", bg=APP_BG, fg=TEXT, font=("Segoe UI", 22, "bold"))
        self.page_title.pack(side="left")

        right = tk.Frame(header, bg=APP_BG)
        right.pack(side="right")
        self.battery_header = tk.Label(right, text="Batería —", bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold"), padx=12, pady=7)
        self.battery_header.pack(side="left", padx=(0, 8))
        self.connection_dot = tk.Label(right, text="●", bg=APP_BG, fg=RED, font=("Segoe UI", 13))
        self.connection_dot.pack(side="left", padx=(0, 5))
        self.connection_label = tk.Label(right, text="Desconectado", bg=APP_BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.connection_label.pack(side="left", padx=(0, 12))
        self._button(right, "Configurar", self.open_setup, compact=True).pack(side="left")

        self.banner = tk.Label(content, text="", bg=APP_BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.banner.pack(fill="x", padx=30, pady=(0, 8))

        self.page_container = tk.Frame(content, bg=APP_BG)
        self.page_container.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self._build_home_page()
        self._build_map_page()
        self._build_robot_page()
        self._build_settings_page()
        self.show_page("home")

    def _nav_button(self, parent, text, page):
        btn = tk.Button(
            parent,
            text=text,
            command=lambda p=page: self.show_page(p),
            bg=CARD,
            fg=MUTED,
            activebackground=ACCENT_SOFT,
            activeforeground=ACCENT,
            relief="flat",
            bd=0,
            anchor="w",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=11,
        )
        btn.pack(fill="x", pady=2)
        self._nav_buttons[page] = btn

    def show_page(self, page):
        titles = {"home": "Inicio", "map": "Mapa local", "robot": "Robot", "settings": "Ajustes"}
        frame = self._pages.get(page)
        if not frame:
            return
        frame.tkraise()
        self.page_title.configure(text=titles.get(page, page))
        for key, btn in self._nav_buttons.items():
            selected = key == page
            btn.configure(bg=ACCENT_SOFT if selected else CARD, fg=ACCENT if selected else MUTED)
        if page in ("home", "map"):
            self.after(50, self._render_maps)

    def _page(self, name):
        frame = tk.Frame(self.page_container, bg=APP_BG)
        frame.grid(row=0, column=0, sticky="nsew")
        self._pages[name] = frame
        return frame

    def _card(self, parent, title, initial):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(side="left", fill="x", expand=True, padx=5)
        tk.Label(card, text=title, bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=15, pady=(11, 2))
        value = tk.Label(card, text=initial, bg=CARD, fg=TEXT, font=("Segoe UI", 17, "bold"))
        value.pack(anchor="w", padx=15, pady=(0, 12))
        return value

    def _build_home_page(self):
        page = self._page("home")
        stats = tk.Frame(page, bg=APP_BG)
        stats.pack(fill="x", pady=(0, 12))
        self.status_value = self._card(stats, "ESTADO", "—")
        self.battery_value = self._card(stats, "BATERÍA", "—")
        self.area_value = self._card(stats, "ÁREA", "—")
        self.time_value = self._card(stats, "TIEMPO", "—")

        body = tk.Frame(page, bg=APP_BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        map_card = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        map_card.grid(row=0, column=0, sticky="nsew", padx=(5, 7))
        map_head = tk.Frame(map_card, bg=CARD)
        map_head.pack(fill="x", padx=18, pady=(15, 8))
        tk.Label(map_head, text="Mapa local", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(map_head, text="PC · LAN", bg=BLUE_SOFT, fg=BLUE, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="left", padx=9)
        self._button(map_head, "Abrir mapa", lambda: self.show_page("map"), compact=True).pack(side="right")

        self.home_map_canvas = tk.Canvas(map_card, bg=MAP_BG, highlightthickness=0)
        self.home_map_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        foot = tk.Frame(map_card, bg=CARD)
        foot.pack(fill="x", padx=16, pady=(0, 13))
        self.map_points_label = tk.Label(foot, text="Todavía no hay un mapa local", bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.map_points_label.pack(side="left")
        self.mapping_badge = tk.Label(foot, text="", bg=CARD, fg=ACCENT, font=("Segoe UI", 8, "bold"))
        self.mapping_badge.pack(side="right")

        controls = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        controls.grid(row=0, column=1, sticky="nsew", padx=(7, 5))
        tk.Label(controls, text="Limpieza", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(17, 8))

        circle = tk.Canvas(controls, width=118, height=118, bg=CARD, highlightthickness=0)
        circle.pack(pady=(0, 8))
        circle.create_oval(10, 10, 108, 108, fill=ACCENT_SOFT, outline="")
        circle.create_oval(31, 31, 87, 87, fill="white", outline=ACCENT, width=2)
        circle.create_text(59, 59, text="E10", fill=ACCENT, font=("Segoe UI", 13, "bold"))

        self.clean_action_button = self._button(controls, "Iniciar limpieza", self.start_clean, accent=True)
        self.clean_action_button.pack(fill="x", padx=20, pady=(0, 12))

        tk.Label(controls, text="Modo", bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20)
        mode_row = tk.Frame(controls, bg=CARD)
        mode_row.pack(fill="x", padx=20, pady=(6, 12))
        self.mode_buttons = {}
        for label in ("Aspirar", "Aspirar + trapear", "Trapear"):
            btn = tk.Button(mode_row, text=label, command=lambda x=label: self._select_mode(x), relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 8, "bold"), padx=7, pady=7)
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.mode_buttons[label] = btn

        mop_row = tk.Frame(controls, bg=CARD)
        mop_row.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(mop_row, text="Mopa", bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.mop_toggle = tk.Button(mop_row, command=self._toggle_mop, relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 8, "bold"), padx=10, pady=5)
        self.mop_toggle.pack(side="right")

        tk.Label(controls, text="Succión", bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20)
        suction_row = tk.Frame(controls, bg=CARD)
        suction_row.pack(fill="x", padx=20, pady=(5, 10))
        self.suction_buttons = {}
        for value, label in ((1, "Silencio"), (2, "Normal"), (3, "Fuerte"), (4, "Turbo")):
            btn = tk.Button(suction_row, text=label, command=lambda v=value: self._choose_suction(v), relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 8, "bold"), padx=6, pady=6)
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.suction_buttons[value] = btn

        tk.Label(controls, text="Agua", bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20)
        water_row = tk.Frame(controls, bg=CARD)
        water_row.pack(fill="x", padx=20, pady=(5, 12))
        self.water_buttons = {}
        for value, label in ((0, "Off"), (1, "Baja"), (2, "Media"), (3, "Alta")):
            btn = tk.Button(water_row, text=label, command=lambda v=value: self._choose_water(v), relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 8, "bold"), padx=6, pady=6)
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.water_buttons[value] = btn

        actions = tk.Frame(controls, bg=CARD)
        actions.pack(fill="x", padx=20, pady=(0, 18))
        self._button(actions, "Detener", self.stop_clean, compact=True).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._button(actions, "Volver a base", self.dock, compact=True).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self._refresh_choice_buttons()

    def _build_map_page(self):
        page = self._page("map")
        body = tk.Frame(page, bg=APP_BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=4)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(5, 7))
        head = tk.Frame(left, bg=CARD)
        head.pack(fill="x", padx=18, pady=(15, 8))
        title_box = tk.Frame(head, bg=CARD)
        title_box.pack(side="left")
        tk.Label(title_box, text="Mapa creado por esta PC", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(title_box, text="No descarga la imagen de Mi Home ni de Xiaomi Cloud.", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        self._button(head, "Crear desde cero", self.start_new_mapping, accent=True, compact=True).pack(side="right", padx=(8, 0))
        self._button(head, "Finalizar", self.finish_mapping, compact=True).pack(side="right")

        self.map_canvas = tk.Canvas(left, bg=MAP_BG, highlightthickness=0, cursor="crosshair")
        self.map_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.map_canvas.bind("<ButtonPress-1>", self._map_press)
        self.map_canvas.bind("<B1-Motion>", self._map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._map_release)
        self.map_canvas.bind("<Configure>", lambda _e: self.after(40, self._render_maps))

        tools = tk.Frame(left, bg=CARD)
        tools.pack(fill="x", padx=16, pady=(0, 14))
        self.map_status_label = tk.Label(tools, text="Mapa local listo", bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.map_status_label.pack(side="left")
        self._button(tools, "Añadir habitación", self.enable_room_editor, compact=True).pack(side="right")

        side = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        side.grid(row=0, column=1, sticky="nsew", padx=(7, 5))
        tk.Label(side, text="Enviar robot", bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(side, text="Hacé clic en un punto del mapa para limpiarlo.", bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=250, justify="left").pack(anchor="w", padx=18)
        self.point_label = tk.Label(side, text="Ningún punto seleccionado", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.point_label.pack(anchor="w", padx=18, pady=(10, 6))
        self.point_clean_button = self._button(side, "Limpiar aquí", self.clean_selected_point, accent=True)
        self.point_clean_button.configure(state="disabled")
        self.point_clean_button.pack(fill="x", padx=18, pady=(0, 14))

        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=18, pady=4)
        tk.Label(side, text="Habitaciones locales", bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(12, 3))
        tk.Label(side, text="Dibujalas sobre el mapa y quedan guardadas sólo en esta PC.", bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=250, justify="left").pack(anchor="w", padx=18, pady=(0, 8))
        self.rooms_frame = tk.Frame(side, bg=CARD)
        self.rooms_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=18, pady=4)
        self._button(side, "Borrar mapa local", self.clear_local_map, compact=True).pack(fill="x", padx=18, pady=(10, 16))

    def _build_robot_page(self):
        page = self._page("robot")
        body = tk.Frame(page, bg=APP_BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        info = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        info.grid(row=0, column=0, sticky="nsew", padx=(5, 7))
        tk.Label(info, text="Estado del robot", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 12))
        self.mode_info = self._info_row(info, "Modo", "—")
        self.deposit_info = self._info_row(info, "Depósito", "—")
        self.mop_info = self._info_row(info, "Mopa física", "—")
        self.fault_info = self._info_row(info, "Error", "—")
        tk.Frame(info, bg=BORDER, height=1).pack(fill="x", padx=20, pady=16)
        tk.Label(info, text="Consumibles", bg=CARD, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(0, 8))
        self.side_brush_info = self._progress_row(info, "Cepillo lateral")
        self.main_brush_info = self._progress_row(info, "Cepillo principal")
        self.hepa_info = self._progress_row(info, "Filtro HEPA")
        self.mop_life_info = self._progress_row(info, "Mopa")
        self._button(info, "Hacer sonar", self.locate, compact=True).pack(anchor="w", padx=20, pady=18)

        manual = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        manual.grid(row=0, column=1, sticky="nsew", padx=(7, 5))
        tk.Label(manual, text="Control manual", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(manual, text="Mantené apretada una dirección para mover el E10.", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=20)
        pad = tk.Frame(manual, bg=CARD)
        pad.pack(expand=True)
        self._manual_pad_button(pad, "↑", 1).grid(row=0, column=1, padx=7, pady=7)
        self._manual_pad_button(pad, "←", 2).grid(row=1, column=0, padx=7, pady=7)
        self._manual_pad_button(pad, "■", 5).grid(row=1, column=1, padx=7, pady=7)
        self._manual_pad_button(pad, "→", 3).grid(row=1, column=2, padx=7, pady=7)
        self._manual_pad_button(pad, "↓", 4).grid(row=2, column=1, padx=7, pady=7)

    def _build_settings_page(self):
        page = self._page("settings")
        card = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=5)
        tk.Label(card, text="Conexión y aplicación", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 6))
        tk.Label(card, text="El control y el mapa local funcionan dentro de tu red. Xiaomi sólo se usa durante la vinculación para obtener el token si elegís QR.", bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=720, justify="left").pack(anchor="w", padx=20, pady=(0, 14))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=20, pady=(0, 18))
        self._button(row, "Configurar robot", self.open_setup, accent=True).pack(side="left")
        self._button(row, "Buscar actualización", self._schedule_update_check).pack(side="left", padx=8)
        self.settings_map_label = tk.Label(card, text="Mapa local: —", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.settings_map_label.pack(anchor="w", padx=20, pady=(0, 18))

    def _info_row(self, parent, label, initial):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=20, pady=5)
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        value = tk.Label(row, text=initial, bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold"))
        value.pack(side="right")
        return value

    def _progress_row(self, parent, label):
        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill="x", padx=20, pady=6)
        row = tk.Frame(wrap, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        value = tk.Label(row, text="—", bg=CARD, fg=TEXT, font=("Segoe UI", 8, "bold"))
        value.pack(side="right")
        bar = ttk.Progressbar(wrap, maximum=100, style="Vacuum.Horizontal.TProgressbar")
        bar.pack(fill="x", pady=(4, 0))
        return value, bar

    def _manual_pad_button(self, parent, text, direction):
        btn = tk.Button(parent, text=text, bg=CARD_ALT, fg=TEXT, activebackground=ACCENT_SOFT, activeforeground=ACCENT, relief="flat", bd=0, width=5, height=2, font=("Segoe UI", 16, "bold"), cursor="hand2")
        btn.bind("<ButtonPress-1>", lambda _e: self.manual(direction))
        btn.bind("<ButtonRelease-1>", lambda _e: self.manual(5))
        return btn

    # -------------------------------------------------------------- controls
    def _select_mode(self, label):
        self.mode_var.set(label)
        if label in ("Aspirar + trapear", "Trapear"):
            self.mop_enabled_var.set(True)
            if self.water_var.get() == 0:
                self.water_var.set(max(1, int(self.settings.get("mop_water_level", 1) or 1)))
        elif label == "Aspirar":
            self.mop_enabled_var.set(False)
            self.water_var.set(0)
        self._save_clean_preferences()
        self._refresh_choice_buttons()

    def _toggle_mop(self):
        enabled = not self.mop_enabled_var.get()
        self.mop_enabled_var.set(enabled)
        if enabled:
            if self.mode_var.get() == "Aspirar":
                self.mode_var.set("Aspirar + trapear")
            if self.water_var.get() == 0:
                self.water_var.set(max(1, int(self.settings.get("mop_water_level", 1) or 1)))
        else:
            self.mode_var.set("Aspirar")
            self.water_var.set(0)
        self._save_clean_preferences()
        self._refresh_choice_buttons()
        if self.vacuum:
            level = max(1, int(self.settings.get("mop_water_level", 1) or 1))
            self._run_command("Configurando mopa…", lambda: self.vacuum.set_mop_enabled(enabled, level))

    def _choose_suction(self, value):
        self.suction_var.set(int(value))
        self.settings["suction"] = int(value)
        self.store.save(self.settings)
        self._refresh_choice_buttons()
        if self.vacuum and not self.mapping_active:
            self.set_suction(int(value))

    def _choose_water(self, value):
        value = int(value)
        if value > 0:
            self.mop_enabled_var.set(True)
            self.settings["mop_water_level"] = value
            if self.mode_var.get() == "Aspirar":
                self.mode_var.set("Aspirar + trapear")
        else:
            self.mop_enabled_var.set(False)
            self.mode_var.set("Aspirar")
        self.water_var.set(value)
        self._save_clean_preferences()
        self._refresh_choice_buttons()
        if self.vacuum and not self.mapping_active:
            self.set_water(value)

    def _save_clean_preferences(self):
        self.settings["mop_enabled"] = bool(self.mop_enabled_var.get())
        self.settings["mop_water_level"] = int(self.water_var.get())
        self.settings["suction"] = int(self.suction_var.get())
        self.store.save(self.settings)

    def _refresh_choice_buttons(self):
        if hasattr(self, "mode_buttons"):
            for label, btn in self.mode_buttons.items():
                selected = label == self.mode_var.get()
                btn.configure(bg=ACCENT_SOFT if selected else CARD_ALT, fg=ACCENT if selected else MUTED)
        if hasattr(self, "suction_buttons"):
            for value, btn in self.suction_buttons.items():
                selected = value == self.suction_var.get()
                btn.configure(bg=ACCENT_SOFT if selected else CARD_ALT, fg=ACCENT if selected else MUTED)
        if hasattr(self, "water_buttons"):
            for value, btn in self.water_buttons.items():
                selected = value == self.water_var.get()
                btn.configure(bg=BLUE_SOFT if selected else CARD_ALT, fg=BLUE if selected else MUTED)
        if hasattr(self, "mop_toggle"):
            enabled = self.mop_enabled_var.get()
            self.mop_toggle.configure(text="Activada" if enabled else "Desactivada", bg=BLUE_SOFT if enabled else CARD_ALT, fg=BLUE if enabled else MUTED)

    def start_clean(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el Xiaomi Vacuum E10.")
            return

        mode = {"Aspirar": 0, "Aspirar + trapear": 1, "Trapear": 2}.get(self.mode_var.get(), 0)
        if not self.mop_enabled_var.get():
            mode = 0

        def command():
            self.vacuum.set_suction(int(self.suction_var.get()))
            if mode == 0:
                self.vacuum.set_water(0)
            else:
                self.vacuum.set_water(max(1, int(self.water_var.get())))
            return self.vacuum.start(mode)

        self._run_command("Iniciando limpieza…", command)

    # -------------------------------------------------------------- local map
    def _on_connected(self, ip):
        super()._on_connected(ip)
        self._start_local_map_polling()

    def _start_local_map_polling(self):
        if self.map_polling:
            return
        self.map_polling = True
        self._poll_local_map()

    def _poll_local_map(self):
        if not self.vacuum:
            self.map_polling = False
            return

        def worker():
            try:
                state = self.vacuum.local_map_state()
                if self.local_map:
                    if self.mapping_active and state.get("path"):
                        self.local_map.merge_trajectory(state["path"])
                    self.local_map.set_robot(state.get("robot"))
                    self.local_map.set_charging_base(state.get("charging_base"))
                    self.after(0, self._render_maps)
            except Exception as exc:
                self.after(0, lambda: self.map_status_label.configure(text=f"Telemetría de mapa: {str(exc)[:90]}", fg=RED) if hasattr(self, "map_status_label") else None)
            finally:
                try:
                    if self.winfo_exists() and self.vacuum:
                        self.after(1800, self._poll_local_map)
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
            "Se va a borrar solamente el mapa guardado por esta aplicación en la PC.\n\n"
            "El E10 recorrerá la vivienda con agua y succión apagadas mientras la PC registra su trayectoria. "
            "No se descarga el mapa de Mi Home ni se borra el mapa de Xiaomi.",
            parent=self,
        )
        if not ok:
            return
        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_seen_moving = False
        self._render_maps()
        self._run_command("Iniciando recorrido de mapeo local…", self.vacuum.start_mapping_run)

    def finish_mapping(self):
        if not self.mapping_active:
            self._set_banner("El mapa local ya está guardado en esta PC.")
            return
        self.mapping_active = False
        self.mapping_seen_moving = False
        self._render_maps()
        if self.vacuum:
            self._run_command("Finalizando recorrido de mapeo…", self.vacuum.stop)

    def clear_local_map(self):
        if not self.local_map:
            return
        if not messagebox.askyesno("Borrar mapa local", "¿Borrar el mapa y las habitaciones guardadas en esta PC?", parent=self):
            return
        self.mapping_active = False
        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self._render_maps()

    def _render_maps(self):
        if not self.local_map:
            return
        snapshot = self.local_map.snapshot()
        for canvas in (getattr(self, "home_map_canvas", None), getattr(self, "map_canvas", None)):
            if canvas and canvas.winfo_exists():
                self._render_map_canvas(canvas, snapshot)
        points = snapshot.get("points", [])
        rooms = snapshot.get("rooms", [])
        if hasattr(self, "map_points_label"):
            if points:
                self.map_points_label.configure(text=f"{len(points)} puntos de recorrido · {len(rooms)} habitaciones locales")
            else:
                self.map_points_label.configure(text="Creá un mapa nuevo para empezar")
        if hasattr(self, "mapping_badge"):
            self.mapping_badge.configure(text="MAPEANDO" if self.mapping_active else "")
        if hasattr(self, "map_status_label"):
            self.map_status_label.configure(text="Mapeando en vivo…" if self.mapping_active else ("Mapa local guardado" if points else "Sin mapa local"), fg=ACCENT if self.mapping_active else MUTED)
        if hasattr(self, "settings_map_label"):
            self.settings_map_label.configure(text=f"Mapa local: {len(points)} puntos · {len(rooms)} habitaciones")
        self._refresh_room_list(snapshot)

    def _render_map_canvas(self, canvas, snapshot):
        canvas.delete("all")
        cw = max(300, canvas.winfo_width())
        ch = max(250, canvas.winfo_height())
        points = snapshot.get("points", []) or []
        rooms = snapshot.get("rooms", []) or []
        robot = snapshot.get("robot")
        base = snapshot.get("charging_base")

        coords = []
        for p in points:
            coords.append((float(p["x"]), float(p["y"])))
        for room in rooms:
            coords.extend([(float(room["x0"]), float(room["y0"])), (float(room["x1"]), float(room["y1"]))])
        for p in (robot, base):
            if p:
                coords.append((float(p["x"]), float(p["y"])))

        if not coords:
            canvas.create_text(cw / 2, ch / 2 - 10, text="Todavía no hay mapa", fill=MUTED, font=("Segoe UI", 14, "bold"))
            canvas.create_text(cw / 2, ch / 2 + 18, text="Usá “Crear desde cero” para que el E10 recorra la casa.", fill=MUTED, font=("Segoe UI", 9))
            self._map_transforms[canvas] = None
            return

        min_x = min(x for x, _ in coords)
        max_x = max(x for x, _ in coords)
        min_y = min(y for _, y in coords)
        max_y = max(y for _, y in coords)
        if max_x - min_x < 0.8:
            min_x -= 0.4
            max_x += 0.4
        if max_y - min_y < 0.8:
            min_y -= 0.4
            max_y += 0.4
        margin_world = 0.45
        min_x -= margin_world
        max_x += margin_world
        min_y -= margin_world
        max_y += margin_world
        pad = 28
        scale = min((cw - pad * 2) / max(0.01, max_x - min_x), (ch - pad * 2) / max(0.01, max_y - min_y))
        self._map_transforms[canvas] = {"min_x": min_x, "max_y": max_y, "scale": scale, "pad": pad}

        def to_screen(x, y):
            return pad + (x - min_x) * scale, pad + (max_y - y) * scale

        # Grilla métrica tenue.
        if scale >= 35:
            first_x = math.floor(min_x)
            last_x = math.ceil(max_x)
            for gx in range(first_x, last_x + 1):
                sx, _ = to_screen(gx, min_y)
                canvas.create_line(sx, pad, sx, ch - pad, fill="#eef1f4")
            first_y = math.floor(min_y)
            last_y = math.ceil(max_y)
            for gy in range(first_y, last_y + 1):
                _, sy = to_screen(min_x, gy)
                canvas.create_line(pad, sy, cw - pad, sy, fill="#eef1f4")

        # La huella ancha del recorrido genera el plano local aproximado del piso.
        if len(points) >= 2:
            segments = []
            current = [points[0]]
            for p in points[1:]:
                prev = current[-1]
                distance = math.hypot(float(p["x"]) - float(prev["x"]), float(p["y"]) - float(prev["y"]))
                if distance > 1.25:
                    if len(current) > 1:
                        segments.append(current)
                    current = [p]
                else:
                    current.append(p)
            if len(current) > 1:
                segments.append(current)

            floor_width = max(10, min(70, int(scale * 0.34)))
            for segment in segments:
                line = []
                for p in segment:
                    line.extend(to_screen(float(p["x"]), float(p["y"])))
                if len(line) >= 4:
                    canvas.create_line(*line, fill=MAP_FLOOR, width=floor_width, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                    canvas.create_line(*line, fill=MAP_PATH, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        elif len(points) == 1:
            x, y = to_screen(float(points[0]["x"]), float(points[0]["y"]))
            r = max(8, int(scale * 0.17))
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=MAP_FLOOR, outline="")

        # Habitaciones creadas por el usuario.
        for room in rooms:
            x0, y1 = to_screen(float(room["x0"]), float(room["y0"]))
            x1, y0 = to_screen(float(room["x1"]), float(room["y1"]))
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            canvas.create_rectangle(left, top, right, bottom, outline=BLUE, width=2, fill="#eaf4ff", stipple="gray25")
            canvas.create_text((left + right) / 2, (top + bottom) / 2, text=room.get("name", "Habitación"), fill=TEXT, font=("Segoe UI", 8, "bold"))

        if base:
            x, y = to_screen(float(base["x"]), float(base["y"]))
            canvas.create_rectangle(x - 7, y - 7, x + 7, y + 7, fill="#30343a", outline="white", width=2)
            canvas.create_text(x, y - 15, text="Base", fill=MUTED, font=("Segoe UI", 7, "bold"))
        if robot:
            x, y = to_screen(float(robot["x"]), float(robot["y"]))
            canvas.create_oval(x - 9, y - 9, x + 9, y + 9, fill=ACCENT, outline="white", width=3)

        if canvas is getattr(self, "map_canvas", None) and self.selected_point:
            x, y = to_screen(self.selected_point[0], self.selected_point[1])
            canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline=ACCENT, width=3)
            canvas.create_line(x - 12, y, x + 12, y, fill=ACCENT, width=2)
            canvas.create_line(x, y - 12, x, y + 12, fill=ACCENT, width=2)

    def _canvas_to_world(self, canvas, x, y):
        transform = self._map_transforms.get(canvas)
        if not transform:
            return None
        scale = transform["scale"]
        world_x = transform["min_x"] + (float(x) - transform["pad"]) / scale
        world_y = transform["max_y"] - (float(y) - transform["pad"]) / scale
        return world_x, world_y

    def _map_press(self, event):
        if self.room_edit_mode:
            self.room_drag_start = (event.x, event.y)
            if self.room_drag_item:
                self.map_canvas.delete(self.room_drag_item)
            self.room_drag_item = self.map_canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=ACCENT, width=2, dash=(5, 3))

    def _map_drag(self, event):
        if self.room_edit_mode and self.room_drag_start and self.room_drag_item:
            x0, y0 = self.room_drag_start
            self.map_canvas.coords(self.room_drag_item, x0, y0, event.x, event.y)

    def _map_release(self, event):
        if self.room_edit_mode and self.room_drag_start:
            start = self._canvas_to_world(self.map_canvas, *self.room_drag_start)
            end = self._canvas_to_world(self.map_canvas, event.x, event.y)
            self.room_edit_mode = False
            self.room_drag_start = None
            if self.room_drag_item:
                self.map_canvas.delete(self.room_drag_item)
                self.room_drag_item = None
            if not start or not end:
                return
            if abs(start[0] - end[0]) < 0.18 or abs(start[1] - end[1]) < 0.18:
                self._set_banner("La habitación dibujada es demasiado pequeña.")
                return
            name = simpledialog.askstring("Nueva habitación", "Nombre de la habitación:", parent=self)
            if name is None:
                return
            self.local_map.add_room(name, start[0], start[1], end[0], end[1])
            self._render_maps()
            return

        point = self._canvas_to_world(self.map_canvas, event.x, event.y)
        if point:
            self.selected_point = point
            self.point_label.configure(text=f"x {point[0]:.2f} · y {point[1]:.2f}")
            self.point_clean_button.configure(state="normal")
            self._render_maps()

    def enable_room_editor(self):
        if not self.local_map or not self.local_map.snapshot().get("points"):
            messagebox.showinfo("Mapa local", "Primero creá un mapa local.", parent=self)
            return
        self.room_edit_mode = True
        self._set_banner("Arrastrá un rectángulo sobre el mapa para definir la habitación.")

    def clean_selected_point(self):
        if not self.selected_point or not self.vacuum:
            return
        x, y = self.selected_point
        self._run_command("Enviando el E10 al punto seleccionado…", lambda: self.vacuum.clean_point(x, y))

    def _refresh_room_list(self, snapshot):
        if not hasattr(self, "rooms_frame"):
            return
        for child in self.rooms_frame.winfo_children():
            child.destroy()
        rooms = snapshot.get("rooms", []) if snapshot else []
        if not rooms:
            tk.Label(self.rooms_frame, text="No hay habitaciones.\nUsá “Añadir habitación” y dibujá una zona.", bg=CARD, fg=MUTED, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=8)
            return
        for room in rooms:
            row = tk.Frame(self.rooms_frame, bg=CARD_ALT)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=room.get("name", "Habitación"), bg=CARD_ALT, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True, padx=9, pady=8)
            tk.Button(row, text="Limpiar", command=lambda r=dict(room): self.clean_local_room(r), bg=ACCENT_SOFT, fg=ACCENT, activebackground=ACCENT_SOFT, relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 8, "bold"), padx=7, pady=5).pack(side="left", padx=3)
            tk.Button(row, text="×", command=lambda rid=room["id"]: self.delete_local_room(rid), bg=CARD_ALT, fg=MUTED, activebackground="#f1f2f4", relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 11, "bold"), padx=7).pack(side="right", padx=4)

    def clean_local_room(self, room):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.")
            return
        self._run_command(
            f"Limpiando {room.get('name', 'habitación')}…",
            lambda: self.vacuum.clean_zone(room["x0"], room["y0"], room["x1"], room["y1"]),
        )

    def delete_local_room(self, room_id):
        if messagebox.askyesno("Eliminar habitación", "¿Eliminar esta habitación del mapa local?", parent=self):
            self.local_map.delete_room(room_id)
            self._render_maps()

    # --------------------------------------------------------------- status
    def _render_status(self, s):
        self.status_value.configure(text=s.status_name)
        self.battery_value.configure(text=f"{s.battery}%")
        self.battery_header.configure(text=f"Batería {s.battery}%")
        self.area_value.configure(text=f"{s.cleaning_area} m²")
        self.time_value.configure(text=f"{s.cleaning_time} min")
        self.mode_info.configure(text=s.mode_name)
        self.deposit_info.configure(text=s.door_name)
        self.mop_info.configure(text=s.cloth_name)
        self.fault_info.configure(text="Sin errores" if s.fault == 0 else f"Código {s.fault}", fg=TEXT if s.fault == 0 else RED)

        for widget, remaining in [
            (self.side_brush_info, s.side_brush_life),
            (self.main_brush_info, s.main_brush_life),
            (self.hepa_info, s.hepa_life),
            (self.mop_life_info, s.mop_life),
        ]:
            label, bar = widget
            label.configure(text=f"{remaining}%")
            bar["value"] = remaining

        if self.mapping_active and s.status in (5, 6, 7):
            self.mapping_seen_moving = True
        if self.mapping_active and self.mapping_seen_moving and s.status in (1, 4):
            self.mapping_active = False
            self.mapping_seen_moving = False
            self._set_banner("Mapeo local terminado. El plano quedó guardado en esta PC.")
            self._render_maps()

        if not self.mapping_active:
            if 1 <= int(s.suction or 0) <= 4:
                self.suction_var.set(int(s.suction))
            if 0 <= int(s.water or 0) <= 3:
                self.water_var.set(int(s.water))
            self._refresh_choice_buttons()

        self._set_connection(True, f"Conectado · {self.settings.get('ip', '')}")


if __name__ == "__main__":
    App().mainloop()

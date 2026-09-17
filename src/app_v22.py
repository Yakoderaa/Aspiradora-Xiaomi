import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_v21
from version import APP_NAME, VERSION
from windows_integration import apply_window_icon, mi_home_png

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# Lenguaje visual propio: neutro, funcional y sin imitar Xiaomi Home.
BG = "#f5f7fa"
SURFACE = "#ffffff"
SURFACE_2 = "#f8fafc"
SIDEBAR = "#111827"
SIDEBAR_MUTED = "#94a3b8"
TEXT = "#111827"
MUTED = "#64748b"
BORDER = "#e2e8f0"
ACCENT = "#4f46e5"
ACCENT_HOVER = "#4338ca"
ACCENT_SOFT = "#eef2ff"
GREEN = "#16a34a"
GREEN_SOFT = "#ecfdf3"
RED = "#dc2626"
RED_SOFT = "#fef2f2"
BLUE = "#0284c7"
BLUE_SOFT = "#eff6ff"
MAP_BG = "#f8fafc"

MODE_LABELS = {
    "Aspirar": "vacuum",
    "Aspirar + trapear": "vacuum_mop",
    "Trapear": "mop",
    "Aspirar y después trapear": "vacuum_then_mop",
}
DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


class App(app_v21.App):
    """v22: interfaz completamente nueva sobre el backend consolidado."""

    def __init__(self):
        self._brand_photo = None
        self._quick_panel_opened_at = 0.0
        self._settings_inner = None
        self._map_toolbar = None
        self._map_library_slot = None
        self._zone_tools_slot = None
        super().__init__()
        self.title(f"Aspiradora · E10 · {VERSION}")
        apply_window_icon(self)
        self.after(120, lambda: self.show_page("home"))

    # app_v21 aplicaba un restyling sobre la UI anterior. En v22 no existe esa UI.
    def _modernize_widget_tree(self, root):
        return

    def _install_sidebar_logo(self):
        return

    # ---------------------------------------------------------------- theme
    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Vacuum.Horizontal.TProgressbar",
            troughcolor="#edf1f5",
            background=ACCENT,
            bordercolor="#edf1f5",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_2,
            background=SURFACE_2,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowsize=14,
            padding=7,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", SURFACE_2)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", SURFACE_2)],
            selectforeground=[("readonly", TEXT)],
        )

    def _button(self, parent, text, command, accent=False, compact=False, danger=False):
        if danger:
            bg, fg, active, border = RED_SOFT, RED, "#fee2e2", "#fecaca"
        elif accent:
            bg, fg, active, border = ACCENT, "white", ACCENT_HOVER, ACCENT
        else:
            bg, fg, active, border = SURFACE_2, TEXT, "#eef2f6", BORDER
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
            cursor="hand2",
            font=("Segoe UI", 9 if compact else 10, "bold"),
            padx=12 if compact else 16,
            pady=6 if compact else 9,
        )

    def _surface(self, parent, padx=18, pady=16):
        outer = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        inner = tk.Frame(outer, bg=SURFACE, padx=padx, pady=pady)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _section_title(self, parent, title, subtitle=None):
        tk.Label(parent, text=title, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        if subtitle:
            tk.Label(
                parent,
                text=subtitle,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 9),
                justify="left",
                wraplength=760,
            ).pack(anchor="w", pady=(3, 0))

    def _metric_card(self, parent, title, initial, hint=""):
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.pack(side="left", fill="both", expand=True, padx=5)
        tk.Label(card, text=title.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=15, pady=(12, 3)
        )
        value = tk.Label(card, text=initial, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 18))
        value.pack(anchor="w", padx=15)
        tk.Label(card, text=hint, bg=SURFACE, fg=SIDEBAR_MUTED, font=("Segoe UI", 8)).pack(
            anchor="w", padx=15, pady=(2, 12)
        )
        return value

    # --------------------------------------------------------------- shell
    def _build_ui(self):
        self.title(f"{APP_NAME} · {VERSION}")
        self.geometry("1420x880")
        self.minsize(1180, 720)
        self.configure(bg=BG)

        self.mode_var = tk.StringVar(value="Aspirar")
        self.suction_var = tk.IntVar(value=max(1, min(4, int(self.settings.get("suction", 2) or 2))))
        self.water_var = tk.IntVar(value=max(0, min(3, int(self.settings.get("mop_water_level", 1) or 1))))
        self.mop_enabled_var = tk.BooleanVar(value=bool(self.settings.get("mop_enabled", False)))

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, bg=SIDEBAR, width=226)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        content = tk.Frame(shell, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        self._build_topbar(content)

        self.banner = tk.Label(
            content,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.banner.pack(fill="x", padx=28, pady=(0, 8))

        self.page_container = tk.Frame(content, bg=BG)
        self.page_container.pack(fill="both", expand=True, padx=24, pady=(0, 22))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self._pages = {}
        self._nav_buttons = {}
        self._build_home_page_v22()
        self._build_clean_page_v22()
        self._build_map_page_v22()
        self._build_robot_page_v22()
        self._build_settings_page_v22()
        self._page("scheduler")

        self.show_page("home")
        self._refresh_choice_buttons()

    def _build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=18, pady=(20, 28))

        icon_box = tk.Frame(brand, bg="#1f2937", width=42, height=42)
        icon_box.pack(side="left")
        icon_box.pack_propagate(False)
        loaded = False
        if Image is not None and ImageTk is not None:
            try:
                path = mi_home_png()
                if path.exists():
                    image = Image.open(path).convert("RGBA")
                    image.thumbnail((34, 34), Image.Resampling.LANCZOS)
                    self._brand_photo = ImageTk.PhotoImage(image)
                    tk.Label(icon_box, image=self._brand_photo, bg="#1f2937").place(relx=0.5, rely=0.5, anchor="center")
                    loaded = True
            except Exception:
                pass
        if not loaded:
            tk.Label(icon_box, text="E10", bg="#1f2937", fg="white", font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        text = tk.Frame(brand, bg=SIDEBAR)
        text.pack(side="left", padx=11)
        tk.Label(text, text="Aspiradora", bg=SIDEBAR, fg="white", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(text, text="Control del hogar", bg=SIDEBAR, fg=SIDEBAR_MUTED, font=("Segoe UI", 8)).pack(anchor="w")

        nav = tk.Frame(self.sidebar, bg=SIDEBAR)
        nav.pack(fill="x", padx=10)
        for label, page, icon in (
            ("Inicio", "home", "⌂"),
            ("Limpiar", "clean", "◉"),
            ("Mapa", "map", "▦"),
            ("Programar", "scheduler", "◷"),
            ("Robot", "robot", "⌁"),
            ("Ajustes", "settings", "⚙"),
        ):
            self._nav_button_v22(nav, label, page, icon)

        footer = tk.Frame(self.sidebar, bg=SIDEBAR)
        footer.pack(side="bottom", fill="x", padx=18, pady=18)
        tk.Label(footer, text=f"v{VERSION}", bg=SIDEBAR, fg=SIDEBAR_MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        tk.Label(footer, text="Windows · control local", bg=SIDEBAR, fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

    def _nav_button_v22(self, parent, text, page, icon):
        btn = tk.Button(
            parent,
            text=f" {icon}    {text}",
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
            padx=12,
            pady=11,
        )
        btn.pack(fill="x", pady=2)
        self._nav_buttons[page] = btn

    # compatible con constructores heredados que llaman _nav_button
    def _nav_button(self, parent, text, page):
        icons = {"home": "⌂", "clean": "◉", "map": "▦", "scheduler": "◷", "robot": "⌁", "settings": "⚙"}
        if page in self._nav_buttons:
            return self._nav_buttons[page]
        return self._nav_button_v22(parent, text, page, icons.get(page, "•"))

    def _build_topbar(self, parent):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=28, pady=(20, 10))

        self.page_title = tk.Label(top, text="Inicio", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 24))
        self.page_title.pack(side="left")

        right = tk.Frame(top, bg=BG)
        right.pack(side="right")

        self.battery_header = tk.Label(
            right, text="Batería —", bg=SURFACE, fg=TEXT, font=("Segoe UI", 9, "bold"), padx=12, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.battery_header.pack(side="left", padx=(0, 8))

        state = tk.Frame(right, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, padx=10, pady=6)
        state.pack(side="left", padx=(0, 8))
        self.connection_dot = tk.Label(state, text="●", bg=SURFACE, fg=RED, font=("Segoe UI", 11))
        self.connection_dot.pack(side="left", padx=(0, 5))
        self.connection_label = tk.Label(state, text="Desconectado", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.connection_label.pack(side="left")

        self._button(right, "Cuenta", self.open_setup, compact=True).pack(side="left")

    def _page(self, name):
        if name in self._pages:
            return self._pages[name]
        frame = tk.Frame(self.page_container, bg=BG)
        frame.grid(row=0, column=0, sticky="nsew")
        self._pages[name] = frame
        return frame

    def show_page(self, page):
        frame = self._pages.get(page)
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
        self.page_title.configure(text=titles.get(page, page))
        for key, btn in self._nav_buttons.items():
            selected = key == page
            btn.configure(
                bg="#1f2937" if selected else SIDEBAR,
                fg="white" if selected else SIDEBAR_MUTED,
            )
        if page in ("home", "map"):
            self.after(40, self._render_maps)
        if page == "scheduler" and self.plan_store:
            self.after(40, self._refresh_scheduler_page)

    # -------------------------------------------------------------- Inicio
    def _build_home_page_v22(self):
        page = self._page("home")

        metrics = tk.Frame(page, bg=BG)
        metrics.pack(fill="x", pady=(0, 12))
        self.status_value = self._metric_card(metrics, "Estado", "—", "Actividad actual")
        self.battery_value = self._metric_card(metrics, "Batería", "—", "Carga restante")
        self.area_value = self._metric_card(metrics, "Área", "—", "Última limpieza")
        self.time_value = self._metric_card(metrics, "Tiempo", "—", "Última limpieza")

        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        map_outer, map_body = self._surface(body, 16, 14)
        map_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7))
        head = tk.Frame(map_body, bg=SURFACE)
        head.pack(fill="x", pady=(0, 10))
        title = tk.Frame(head, bg=SURFACE)
        title.pack(side="left")
        tk.Label(title, text="Tu mapa", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        self.map_points_label = tk.Label(title, text="Sin mapa todavía", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8))
        self.map_points_label.pack(anchor="w", pady=(2, 0))
        self._button(head, "Abrir mapa", lambda: self.show_page("map"), compact=True).pack(side="right")

        self.home_map_canvas = tk.Canvas(map_body, bg=MAP_BG, highlightthickness=0)
        self.home_map_canvas.pack(fill="both", expand=True)
        self.mapping_badge = tk.Label(map_body, text="", bg=SURFACE, fg=ACCENT, font=("Segoe UI", 8, "bold"))
        self.mapping_badge.pack(anchor="e", pady=(7, 0))

        side = tk.Frame(body, bg=BG)
        side.grid(row=0, column=1, sticky="nsew", padx=(7, 5))

        quick_outer, quick = self._surface(side, 18, 16)
        quick_outer.pack(fill="x", pady=(0, 10))
        self._section_title(quick, "Acciones rápidas", "Lo habitual, sin entrar en menús.")
        self.clean_action_button = self._button(quick, "Iniciar limpieza", self.start_clean, accent=True)
        self.clean_action_button.pack(fill="x", pady=(16, 7))
        row = tk.Frame(quick, bg=SURFACE)
        row.pack(fill="x")
        self._button(row, "Volver a base", self.dock, compact=True).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._button(row, "Detener", self.stop_clean, compact=True).pack(side="left", fill="x", expand=True, padx=(4, 0))

        map_outer2, map_quick = self._surface(side, 18, 16)
        map_outer2.pack(fill="x")
        self._section_title(map_quick, "Mapeo", "Crear o continuar el plano de la vivienda.")
        self._button(map_quick, "Abrir herramientas de mapa", lambda: self.show_page("map"), accent=True).pack(fill="x", pady=(16, 0))

    # ------------------------------------------------------------- Limpiar
    def _build_clean_page_v22(self):
        page = self._page("clean")
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(0, weight=1)

        left_outer, left = self._surface(page, 22, 20)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)
        self._section_title(left, "Configurar limpieza", "Elegí el modo y la intensidad antes de iniciar.")

        tk.Label(left, text="MODO", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(22, 7))
        mode_row = tk.Frame(left, bg=SURFACE)
        mode_row.pack(fill="x")
        self.mode_buttons = {}
        for label in ("Aspirar", "Aspirar + trapear", "Trapear"):
            btn = self._button(mode_row, label, lambda l=label: self._select_mode(l), compact=True)
            btn.pack(side="left", padx=(0, 7))
            self.mode_buttons[label] = btn

        tk.Label(left, text="SUCCIÓN", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(22, 7))
        suction = tk.Frame(left, bg=SURFACE)
        suction.pack(fill="x")
        self.suction_buttons = {}
        for value, label in ((1, "Silenciosa"), (2, "Normal"), (3, "Fuerte"), (4, "Turbo")):
            btn = self._button(suction, label, lambda v=value: self._choose_suction(v), compact=True)
            btn.pack(side="left", fill="x", expand=True, padx=(0, 6 if value < 4 else 0))
            self.suction_buttons[value] = btn

        tk.Label(left, text="AGUA", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(22, 7))
        water = tk.Frame(left, bg=SURFACE)
        water.pack(fill="x")
        self.water_buttons = {}
        for value, label in ((0, "Sin agua"), (1, "Baja"), (2, "Media"), (3, "Alta")):
            btn = self._button(water, label, lambda v=value: self._choose_water(v), compact=True)
            btn.pack(side="left", fill="x", expand=True, padx=(0, 6 if value < 3 else 0))
            self.water_buttons[value] = btn

        mop_row = tk.Frame(left, bg=SURFACE_2, highlightthickness=1, highlightbackground=BORDER)
        mop_row.pack(fill="x", pady=(22, 0))
        text = tk.Frame(mop_row, bg=SURFACE_2)
        text.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        tk.Label(text, text="Mopa", bg=SURFACE_2, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(text, text="Activala o desactivala rápidamente.", bg=SURFACE_2, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        self.mop_toggle = self._button(mop_row, "Desactivada", self._toggle_mop, compact=True)
        self.mop_toggle.pack(side="right", padx=12)

        action = tk.Frame(left, bg=SURFACE)
        action.pack(fill="x", side="bottom", pady=(22, 0))
        self._button(action, "Iniciar limpieza", self.start_clean, accent=True).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._button(action, "Detener", self.stop_clean).pack(side="left", padx=5)
        self._button(action, "Base", self.dock).pack(side="left", padx=(5, 0))

        right_outer, right = self._surface(page, 20, 18)
        right_outer.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)
        self._section_title(right, "Limpiar por lugar", "Usá zonas guardadas o elegí un punto desde el mapa.")
        self._button(right, "Elegir zonas", self.open_zone_clean_dialog, accent=True).pack(fill="x", pady=(18, 8))
        self._button(right, "Abrir mapa y elegir punto", lambda: self.show_page("map")).pack(fill="x", pady=4)
        self._button(right, "Administrar zonas y puntos", self.open_zone_manager).pack(fill="x", pady=4)

    # ---------------------------------------------------------------- Mapa
    def _build_map_page_v22(self):
        page = self._page("map")
        page.grid_columnconfigure(0, weight=5)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(0, weight=1)

        map_outer = tk.Frame(page, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        map_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)

        head = tk.Frame(map_outer, bg=SURFACE)
        head.pack(fill="x", padx=16, pady=(14, 8))
        title = tk.Frame(head, bg=SURFACE)
        title.pack(side="left")
        tk.Label(title, text="Plano de la vivienda", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        self.map_status_label = tk.Label(title, text="Mapa local listo", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8))
        self.map_status_label.pack(anchor="w", pady=(2, 0))

        mapping_controls = tk.Frame(head, bg=SURFACE)
        mapping_controls.pack(side="right")
        self.stop_mapping_button = self._button(mapping_controls, "Detener", self.finish_mapping, compact=True)
        self.stop_mapping_button.pack(side="right", padx=(6, 0))
        self.step2_mapping_button = self._button(mapping_controls, "Paso 2 · Interior", self.start_interior_mapping, compact=True)
        self.step2_mapping_button.pack(side="right", padx=(6, 0))
        self.step1_mapping_button = self._button(mapping_controls, "Paso 1 · Perímetro", self.start_new_mapping, accent=True, compact=True)
        self.step1_mapping_button.pack(side="right")

        self.map_canvas = tk.Canvas(map_outer, bg=MAP_BG, highlightthickness=0, cursor="fleur")
        self.map_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.map_canvas.bind("<ButtonPress-1>", self._map_press)
        self.map_canvas.bind("<B1-Motion>", self._map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._map_release)
        self.map_canvas.bind("<Double-Button-1>", self._map_double_click)
        self.map_canvas.bind("<Configure>", lambda _e: self.after(35, self._render_maps))

        tools = tk.Frame(map_outer, bg=SURFACE)
        tools.pack(fill="x", padx=14, pady=(0, 12))
        self._map_toolbar = tools
        self.mapping_steps_info = tk.Label(
            tools,
            text="Arrastrar: mover · doble clic: objetivo · Paso 1: paredes · Paso 2: interior",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.mapping_steps_info.pack(side="left")
        self._zone_tools_slot = tk.Frame(tools, bg=SURFACE)
        self._zone_tools_slot.pack(side="right")
        self._map_library_slot = tk.Frame(tools, bg=SURFACE)
        self._map_library_slot.pack(side="right", padx=(0, 6))

        side = tk.Frame(page, bg=BG)
        side.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)

        target_outer, target = self._surface(side, 18, 15)
        target_outer.pack(fill="x", pady=(0, 10))
        self._section_title(target, "Objetivo", "Hacé doble clic en el mapa para marcarlo.")
        self.point_label = tk.Label(target, text="Ningún objetivo seleccionado", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self.point_label.pack(anchor="w", pady=(12, 8))
        self.point_clean_button = self._button(target, "Limpiar aquí", self.clean_selected_point, accent=True)
        self.point_clean_button.configure(state="disabled")
        self.point_clean_button.pack(fill="x")
        self._button(target, "Guardar punto con nombre", self.save_selected_point, compact=True).pack(fill="x", pady=(7, 0))

        room_outer, room = self._surface(side, 18, 15)
        room_outer.pack(fill="both", expand=True)
        top = tk.Frame(room, bg=SURFACE)
        top.pack(fill="x")
        tk.Label(top, text="Habitaciones", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(side="left")
        self._button(top, "+ Añadir", self.enable_room_editor, compact=True).pack(side="right")
        self.rooms_frame = tk.Frame(room, bg=SURFACE)
        self.rooms_frame.pack(fill="both", expand=True, pady=(10, 0))

    # ---------------------------------------------------------------- Robot
    def _build_robot_page_v22(self):
        page = self._page("robot")
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)

        info_outer, info = self._surface(page, 20, 18)
        info_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)
        self._section_title(info, "Estado del robot", "Sensores, depósito y consumibles.")
        self.mode_info = self._info_row_v22(info, "Modo", "—")
        self.deposit_info = self._info_row_v22(info, "Depósito", "—")
        self.mop_info = self._info_row_v22(info, "Mopa física", "—")
        self.fault_info = self._info_row_v22(info, "Error", "—")
        tk.Frame(info, bg=BORDER, height=1).pack(fill="x", pady=16)
        tk.Label(info, text="Consumibles", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 8))
        self.side_brush_info = self._progress_row_v22(info, "Cepillo lateral")
        self.main_brush_info = self._progress_row_v22(info, "Cepillo principal")
        self.hepa_info = self._progress_row_v22(info, "Filtro HEPA")
        self.mop_life_info = self._progress_row_v22(info, "Mopa")
        self._button(info, "Hacer sonar", self.locate, compact=True).pack(anchor="w", pady=(16, 0))

        manual_outer, manual = self._surface(page, 20, 18)
        manual_outer.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)
        self._section_title(manual, "Control manual", "Mantené presionada una dirección para mover el E10.")
        pad = tk.Frame(manual, bg=SURFACE)
        pad.pack(expand=True)
        self._manual_pad_button_v22(pad, "↑", 1).grid(row=0, column=1, padx=7, pady=7)
        self._manual_pad_button_v22(pad, "←", 2).grid(row=1, column=0, padx=7, pady=7)
        self._manual_pad_button_v22(pad, "■", 5).grid(row=1, column=1, padx=7, pady=7)
        self._manual_pad_button_v22(pad, "→", 3).grid(row=1, column=2, padx=7, pady=7)
        self._manual_pad_button_v22(pad, "↓", 4).grid(row=2, column=1, padx=7, pady=7)

    def _info_row_v22(self, parent, label, initial):
        row = tk.Frame(parent, bg=SURFACE)
        row.pack(fill="x", pady=6)
        tk.Label(row, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        value = tk.Label(row, text=initial, bg=SURFACE, fg=TEXT, font=("Segoe UI", 9, "bold"))
        value.pack(side="right")
        return value

    def _progress_row_v22(self, parent, label):
        wrap = tk.Frame(parent, bg=SURFACE)
        wrap.pack(fill="x", pady=6)
        row = tk.Frame(wrap, bg=SURFACE)
        row.pack(fill="x")
        tk.Label(row, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        value = tk.Label(row, text="—", bg=SURFACE, fg=TEXT, font=("Segoe UI", 8, "bold"))
        value.pack(side="right")
        bar = ttk.Progressbar(wrap, maximum=100, style="Vacuum.Horizontal.TProgressbar")
        bar.pack(fill="x", pady=(4, 0))
        return value, bar

    def _manual_pad_button_v22(self, parent, text, direction):
        btn = tk.Button(
            parent, text=text, bg=SURFACE_2, fg=TEXT, activebackground=ACCENT_SOFT,
            activeforeground=ACCENT, relief="flat", bd=0, width=5, height=2,
            font=("Segoe UI", 16, "bold"), cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        )
        btn.bind("<ButtonPress-1>", lambda _e: self.manual(direction))
        btn.bind("<ButtonRelease-1>", lambda _e: self.manual(5))
        return btn

    # ------------------------------------------------------------- Ajustes
    def _build_settings_page_v22(self):
        page = self._page("settings")
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        inner = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self._settings_inner = inner

        base_outer, base = self._surface(inner, 20, 17)
        base_outer.pack(fill="x", padx=5, pady=6)
        self._section_title(base, "Aplicación", "Estado general y mantenimiento.")
        row = tk.Frame(base, bg=SURFACE)
        row.pack(fill="x", pady=(14, 0))
        self._button(row, "Buscar actualización", self.manual_check_for_updates, accent=True, compact=True).pack(side="left")
        self.settings_map_label = tk.Label(row, text="Mapa local: —", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self.settings_map_label.pack(side="right")

    def _settings_parent(self):
        return self._settings_inner or self._pages["settings"]

    # app_v19 llama esta función durante __init__.
    def _install_windows_settings_card(self):
        parent = self._settings_parent()
        outer, card = self._surface(parent, 20, 17)
        outer.pack(fill="x", padx=5, pady=6)
        self._section_title(card, "Windows y bandeja", "Elegí cómo querés que la aplicación viva en segundo plano.")

        self.start_windows_var = tk.BooleanVar(value=bool(self.settings.get("start_with_windows", False)))
        self.close_tray_var = tk.BooleanVar(value=bool(self.settings.get("close_to_tray", True)))
        for text, variable, command in (
            ("Iniciar con Windows y quedar minimizada en la bandeja", self.start_windows_var, self._toggle_start_with_windows),
            ("Al cerrar con X, mantener la aplicación en la bandeja", self.close_tray_var, self._toggle_close_to_tray),
        ):
            tk.Checkbutton(
                card, text=text, variable=variable, command=command, bg=SURFACE, activebackground=SURFACE,
                fg=TEXT, selectcolor=SURFACE, font=("Segoe UI", 9),
            ).pack(anchor="w", pady=5)
        self._button(card, "Configurar acciones rápidas", self.open_quick_actions_config, compact=True).pack(anchor="w", pady=(10, 0))

    # app_v20 llama esta función durante __init__.
    def _install_xiaomi_account_card(self):
        parent = self._settings_parent()
        outer, card = self._surface(parent, 20, 17)
        outer.pack(fill="x", padx=5, pady=6, before=parent.winfo_children()[0] if parent.winfo_children() else None)
        self._account_card = card
        top = tk.Frame(card, bg=SURFACE)
        top.pack(fill="x")
        tk.Label(top, text="Cuenta Xiaomi", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(side="left")
        self._account_status_label = tk.Label(top, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self._account_status_label.pack(side="right")
        self._account_user_label = tk.Label(card, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self._account_user_label.pack(fill="x", pady=(7, 12))
        self._account_button = self._button(card, "", self.open_setup, accent=True, compact=True)
        self._account_button.pack(anchor="w")

    # ---------------------------------------------------------- Programar
    def _build_scheduler_page(self):
        page = self._pages.get("scheduler") or self._page("scheduler")
        for child in page.winfo_children():
            child.destroy()
        page.grid_columnconfigure(0, weight=2)
        page.grid_columnconfigure(1, weight=3)
        page.grid_rowconfigure(0, weight=1)

        form_outer, form = self._surface(page, 20, 18)
        form_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)
        list_outer, listing = self._surface(page, 20, 18)
        list_outer.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)

        self._section_title(form, "Nueva rutina", "Definí cuándo, cómo y dónde limpiar.")
        self.schedule_name_var = tk.StringVar(value="Limpieza")
        self._field_v22(form, "Nombre", self.schedule_name_var)

        tk.Label(form, text="DÍAS", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 6))
        days = tk.Frame(form, bg=SURFACE)
        days.pack(fill="x")
        self.schedule_day_vars = []
        for index, label in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=index < 5)
            self.schedule_day_vars.append(var)
            tk.Checkbutton(days, text=label, variable=var, bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE, font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))

        hour_row = tk.Frame(form, bg=SURFACE)
        hour_row.pack(fill="x", pady=(14, 0))
        self.schedule_hour_var = tk.StringVar(value="10")
        self.schedule_minute_var = tk.StringVar(value="00")
        self._mini_field(hour_row, "Hora", self.schedule_hour_var).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._mini_field(hour_row, "Minuto", self.schedule_minute_var).pack(side="left", fill="x", expand=True, padx=(5, 0))

        tk.Label(form, text="MODO", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 6))
        self.schedule_mode_var = tk.StringVar(value="Aspirar")
        ttk.Combobox(form, textvariable=self.schedule_mode_var, values=list(MODE_LABELS), state="readonly").pack(fill="x")

        level = tk.Frame(form, bg=SURFACE)
        level.pack(fill="x", pady=(14, 0))
        self.schedule_suction_var = tk.StringVar(value="2")
        self.schedule_water_var = tk.StringVar(value="1")
        self._combo_field(level, "Succión", self.schedule_suction_var, ["1", "2", "3", "4"]).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._combo_field(level, "Agua", self.schedule_water_var, ["1", "2", "3"]).pack(side="left", fill="x", expand=True, padx=(5, 0))

        tk.Label(form, text="DÓNDE", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 6))
        self.schedule_target_var = tk.StringVar(value="all")
        target = tk.Frame(form, bg=SURFACE)
        target.pack(fill="x")
        tk.Radiobutton(target, text="Toda la casa", variable=self.schedule_target_var, value="all", bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE).pack(side="left")
        tk.Radiobutton(target, text="Solo zonas", variable=self.schedule_target_var, value="zones", bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE).pack(side="left", padx=(12, 0))

        self.schedule_zone_frame = tk.Frame(form, bg=SURFACE_2, padx=10, pady=8, highlightthickness=1, highlightbackground=BORDER)
        self.schedule_zone_frame.pack(fill="x", pady=(8, 14))
        self.schedule_zone_vars = {}
        self._button(form, "Guardar rutina", self._add_schedule_from_form, accent=True).pack(fill="x")

        head = tk.Frame(listing, bg=SURFACE)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="Rutinas", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(side="left")
        tk.Label(head, text="Se ejecutan en segundo plano", bg=GREEN_SOFT, fg=GREEN, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="right")
        self.schedule_list_frame = tk.Frame(listing, bg=SURFACE)
        self.schedule_list_frame.pack(fill="both", expand=True)

    def _field_v22(self, parent, label, variable):
        tk.Label(parent, text=label.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(16, 6))
        tk.Entry(parent, textvariable=variable, bg=SURFACE_2, fg=TEXT, relief="flat", highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 9)).pack(fill="x", ipady=7)

    def _mini_field(self, parent, label, variable):
        frame = tk.Frame(parent, bg=SURFACE)
        tk.Label(frame, text=label.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Entry(frame, textvariable=variable, bg=SURFACE_2, fg=TEXT, relief="flat", highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 9)).pack(fill="x", ipady=7)
        return frame

    def _combo_field(self, parent, label, variable, values):
        frame = tk.Frame(parent, bg=SURFACE)
        tk.Label(frame, text=label.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Combobox(frame, textvariable=variable, values=values, state="readonly").pack(fill="x")
        return frame

    # ------------------------------------------------ tools instalados luego
    def _install_map_plan_controls(self):
        parent = self._zone_tools_slot or self._map_toolbar
        self._button(parent, "Zonas", self.open_zone_manager, compact=True).pack(side="right", padx=(5, 0))
        self._button(parent, "Limpiar zonas", self.open_zone_clean_dialog, compact=True).pack(side="right", padx=(5, 0))
        self._button(parent, "Bloquear", lambda: self._enable_plan_draw("no_go"), compact=True).pack(side="right", padx=(5, 0))
        self._button(parent, "+ Zona", lambda: self._enable_plan_draw("zone"), compact=True).pack(side="right", padx=(5, 0))

    def _install_map_library_control(self):
        parent = self._map_library_slot or self._map_toolbar
        self.map_library_button = self._button(parent, "Mapas", self.open_map_library, compact=True)
        self.map_library_button.pack(side="right")
        self._refresh_map_library_button()

    # --------------------------------------------------- diálogos modernos
    def _dialog(self, title, geometry):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry(geometry)
        win.configure(bg=BG)
        win.transient(self)
        apply_window_icon(win)
        return win

    def open_zone_manager(self):
        if not self.plan_store:
            return
        if self._zone_manager and self._zone_manager.winfo_exists():
            self._zone_manager.destroy()
        win = self._dialog("Zonas y puntos", "700x620")
        self._zone_manager = win
        outer, body = self._surface(win, 20, 18)
        outer.pack(fill="both", expand=True, padx=16, pady=16)
        self._section_title(body, "Zonas y puntos", "Todo lo que guardaste sobre el mapa activo.")
        plan = self.plan_store.snapshot()

        def section(title, items, color, action_builder):
            tk.Label(body, text=title.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(18, 7))
            if not items:
                tk.Label(body, text="No hay elementos todavía.", bg=SURFACE, fg=SIDEBAR_MUTED, font=("Segoe UI", 9)).pack(anchor="w")
                return
            for item in items:
                row = tk.Frame(body, bg=SURFACE_2, highlightthickness=1, highlightbackground=BORDER)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=item.get("name", "Sin nombre"), bg=SURFACE_2, fg=color, font=("Segoe UI", 9, "bold")).pack(side="left", padx=10, pady=9)
                action_builder(row, item)

        section(
            "Zonas de limpieza", plan.get("zones", []), GREEN,
            lambda row, item: (
                self._button(row, "Eliminar", lambda zid=item["id"]: self._delete_zone_and_refresh(zid), compact=True, danger=True).pack(side="right", padx=(4, 8), pady=5),
                self._button(row, "Limpiar", lambda z=dict(item): self._run_zones_now([z], "vacuum", int(self.suction_var.get()), 0), compact=True).pack(side="right", pady=5),
            )
        )
        section(
            "Zonas bloqueadas", plan.get("no_go", []), RED,
            lambda row, item: self._button(row, "Eliminar", lambda wid=item["id"]: self._delete_no_go_and_refresh(wid), compact=True, danger=True).pack(side="right", padx=8, pady=5),
        )
        section(
            "Puntos guardados", plan.get("points", []), BLUE,
            lambda row, item: (
                self._button(row, "Eliminar", lambda pid=item["id"]: self._delete_point_and_refresh(pid), compact=True, danger=True).pack(side="right", padx=(4, 8), pady=5),
                self._button(row, "Ir / limpiar", lambda p=dict(item): self._clean_saved_point(p), compact=True).pack(side="right", pady=5),
            )
        )

    def open_zone_clean_dialog(self):
        if not self.plan_store:
            return
        zones = self.plan_store.snapshot().get("zones", [])
        if not zones:
            messagebox.showinfo("Zonas", "Primero creá al menos una zona en el mapa.", parent=self)
            return
        win = self._dialog("Limpiar zonas", "500x580")
        outer, body = self._surface(win, 20, 18)
        outer.pack(fill="both", expand=True, padx=16, pady=16)
        self._section_title(body, "Limpiar zonas", "Podés elegir una o varias áreas del mapa.")
        vars_by_id = {}
        for zone in zones:
            var = tk.BooleanVar(value=False)
            vars_by_id[zone["id"]] = var
            tk.Checkbutton(body, text=zone.get("name", "Zona"), variable=var, bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE, font=("Segoe UI", 9)).pack(anchor="w", pady=3)
        mode_var = tk.StringVar(value="Aspirar")
        suction_var = tk.StringVar(value=str(max(1, int(self.suction_var.get()))))
        water_var = tk.StringVar(value="1")
        for label, var, values in (
            ("Modo", mode_var, list(MODE_LABELS)),
            ("Succión", suction_var, ["1", "2", "3", "4"]),
            ("Agua", water_var, ["1", "2", "3"]),
        ):
            tk.Label(body, text=label.upper(), bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 5))
            ttk.Combobox(body, textvariable=var, values=values, state="readonly").pack(fill="x")

        def run():
            selected = [z for z in zones if vars_by_id[z["id"]].get()]
            if not selected:
                messagebox.showinfo("Zonas", "Elegí al menos una zona.", parent=win)
                return
            win.destroy()
            self._run_zones_now(selected, MODE_LABELS[mode_var.get()], int(suction_var.get()), int(water_var.get()))

        self._button(body, "Iniciar limpieza", run, accent=True).pack(fill="x", pady=(18, 0))

    def open_map_library(self):
        if not self.local_map or not self.plan_store:
            return
        if self._map_library_window and self._map_library_window.winfo_exists():
            self._map_library_window.destroy()
        win = self._dialog("Mapas", "760x600")
        self._map_library_window = win
        outer, body = self._surface(win, 20, 18)
        outer.pack(fill="both", expand=True, padx=16, pady=16)
        head = tk.Frame(body, bg=SURFACE)
        head.pack(fill="x", pady=(0, 12))
        title = tk.Frame(head, bg=SURFACE)
        title.pack(side="left")
        tk.Label(title, text="Mapas", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(title, text="Hasta cuatro viviendas o plantas.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        controls = tk.Frame(head, bg=SURFACE)
        controls.pack(side="right")
        self._button(controls, "Importar .xvac", lambda: self._import_backup(win), compact=True).pack(side="right", padx=(6, 0))
        self._button(controls, "Exportar .xvac", self._export_backup, compact=True).pack(side="right")

        list_frame = tk.Frame(body, bg=SURFACE)
        list_frame.pack(fill="both", expand=True)
        footer = tk.Frame(body, bg=SURFACE)
        footer.pack(fill="x", pady=(12, 0))

        def rebuild():
            for child in list_frame.winfo_children():
                child.destroy()
            for child in footer.winfo_children():
                child.destroy()
            maps = self.local_map.list_maps()
            for item in maps:
                row = tk.Frame(list_frame, bg=SURFACE_2, highlightthickness=1, highlightbackground=BORDER)
                row.pack(fill="x", pady=4)
                info = tk.Frame(row, bg=SURFACE_2)
                info.pack(side="left", fill="x", expand=True, padx=12, pady=10)
                name = item.get("name", "Mapa")
                if item.get("active"):
                    name += "  ·  ACTIVO"
                tk.Label(info, text=name, bg=SURFACE_2, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
                plan = self.plan_store.snapshot(item["id"])
                tk.Label(
                    info,
                    text=f"{item.get('points', 0)} puntos · {len(plan.get('zones', []))} zonas · {len(plan.get('no_go', []))} bloqueos · {len(plan.get('schedules', []))} rutinas",
                    bg=SURFACE_2, fg=MUTED, font=("Segoe UI", 8),
                ).pack(anchor="w", pady=(3, 0))
                actions = tk.Frame(row, bg=SURFACE_2)
                actions.pack(side="right", padx=8)
                if not item.get("active"):
                    self._button(actions, "Usar", lambda mid=item["id"]: self._switch_map(mid, win), compact=True, accent=True).pack(side="left", padx=2)
                self._button(actions, "Renombrar", lambda m=dict(item): self._rename_map(m, rebuild), compact=True).pack(side="left", padx=2)
                if len(maps) > 1:
                    self._button(actions, "Eliminar", lambda m=dict(item): self._delete_map(m, rebuild), compact=True, danger=True).pack(side="left", padx=2)
            btn = self._button(footer, "+ Nuevo mapa", lambda: self._create_map(rebuild), accent=True, compact=True)
            btn.pack(side="left")
            if len(maps) >= 4:
                btn.configure(state="disabled")

        rebuild()

    def open_quick_actions_config(self):
        if self._quick_config_window and self._quick_config_window.winfo_exists():
            self._quick_config_window.destroy()
        win = self._dialog("Acciones rápidas", "560x560")
        self._quick_config_window = win
        outer, body = self._surface(win, 20, 18)
        outer.pack(fill="both", expand=True, padx=16, pady=16)
        self._section_title(body, "Acciones rápidas", "Elegí hasta seis accesos para el clic izquierdo de la bandeja.")
        options = self._quick_action_options()
        labels = ["—"] + [label for label, _code in options]
        label_to_code = {label: code for label, code in options}
        code_to_label = {code: label for label, code in options}
        current = list(self.settings.get("tray_quick_actions") or [])[: self.MAX_QUICK_ACTIONS]
        vars_ = []
        for index in range(self.MAX_QUICK_ACTIONS):
            row = tk.Frame(body, bg=SURFACE)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=str(index + 1), bg=SURFACE, fg=MUTED, width=3, font=("Segoe UI", 9, "bold")).pack(side="left")
            code = current[index] if index < len(current) else ""
            var = tk.StringVar(value=code_to_label.get(code, "—"))
            vars_.append(var)
            ttk.Combobox(row, textvariable=var, values=labels, state="readonly").pack(side="left", fill="x", expand=True)

        def save():
            selected = []
            for var in vars_:
                code = label_to_code.get(var.get())
                if code and code not in selected:
                    selected.append(code)
            self.settings["tray_quick_actions"] = selected
            self.store.save(self.settings)
            win.destroy()
            self._set_banner("Acciones rápidas actualizadas.")
            self._update_tray_metadata()

        self._button(body, "Guardar", save, accent=True).pack(fill="x", pady=(14, 0))

    # --------------------------------------------------- flyout de bandeja
    def _show_quick_panel(self):
        if self._quick_panel and self._quick_panel.winfo_exists():
            self._quick_panel.destroy()
            self._quick_panel = None
            return
        win = tk.Toplevel(self)
        self._quick_panel = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        apply_window_icon(win)
        outer = tk.Frame(win, bg="#cbd5e1", padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=SURFACE, padx=14, pady=12)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Aspiradora", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(body, text=self._tray_battery_text(), bg=SURFACE, fg=GREEN if self._last_tray_battery is not None else MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 10))
        for code in list(self.settings.get("tray_quick_actions") or [])[: self.MAX_QUICK_ACTIONS]:
            self._button(body, self._quick_action_label(code), lambda c=code: self._quick_panel_action(c), compact=True).pack(fill="x", pady=2)
        self._button(body, "Abrir aplicación", lambda: self._quick_panel_action("open"), accent=True, compact=True).pack(fill="x", pady=(8, 0))
        win.update_idletasks()
        width = max(330, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        px, py = self.winfo_pointerxy()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(max(8, px - width + 20), max(8, sw - width - 8))
        y = min(max(8, py - height - 12), max(8, sh - height - 8))
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.bind("<Escape>", lambda _e: win.destroy())
        self._quick_panel_opened_at = time.monotonic()
        outside_since = [None]

        def monitor_pointer():
            if not win.winfo_exists():
                return
            try:
                px2, py2 = self.winfo_pointerxy()
                x0, y0 = win.winfo_rootx(), win.winfo_rooty()
                inside = x0 <= px2 <= x0 + win.winfo_width() and y0 <= py2 <= y0 + win.winfo_height()
                now = time.monotonic()
                if inside:
                    outside_since[0] = None
                elif now - self._quick_panel_opened_at > 0.85:
                    if outside_since[0] is None:
                        outside_since[0] = now
                    elif now - outside_since[0] >= 0.50:
                        win.destroy()
                        if self._quick_panel is win:
                            self._quick_panel = None
                        return
            except Exception:
                return
            win.after(120, monitor_pointer)

        win.after(120, monitor_pointer)


if __name__ == "__main__":
    app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

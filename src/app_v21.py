import time
import tkinter as tk
from tkinter import ttk

import app_v20
from map_geometry import build_mapped_walls
from windows_integration import apply_window_icon, mi_home_png

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

APP_BG = "#f3f5f8"
SURFACE = "#ffffff"
SURFACE_ALT = "#f7f8fa"
TEXT = "#15171a"
MUTED = "#737982"
BORDER = "#e4e7eb"
ACCENT = "#ff6900"
ACCENT_HOVER = "#eb5f00"
ACCENT_SOFT = "#fff2e8"
GREEN = "#1f9d68"
BLUE = "#3286d9"
RED = "#d94a45"
WALL = "#343a43"
MAP_BG = "#f7f9fb"


class App(app_v20.App):
    """v21: paredes persistentes derivadas de EDGE + interfaz visual renovada."""

    def __init__(self):
        self._mapped_wall_source_count = -1
        self._mapped_wall_last_build = 0.0
        self._sidebar_logo_photo = None
        super().__init__()
        self._modernize_widget_tree(self)
        self._install_sidebar_logo()
        self._rebuild_mapped_walls(force=True)
        self.after(180, lambda: self.show_page("home"))

    # ---------------------------------------------------------- estilo global
    def _configure_styles(self):
        try:
            super()._configure_styles()
        except Exception:
            pass
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Vacuum.Horizontal.TProgressbar",
            troughcolor="#eceff2",
            background=ACCENT,
            bordercolor="#eceff2",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowsize=14,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", SURFACE_ALT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", TEXT)],
        )

    def _button(self, parent, text, command, accent=False, compact=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else SURFACE_ALT,
            fg="white" if accent else TEXT,
            activebackground=ACCENT_HOVER if accent else "#eceff2",
            activeforeground="white" if accent else TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=ACCENT if accent else BORDER,
            highlightcolor=ACCENT if accent else BORDER,
            cursor="hand2",
            font=("Segoe UI", 9 if compact else 10, "bold"),
            padx=13 if compact else 16,
            pady=7 if compact else 10,
        )

    def _card(self, parent, title, initial):
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.pack(side="left", fill="x", expand=True, padx=5)
        tk.Label(card, text=title, bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=16, pady=(12, 3)
        )
        value = tk.Label(card, text=initial, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 18))
        value.pack(anchor="w", padx=16, pady=(0, 13))
        return value

    def _nav_button(self, parent, text, page):
        icon = {
            "home": "⌂",
            "map": "▦",
            "scheduler": "◷",
            "robot": "◉",
            "settings": "⚙",
        }.get(page, "•")
        btn = tk.Button(
            parent,
            text=f" {icon}   {text}",
            command=lambda p=page: self.show_page(p),
            bg=SURFACE,
            fg=MUTED,
            activebackground=ACCENT_SOFT,
            activeforeground=ACCENT,
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

    def show_page(self, page):
        result = super().show_page(page)
        for key, button in getattr(self, "_nav_buttons", {}).items():
            selected = key == page
            try:
                button.configure(
                    bg=ACCENT_SOFT if selected else SURFACE,
                    fg=ACCENT if selected else MUTED,
                    activebackground=ACCENT_SOFT,
                    activeforeground=ACCENT,
                )
            except Exception:
                pass
        return result

    def _modernize_widget_tree(self, root):
        color_map = {
            "#f4f5f7": APP_BG,
            "#ffffff": SURFACE,
            "#f8f9fb": SURFACE_ALT,
            "#f7f9fb": MAP_BG,
            "#e8eaed": BORDER,
            "#17181a": TEXT,
            "#7b8088": MUTED,
        }

        def walk(widget):
            try:
                current_bg = str(widget.cget("bg")).lower()
                if current_bg in color_map:
                    widget.configure(bg=color_map[current_bg])
            except Exception:
                pass
            try:
                current_fg = str(widget.cget("fg")).lower()
                if current_fg in color_map:
                    widget.configure(fg=color_map[current_fg])
            except Exception:
                pass
            try:
                if int(widget.cget("highlightthickness")) > 0:
                    widget.configure(highlightbackground=BORDER)
            except Exception:
                pass
            try:
                children = list(widget.winfo_children())
            except Exception:
                children = []
            for child in children:
                walk(child)

        try:
            self.configure(bg=APP_BG)
        except Exception:
            pass
        walk(root)
        try:
            self.sidebar.configure(width=216, bg=SURFACE, highlightbackground=BORDER)
        except Exception:
            pass
        try:
            self.page_title.configure(font=("Segoe UI Semibold", 23), fg=TEXT, bg=APP_BG)
        except Exception:
            pass
        try:
            self.battery_header.configure(bg=SURFACE, fg=TEXT, font=("Segoe UI", 9, "bold"), padx=13, pady=8)
        except Exception:
            pass
        try:
            self.connection_label.configure(bg=APP_BG, fg=MUTED)
            self.connection_dot.configure(bg=APP_BG)
        except Exception:
            pass
        try:
            self.map_canvas.configure(bg=MAP_BG, cursor="fleur")
            self.home_map_canvas.configure(bg=MAP_BG)
        except Exception:
            pass
        try:
            self.mapping_steps_info.configure(
                text="Paso 1 crea paredes estimadas en vivo · Paso 2 completa el interior · ECO mínimo"
            )
        except Exception:
            pass

    def _install_sidebar_logo(self):
        if Image is None or ImageTk is None:
            return
        try:
            source = mi_home_png()
            if not source.exists():
                return
            image = Image.open(source).convert("RGBA")
            image.thumbnail((38, 38), Image.Resampling.LANCZOS)
            self._sidebar_logo_photo = ImageTk.PhotoImage(image)
            brand = self.sidebar.winfo_children()[0]
            for child in brand.winfo_children():
                if isinstance(child, tk.Canvas):
                    child.delete("all")
                    child.configure(width=40, height=40, bg=SURFACE, highlightthickness=0)
                    child.create_image(20, 20, image=self._sidebar_logo_photo)
                elif isinstance(child, tk.Frame):
                    for label in child.winfo_children():
                        try:
                            if label.cget("text") == "Mi Vacuum":
                                label.configure(
                                    text="Xiaomi Home", fg=TEXT, bg=SURFACE, font=("Segoe UI Semibold", 12)
                                )
                            elif label.cget("text") == "E10 · PC":
                                label.configure(text="Robot Vacuum E10 · PC", fg=MUTED, bg=SURFACE)
                        except Exception:
                            pass
        except Exception:
            pass

    # ------------------------------------------------------ settings ordenado
    def _settings_page(self):
        return self._pages.get("settings") or self._page("settings")

    def _install_windows_settings_card(self):
        page = self._settings_page()
        card = tk.Frame(page, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=6)
        tk.Label(card, text="Windows y bandeja", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(
            anchor="w", padx=20, pady=(16, 4)
        )
        tk.Label(
            card,
            text="Inicio automático, comportamiento al cerrar y accesos rápidos desde el icono de Mi Home.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 10))

        self.start_windows_var = tk.BooleanVar(value=bool(self.settings.get("start_with_windows", False)))
        self.close_tray_var = tk.BooleanVar(value=bool(self.settings.get("close_to_tray", True)))
        for text, variable, command in (
            (
                "Iniciar con Windows y abrir minimizada en la bandeja",
                self.start_windows_var,
                self._toggle_start_with_windows,
            ),
            (
                "Al cerrar con X, mantener la aplicación en la bandeja",
                self.close_tray_var,
                self._toggle_close_to_tray,
            ),
        ):
            tk.Checkbutton(
                card,
                text=text,
                variable=variable,
                command=command,
                bg=SURFACE,
                activebackground=SURFACE,
                fg=TEXT,
                selectcolor=SURFACE,
                font=("Segoe UI", 9),
            ).pack(anchor="w", padx=20, pady=4)

        row = tk.Frame(card, bg=SURFACE)
        row.pack(fill="x", padx=20, pady=(10, 16))
        self._button(
            row,
            "Configurar acciones rápidas",
            self.open_quick_actions_config,
            accent=True,
            compact=True,
        ).pack(side="left")
        tk.Label(
            row,
            text="Clic izquierdo: batería + hasta 6 acciones configurables",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=10)

    def _install_xiaomi_account_card(self):
        page = self._settings_page()
        card = tk.Frame(page, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        existing = page.winfo_children()
        if existing:
            card.pack(fill="x", padx=5, pady=6, before=existing[0])
        else:
            card.pack(fill="x", padx=5, pady=6)
        self._account_card = card

        head = tk.Frame(card, bg=SURFACE)
        head.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(head, text="Cuenta Xiaomi", bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(
            side="left"
        )
        self._account_status_label = tk.Label(
            head, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9, "bold")
        )
        self._account_status_label.pack(side="right")
        self._account_user_label = tk.Label(
            card, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w"
        )
        self._account_user_label.pack(fill="x", padx=20, pady=(3, 10))
        self._account_button = self._button(card, "", self.open_setup, accent=True, compact=True)
        self._account_button.pack(anchor="w", padx=20, pady=(0, 16))

    # ----------------------------------------------------- paredes persistentes
    def _rebuild_mapped_walls(self, force=False):
        if not self.local_map:
            return False
        snapshot = self.local_map.snapshot()
        perimeter = [p for p in snapshot.get("points", []) if int(p.get("phase", 0) or 0) == 1]
        count = len(perimeter)
        now = time.monotonic()
        if not force:
            if count == self._mapped_wall_source_count:
                return False
            if now - self._mapped_wall_last_build < 0.45:
                return False
        walls = build_mapped_walls(perimeter)
        self.local_map.set_mapped_walls(walls)
        self._mapped_wall_source_count = count
        self._mapped_wall_last_build = now
        self._render_maps()
        return True

    def start_new_mapping(self):
        self._mapped_wall_source_count = -1
        self._mapped_wall_last_build = 0.0
        return super().start_new_mapping()

    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        if self.mapping_active and int(self.mapping_phase or 0) == 1:
            self._rebuild_mapped_walls(force=False)
        return result

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("edge_only_complete", "perimeter_complete"):
            self._rebuild_mapped_walls(force=True)
        return result

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        transform = self._map_transforms.get(canvas)
        walls = list((snapshot or {}).get("mapped_walls") or [])
        if not transform or not walls:
            return result

        scale = float(transform["scale"])
        min_x = float(transform["min_x"])
        max_y = float(transform["max_y"])
        pad = float(transform["pad"])
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)

        def to_screen(point):
            return (
                pad + (float(point["x"]) - min_x) * scale + pan_x,
                pad + (max_y - float(point["y"])) * scale + pan_y,
            )

        segment_count = 0
        for wall in walls:
            points = wall.get("points", []) or []
            if len(points) < 2:
                continue
            coords = []
            for point in points:
                x, y = to_screen(point)
                coords.extend((x, y))
            canvas.create_line(
                *coords,
                fill=WALL,
                width=4,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags=("mapped_wall_v21",),
            )
            segment_count += max(0, len(points) - 1)

        if canvas is getattr(self, "map_canvas", None):
            canvas.create_rectangle(
                14,
                14,
                196,
                62,
                fill=SURFACE,
                outline=BORDER,
                width=1,
                tags=("wall_legend_v21",),
            )
            canvas.create_line(
                27,
                36,
                55,
                36,
                fill=WALL,
                width=4,
                capstyle=tk.ROUND,
                tags=("wall_legend_v21",),
            )
            canvas.create_text(
                66,
                29,
                anchor="w",
                text="Paredes estimadas",
                fill=TEXT,
                font=("Segoe UI", 8, "bold"),
                tags=("wall_legend_v21",),
            )
            canvas.create_text(
                66,
                45,
                anchor="w",
                text=f"{segment_count} segmentos guardados",
                fill=MUTED,
                font=("Segoe UI", 7),
                tags=("wall_legend_v21",),
            )
        return result

    # ------------------------------------------------ diálogos también modernos
    def open_zone_manager(self):
        result = super().open_zone_manager()
        try:
            apply_window_icon(self._zone_manager)
            self._modernize_widget_tree(self._zone_manager)
        except Exception:
            pass
        return result

    def open_map_library(self):
        result = super().open_map_library()
        try:
            apply_window_icon(self._map_library_window)
            self._modernize_widget_tree(self._map_library_window)
        except Exception:
            pass
        return result

    def open_quick_actions_config(self):
        result = super().open_quick_actions_config()
        try:
            apply_window_icon(self._quick_config_window)
            self._modernize_widget_tree(self._quick_config_window)
        except Exception:
            pass
        return result


if __name__ == "__main__":
    app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

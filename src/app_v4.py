import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import app_v2
from xiaomi_cloud_qr_v2 import XiaomiQrLogin, discover_e10_from_qr
from xiaomi_map import XiaomiE10MapClient

# La UI base sigue en app_v2. Esta versión incorpora el login QR corregido,
# persiste una sesión cifrada para el mapa y agrega controles de mopa/mapa.
app_v2.XiaomiQrLogin = XiaomiQrLogin
app_v2.discover_e10_from_qr = discover_e10_from_qr

BG = app_v2.BG
PANEL = app_v2.PANEL
PANEL_2 = app_v2.PANEL_2
TEXT = app_v2.TEXT
MUTED = app_v2.MUTED
ACCENT = app_v2.ACCENT
GREEN = app_v2.GREEN
RED = app_v2.RED


def _qr_authenticated(dialog):
    try:
        if dialog.qr_window and dialog.qr_window.winfo_exists():
            dialog.qr_window.destroy()
    except Exception:
        pass
    dialog.status.configure(
        text="Sesión de Xiaomi confirmada. Buscando tu Vacuum E10 y preparando el acceso al mapa…"
    )


def _show_qr(self, login, info):
    self.status.configure(text="QR listo. Escanealo con tu celular y completá el inicio de sesión de Xiaomi.")
    self.qr_window = app_v2.QrDialog(self, info)
    selected_region = self.region.get()

    def worker():
        try:
            login.wait_for_login()
            self.after(0, lambda: _qr_authenticated(self))

            devices = discover_e10_from_qr(login, selected_region)
            if not devices:
                raise RuntimeError(
                    "La sesión de Xiaomi se inició correctamente, pero no encontré un Xiaomi Vacuum E10 en la cuenta. "
                    "Dejá Región en 'all' y verificá que el E10 aparezca en Mi Home con esa misma cuenta."
                )

            device = devices[0]
            # Guardamos solamente las credenciales de sesión necesarias para pedir el
            # mapa. SettingsStore cifra cloud_session con DPAPI de Windows.
            session_data = {
                "user_id": login.user_id,
                "service_token": login.service_token,
                "ssecurity": login.ssecurity,
                "cuser_id": login.cuser_id,
                "pass_token": login.pass_token,
            }
            self.app.settings["cloud_session"] = json.dumps(session_data, separators=(",", ":"))
            self.app.settings["device_did"] = str(device.get("did") or "")
            self.app.settings["device_region"] = str(device.get("locale") or "")
            self.app.settings["device_name"] = device.get("name") or "Xiaomi Robot Vacuum E10"
            self.app.store.save(self.app.settings)

            self.after(0, lambda: self._qr_success(device, len(devices)))
        except Exception as exc:
            msg = str(exc).strip() or "No se pudo completar el inicio de sesión por QR."
            self.after(0, lambda: self._qr_error(msg))

    threading.Thread(target=worker, daemon=True).start()


app_v2.SetupDialog._show_qr = _show_qr


class App(app_v2.App):
    def __init__(self):
        super().__init__()
        self.geometry("1040x760")
        self.minsize(940, 690)

    def _build_ui(self):
        super()._build_ui()

        self.mop_enabled_var = tk.BooleanVar(value=bool(self.settings.get("mop_enabled", False)))
        self._last_water_level = max(1, min(3, int(self.settings.get("mop_water_level", 1) or 1)))

        bar = tk.Frame(self, bg=PANEL)
        bar.pack(side="bottom", fill="x", padx=26, pady=(4, 14))

        left = tk.Frame(bar, bg=PANEL)
        left.pack(side="left", padx=16, pady=10)
        tk.Label(left, text="Mopa", bg=PANEL, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 10))
        self.mop_check = tk.Checkbutton(
            left,
            text="Usar mopa",
            variable=self.mop_enabled_var,
            command=self._mop_changed,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=PANEL_2,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.mop_check.pack(side="left")
        tk.Label(
            left,
            text="Activa agua + trapeado si la mopa está colocada físicamente.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12)

        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=16, pady=8)
        self._button(right, "Mapa y habitaciones", self.open_map, accent=True).pack(side="left")

        if self.mop_enabled_var.get():
            if self.mode_var.get() == "Aspirar":
                self.mode_var.set("Aspirar + trapear")
            if self.water_var.get() == 0:
                self.water_var.set(self._last_water_level)
        else:
            self.mode_var.set("Aspirar")
            self.water_var.set(0)

    def _save_mop_preferences(self):
        self.settings["mop_enabled"] = bool(self.mop_enabled_var.get())
        if self.mop_enabled_var.get():
            self.settings["mop_water_level"] = max(1, int(self.water_var.get() or self._last_water_level))
        self.store.save(self.settings)

    def _mop_changed(self):
        enabled = bool(self.mop_enabled_var.get())
        if enabled:
            level = max(1, int(self.settings.get("mop_water_level", self._last_water_level) or 1))
            self._last_water_level = min(3, level)
            self.water_var.set(self._last_water_level)
            if self.mode_var.get() == "Aspirar":
                self.mode_var.set("Aspirar + trapear")
        else:
            if self.water_var.get() > 0:
                self._last_water_level = int(self.water_var.get())
            self.water_var.set(0)
            self.mode_var.set("Aspirar")

        self._save_mop_preferences()
        if self.vacuum:
            level = self._last_water_level
            self._run_command(
                "Configurando mopa…",
                lambda: self.vacuum.set_mop_enabled(enabled, level),
            )

    def set_water(self, level):
        level = int(level)
        if not self.mop_enabled_var.get() and level > 0:
            self.water_var.set(0)
            self._set_banner("Activá 'Usar mopa' para habilitar el agua.")
            return
        if level > 0:
            self._last_water_level = level
            self.settings["mop_water_level"] = level
            self.store.save(self.settings)
        super().set_water(level)

    def _prepare_cleaning_mode(self):
        if not self.vacuum:
            raise RuntimeError("El robot está desconectado.")
        if self.mop_enabled_var.get():
            water = max(1, min(3, int(self.water_var.get() or self._last_water_level)))
            self.vacuum.set_water(water)
            selected = self.mode_var.get()
            mode = 2 if selected == "Trapear" else 1
            self.vacuum.set_mode(mode)
            return mode
        self.vacuum.set_water(0)
        self.vacuum.set_mode(0)
        return 0

    def start_clean(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el Xiaomi Vacuum E10.")
            return

        def command():
            mode = self._prepare_cleaning_mode()
            # start() vuelve a fijar el modo y ejecuta la acción correspondiente.
            return self.vacuum.start(mode)

        self._run_command("Iniciando limpieza…", command)

    def open_map(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el Xiaomi Vacuum E10.")
            return
        MapDialog(self)


class MapDialog(tk.Toplevel):
    MAX_MAP_W = 720
    MAX_MAP_H = 620

    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Mapa · Xiaomi Vacuum E10")
        self.geometry("1040x760")
        self.minsize(920, 680)
        self.configure(bg=BG)
        self.transient(app)

        self.snapshot = None
        self.photo = None
        self.display_scale = 1.0
        self.selected_point = None
        self.room_vars = {}
        self.selection_marker = None

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(header, text="Mapa de limpieza", bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(side="left")
        self.app._button(header, "Actualizar mapa", self.refresh, compact=True).pack(side="right")

        self.status = tk.Label(
            self,
            text="Cargando mapa desde Xiaomi…",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.status.pack(fill="x", padx=24, pady=(0, 8))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        map_panel = tk.Frame(body, bg=PANEL)
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.canvas = tk.Canvas(
            map_panel,
            bg="#0b0d11",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._map_click)

        side = tk.Frame(body, bg=PANEL, width=260)
        side.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        side.grid_propagate(False)

        tk.Label(side, text="Punto del mapa", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            side,
            text="Hacé clic en cualquier parte accesible del mapa. El E10 irá a esa zona y hará una limpieza puntual.",
            bg=PANEL,
            fg=MUTED,
            wraplength=225,
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16, pady=(0, 8))
        self.point_label = tk.Label(side, text="Ningún punto elegido", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.point_label.pack(anchor="w", padx=16, pady=(0, 8))
        self.point_button = self.app._button(side, "Ir y limpiar aquí", self.clean_point, accent=True)
        self.point_button.configure(state="disabled")
        self.point_button.pack(fill="x", padx=16, pady=(0, 14))

        tk.Frame(side, bg=PANEL_2, height=1).pack(fill="x", padx=16, pady=6)
        tk.Label(side, text="Habitaciones", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(10, 5))
        self.rooms_frame = tk.Frame(side, bg=PANEL)
        self.rooms_frame.pack(fill="both", expand=True, padx=16)
        self.rooms_button = self.app._button(side, "Limpiar seleccionadas", self.clean_rooms)
        self.rooms_button.configure(state="disabled")
        self.rooms_button.pack(fill="x", padx=16, pady=(8, 16))

        self.after(150, self.refresh)

    def refresh(self):
        self.status.configure(text="Descargando y decodificando el mapa…")

        def worker():
            try:
                client = XiaomiE10MapClient(self.app.vacuum, self.app.settings)
                snapshot = client.load()
                self.after(0, lambda: self._render_map(snapshot))
            except Exception as exc:
                msg = str(exc).strip() or "No se pudo cargar el mapa."
                self.after(0, lambda: self._map_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _map_error(self, error):
        self.status.configure(text=error, fg=RED)
        self.canvas.delete("all")
        self.canvas.create_text(
            25,
            25,
            anchor="nw",
            fill=MUTED,
            width=600,
            text=error + "\n\nSi todavía no vinculaste esta versión con QR, cerrá el mapa y hacelo desde Configurar.",
            font=("Segoe UI", 11),
        )

    def _render_map(self, snapshot):
        self.snapshot = snapshot
        self.status.configure(text=f"Mapa {snapshot.map_name} · hacé clic para elegir un punto", fg=MUTED)
        self.canvas.delete("all")

        source = snapshot.image
        width, height = source.size
        scale = min(self.MAX_MAP_W / max(1, width), self.MAX_MAP_H / max(1, height), 3.0)
        self.display_scale = max(0.15, scale)
        display_w = max(1, int(width * self.display_scale))
        display_h = max(1, int(height * self.display_scale))
        display = source.resize((display_w, display_h), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.configure(scrollregion=(0, 0, display_w, display_h))
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags="map")

        self._draw_rooms()
        self._draw_positions()
        self._build_room_controls()
        self.selected_point = None
        self.point_button.configure(state="disabled")
        self.point_label.configure(text="Ningún punto elegido")

    def _world_to_canvas(self, point):
        if not self.snapshot or point is None:
            return None
        transformed = self.snapshot.transformer.map_to_image(point)
        height = self.snapshot.image.size[1]
        x = transformed.x * self.display_scale
        y = (height - 1 - transformed.y) * self.display_scale
        return x, y

    def _draw_positions(self):
        if not self.snapshot:
            return
        data = self.snapshot.map_data
        if getattr(data, "charger", None):
            pos = self._world_to_canvas(data.charger)
            if pos:
                x, y = pos
                self.canvas.create_rectangle(x - 6, y - 6, x + 6, y + 6, fill=GREEN, outline="white", width=1)
        if getattr(data, "vacuum_position", None):
            pos = self._world_to_canvas(data.vacuum_position)
            if pos:
                x, y = pos
                self.canvas.create_oval(x - 7, y - 7, x + 7, y + 7, fill="white", outline="#222222", width=2)

    def _draw_rooms(self):
        rooms = getattr(self.snapshot.map_data, "rooms", None) or {}
        for room_id, room in rooms.items():
            center_x = (float(room.x0) + float(room.x1)) / 2
            center_y = (float(room.y0) + float(room.y1)) / 2

            class P:
                x = center_x
                y = center_y

            pos = self._world_to_canvas(P())
            if not pos:
                continue
            x, y = pos
            name = getattr(room, "name", None) or f"Habitación {room_id}"
            self.canvas.create_text(
                x,
                y,
                text=name,
                fill="white",
                font=("Segoe UI", 9, "bold"),
            )

    def _build_room_controls(self):
        for widget in self.rooms_frame.winfo_children():
            widget.destroy()
        self.room_vars = {}
        rooms = getattr(self.snapshot.map_data, "rooms", None) or {}
        if not rooms:
            tk.Label(
                self.rooms_frame,
                text="Este mapa no trajo habitaciones separadas.",
                bg=PANEL,
                fg=MUTED,
                wraplength=220,
                justify="left",
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=4)
            self.rooms_button.configure(state="disabled")
            return

        for room_id, room in sorted(rooms.items(), key=lambda item: int(item[0])):
            var = tk.BooleanVar(value=False)
            self.room_vars[int(room_id)] = var
            name = getattr(room, "name", None) or f"Habitación {room_id}"
            tk.Checkbutton(
                self.rooms_frame,
                text=name,
                variable=var,
                bg=PANEL,
                fg=TEXT,
                activebackground=PANEL,
                activeforeground=TEXT,
                selectcolor=PANEL_2,
                anchor="w",
                font=("Segoe UI", 9),
            ).pack(fill="x", anchor="w", pady=2)
        self.rooms_button.configure(state="normal")

    def _map_click(self, event):
        if not self.snapshot:
            return
        image_w, image_h = self.snapshot.image.size
        px = float(event.x) / self.display_scale
        py_display = float(event.y) / self.display_scale
        if px < 0 or py_display < 0 or px >= image_w or py_display >= image_h:
            return

        # La imagen se dibuja con Y invertida respecto de las coordenadas internas.
        raw_y = image_h - 1 - py_display
        x = self.snapshot.transformer.image_to_map_x(int(round(px)))
        y = self.snapshot.transformer.image_to_map_y(int(round(raw_y)))
        self.selected_point = (x, y)
        self.point_label.configure(text=f"x {x:.0f} · y {y:.0f}")
        self.point_button.configure(state="normal")

        if self.selection_marker:
            self.canvas.delete(self.selection_marker)
        self.selection_marker = self.canvas.create_oval(
            event.x - 7,
            event.y - 7,
            event.x + 7,
            event.y + 7,
            outline="white",
            width=3,
        )

    def _run_map_command(self, message, function):
        self.status.configure(text=message, fg=MUTED)

        def worker():
            try:
                self.app._prepare_cleaning_mode()
                function()
                self.after(0, lambda: self.status.configure(text="Comando enviado al E10.", fg=GREEN))
            except Exception as exc:
                msg = str(exc).strip() or "El robot rechazó el comando."
                self.after(0, lambda: messagebox.showerror("No se pudo iniciar", msg, parent=self))

        threading.Thread(target=worker, daemon=True).start()

    def clean_point(self):
        if not self.selected_point:
            return
        x, y = self.selected_point
        self._run_map_command(
            "Enviando el E10 al punto elegido…",
            lambda: self.app.vacuum.clean_point(x, y),
        )

    def clean_rooms(self):
        selected = [room_id for room_id, var in self.room_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Habitaciones", "Elegí al menos una habitación.", parent=self)
            return
        self._run_map_command(
            "Iniciando limpieza de habitaciones…",
            lambda: self.app.vacuum.clean_rooms(selected),
        )


if __name__ == "__main__":
    App().mainloop()

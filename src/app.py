import threading
import tkinter as tk
from tkinter import messagebox, ttk

from settings_store import SettingsStore
from updater import check_for_update, download_and_install
from version import APP_NAME, VERSION
from xiaomi_e10 import XiaomiE10, discover_from_xiaomi

BG = "#0f1115"
PANEL = "#171a21"
PANEL_2 = "#20242d"
TEXT = "#f3f5f7"
MUTED = "#9aa3ad"
ACCENT = "#45a6ff"
GREEN = "#41c97a"
RED = "#ff6577"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} · {VERSION}")
        self.geometry("980x690")
        self.minsize(900, 620)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.store = SettingsStore()
        self.settings = self.store.load()
        self.vacuum = None
        self.polling = False
        self.updating = False

        self._configure_styles()
        self._build_ui()
        self.after(400, self._connect_from_saved)
        if self.settings.get("auto_update", True):
            self.after(2500, self._schedule_update_check)

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])

    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=26, pady=(22, 10))
        tk.Label(header, text="Xiaomi Vacuum E10", bg=BG, fg=TEXT, font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(header, text=f"v{VERSION}", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=10, pady=(12, 0))

        right = tk.Frame(header, bg=BG)
        right.pack(side="right")
        self.connection_dot = tk.Label(right, text="●", bg=BG, fg=RED, font=("Segoe UI", 13))
        self.connection_dot.pack(side="left", padx=(0, 6))
        self.connection_label = tk.Label(right, text="Desconectado", bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self.connection_label.pack(side="left", padx=(0, 12))
        self._button(right, "Configurar", self.open_setup, compact=True).pack(side="left")

        self.banner = tk.Label(self, text="", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.banner.pack(fill="x", padx=28, pady=(0, 8))

        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", padx=26, pady=8)
        self.status_value = self._card(cards, "ESTADO", "—")
        self.battery_value = self._card(cards, "BATERÍA", "—")
        self.area_value = self._card(cards, "ÁREA", "—")
        self.time_value = self._card(cards, "TIEMPO", "—")

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=26, pady=8)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        controls = self._panel(main)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side = self._panel(main)
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        tk.Label(controls, text="Limpieza", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=20, pady=(18, 10))

        mode_row = tk.Frame(controls, bg=PANEL)
        mode_row.pack(fill="x", padx=20, pady=5)
        self.mode_var = tk.StringVar(value="Aspirar")
        self.mode_combo = ttk.Combobox(mode_row, textvariable=self.mode_var, state="readonly", values=["Aspirar", "Aspirar + trapear", "Trapear"], width=22)
        self.mode_combo.pack(side="left", fill="x", expand=True)
        self._button(mode_row, "Iniciar", self.start_clean, accent=True).pack(side="left", padx=(10, 0))

        pattern_row = tk.Frame(controls, bg=PANEL)
        pattern_row.pack(fill="x", padx=20, pady=(3, 7))
        self._button(pattern_row, "Limpiar bordes", self.start_edge_clean).pack(side="left", fill="x", expand=True)
        self._button(pattern_row, "Espiral", self.start_spiral_clean).pack(side="left", fill="x", expand=True, padx=(10, 0))

        cmd_row = tk.Frame(controls, bg=PANEL)
        cmd_row.pack(fill="x", padx=20, pady=7)
        self._button(cmd_row, "Detener", self.stop_clean).pack(side="left", fill="x", expand=True)
        self._button(cmd_row, "Volver a base", self.dock).pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._button(cmd_row, "Encontrar", self.locate).pack(side="left", fill="x", expand=True, padx=(10, 0))

        self._separator(controls)
        tk.Label(controls, text="Ajustes de limpieza", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(4, 8))

        self.suction_var = tk.IntVar(value=2)
        self.water_var = tk.IntVar(value=1)
        self._scale_row(controls, "Succión", self.suction_var, 1, 4, self.set_suction, ["Silenciosa", "Estándar", "Fuerte", "Turbo"])
        self._scale_row(controls, "Agua", self.water_var, 0, 3, self.set_water, ["Apagada", "Baja", "Media", "Alta"])

        self._separator(controls)
        tk.Label(controls, text="Control manual", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(4, 8))
        pad = tk.Frame(controls, bg=PANEL)
        pad.pack(pady=4)
        self._manual_button(pad, "↑", 1).grid(row=0, column=1, padx=5, pady=5)
        self._manual_button(pad, "←", 2).grid(row=1, column=0, padx=5, pady=5)
        self._manual_button(pad, "■", 5).grid(row=1, column=1, padx=5, pady=5)
        self._manual_button(pad, "→", 3).grid(row=1, column=2, padx=5, pady=5)
        self._manual_button(pad, "↓", 4).grid(row=2, column=1, padx=5, pady=5)

        tk.Label(side, text="Robot", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=20, pady=(18, 12))
        self.mode_info = self._info_row(side, "Modo", "—")
        self.deposit_info = self._info_row(side, "Depósito", "—")
        self.mop_info = self._info_row(side, "Mopa", "—")
        self.fault_info = self._info_row(side, "Error", "—")

        self._separator(side)
        tk.Label(side, text="Consumibles", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(4, 10))
        self.side_brush_info = self._progress_row(side, "Cepillo lateral")
        self.main_brush_info = self._progress_row(side, "Cepillo principal")
        self.hepa_info = self._progress_row(side, "Filtro HEPA")
        self.mop_life_info = self._progress_row(side, "Mopa")

    def _card(self, parent, title, initial):
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=0)
        frame.pack(side="left", fill="x", expand=True, padx=6)
        tk.Label(frame, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        value = tk.Label(frame, text=initial, bg=PANEL, fg=TEXT, font=("Segoe UI", 18, "bold"))
        value.pack(anchor="w", padx=16, pady=(0, 13))
        return value

    def _panel(self, parent):
        return tk.Frame(parent, bg=PANEL)

    def _button(self, parent, text, command, accent=False, compact=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else PANEL_2,
            fg="white",
            activebackground="#328edb" if accent else "#2a303b",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9 if compact else 10, "bold"),
            padx=12 if compact else 14,
            pady=6 if compact else 9,
        )

    def _separator(self, parent):
        tk.Frame(parent, bg=PANEL_2, height=1).pack(fill="x", padx=20, pady=16)

    def _info_row(self, parent, label, initial):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=20, pady=5)
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")
        value = tk.Label(row, text=initial, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"))
        value.pack(side="right")
        return value

    def _progress_row(self, parent, label):
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", padx=20, pady=5)
        row = tk.Frame(wrap, bg=PANEL)
        row.pack(fill="x")
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        value = tk.Label(row, text="—", bg=PANEL, fg=TEXT, font=("Segoe UI", 9, "bold"))
        value.pack(side="right")
        bar = ttk.Progressbar(wrap, maximum=100)
        bar.pack(fill="x", pady=(4, 0))
        return value, bar

    def _scale_row(self, parent, label, variable, minimum, maximum, command, names):
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", padx=20, pady=5)
        top = tk.Frame(wrap, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")
        value = tk.Label(top, text=names[variable.get() - minimum], bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"))
        value.pack(side="right")

        def changed(raw):
            v = int(float(raw))
            value.configure(text=names[v - minimum])

        scale = tk.Scale(wrap, from_=minimum, to=maximum, orient="horizontal", variable=variable, command=changed, showvalue=False,
                         bg=PANEL, fg=TEXT, troughcolor=PANEL_2, highlightthickness=0, activebackground=ACCENT)
        scale.pack(fill="x")
        scale.bind("<ButtonRelease-1>", lambda _e: command(variable.get()))

    def _manual_button(self, parent, text, direction):
        btn = self._button(parent, text, lambda: None)
        btn.configure(width=4, font=("Segoe UI", 14, "bold"))
        btn.bind("<ButtonPress-1>", lambda _e: self.manual(direction))
        btn.bind("<ButtonRelease-1>", lambda _e: self.manual(5))
        return btn

    def _set_banner(self, text):
        self.banner.configure(text=text)

    def _set_connection(self, connected, text=None):
        self.connection_dot.configure(fg=GREEN if connected else RED)
        self.connection_label.configure(text=text or ("Conectado" if connected else "Desconectado"))

    def _connect_from_saved(self):
        if self.settings.get("ip") and self.settings.get("token"):
            self.connect_device(self.settings["ip"], self.settings["token"], quiet=True)
        else:
            self._set_banner("Configurá el robot para empezar. Podés obtener IP/token desde tu cuenta Xiaomi o ingresarlos manualmente.")

    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")

        def worker():
            try:
                vacuum = XiaomiE10(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self.vacuum = vacuum
                self.settings["ip"] = ip
                self.settings["token"] = token
                self.store.save(self.settings)
                self.after(0, lambda: self._on_connected(ip))
            except Exception as exc:
                self.vacuum = None
                self.after(0, lambda: self._on_connect_error(str(exc), quiet))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected(self, ip):
        self._set_connection(True, f"Conectado · {ip}")
        self._set_banner("Control local activo. PC y robot se comunican por tu router.")
        self._start_polling()

    def _on_connect_error(self, error, quiet):
        self._set_connection(False)
        self._set_banner("No se pudo conectar. Revisá IP/token y que el robot esté en la misma red.")
        if not quiet:
            messagebox.showerror("No se pudo conectar", error)

    def _start_polling(self):
        if self.polling:
            return
        self.polling = True
        self._poll_status()

    def _poll_status(self):
        if not self.vacuum:
            self.polling = False
            return

        def worker():
            try:
                status = self.vacuum.status()
                self.after(0, lambda: self._render_status(status))
            except Exception as exc:
                self.after(0, lambda: self._set_banner(f"Robot sin respuesta: {exc}"))
            finally:
                delay = max(2, int(self.settings.get("poll_seconds", 5))) * 1000
                self.after(delay, self._poll_status)

        threading.Thread(target=worker, daemon=True).start()

    def _render_status(self, s):
        self.status_value.configure(text=s.status_name)
        self.battery_value.configure(text=f"{s.battery}%")
        self.area_value.configure(text=f"{s.cleaning_area} m²")
        self.time_value.configure(text=f"{s.cleaning_time} min")
        self.mode_info.configure(text=s.mode_name)
        self.deposit_info.configure(text=s.door_name)
        self.mop_info.configure(text=s.cloth_name)
        self.fault_info.configure(text="Sin errores" if s.fault == 0 else f"Código {s.fault}", fg=TEXT if s.fault == 0 else RED)
        self.suction_var.set(max(1, min(4, s.suction or 1)))
        self.water_var.set(max(0, min(3, s.water)))
        for widget, value in [
            (self.side_brush_info, s.side_brush_life),
            (self.main_brush_info, s.main_brush_life),
            (self.hepa_info, s.hepa_life),
            (self.mop_life_info, s.mop_life),
        ]:
            label, bar = widget
            label.configure(text=f"{value}%")
            bar["value"] = value
        self._set_connection(True, f"Conectado · {self.settings.get('ip', '')}")

    def _run_command(self, description, function):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el Xiaomi Vacuum E10.")
            return
        self._set_banner(description)

        def worker():
            try:
                function()
                self.after(0, lambda: self._set_banner("Comando enviado correctamente."))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _selected_clean_mode(self):
        return {"Aspirar": 0, "Aspirar + trapear": 1, "Trapear": 2}[self.mode_var.get()]

    def start_clean(self):
        mode = self._selected_clean_mode()
        self._run_command("Iniciando limpieza global…", lambda: self.vacuum.start(mode))

    def start_edge_clean(self):
        mode = self._selected_clean_mode()
        self._run_command("Iniciando limpieza por bordes…", lambda: self.vacuum.start_edge(mode))

    def start_spiral_clean(self):
        mode = self._selected_clean_mode()
        self._run_command("Iniciando limpieza en espiral…", lambda: self.vacuum.start_spiral(mode))

    def stop_clean(self):
        self._run_command("Deteniendo limpieza…", self.vacuum.stop if self.vacuum else lambda: None)

    def dock(self):
        self._run_command("Enviando el robot a la base…", self.vacuum.dock if self.vacuum else lambda: None)

    def locate(self):
        self._run_command("Haciendo sonar el robot…", self.vacuum.locate if self.vacuum else lambda: None)

    def set_suction(self, level):
        self._run_command("Ajustando succión…", lambda: self.vacuum.set_suction(int(level)))

    def set_water(self, level):
        self._run_command("Ajustando nivel de agua…", lambda: self.vacuum.set_water(int(level)))

    def manual(self, direction):
        if self.vacuum:
            threading.Thread(target=lambda: self._safe_manual(direction), daemon=True).start()

    def _safe_manual(self, direction):
        try:
            self.vacuum.manual(direction)
        except Exception as exc:
            self.after(0, lambda: self._set_banner(f"Control manual no disponible: {exc}"))

    def open_setup(self):
        SetupDialog(self)

    def _schedule_update_check(self):
        if self.updating:
            return
        self.updating = True

        def worker():
            try:
                update = check_for_update()
                if update:
                    self.after(0, lambda: self._set_banner(f"Nueva versión {update['version']} encontrada. Actualizando automáticamente…"))
                    download_and_install(update, lambda text: self.after(0, lambda t=text: self._set_banner(t)))
                    self.after(0, self.destroy)
                    return
            except Exception as exc:
                self.after(0, lambda: self._set_banner(f"No se pudo comprobar la actualización: {exc}"))
            finally:
                self.updating = False
                if self.winfo_exists():
                    self.after(30 * 60 * 1000, self._schedule_update_check)

        threading.Thread(target=worker, daemon=True).start()


class SetupDialog(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Configurar Xiaomi Vacuum E10")
        self.geometry("620x540")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()

        tk.Label(self, text="Configurar robot", bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        tk.Label(self, text="La forma más simple es obtener IP y token desde tu cuenta Xiaomi. La contraseña no se guarda.", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=560, justify="left").pack(anchor="w", padx=24, pady=(0, 16))

        cloud = tk.Frame(self, bg=PANEL)
        cloud.pack(fill="x", padx=24, pady=5)
        tk.Label(cloud, text="Cuenta Xiaomi", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.user = self._entry(cloud, "Correo / teléfono / ID Xiaomi")
        self.password = self._entry(cloud, "Contraseña", show="•")
        region_row = tk.Frame(cloud, bg=PANEL)
        region_row.pack(fill="x", padx=16, pady=6)
        tk.Label(region_row, text="Región", bg=PANEL, fg=MUTED, width=19, anchor="w").pack(side="left")
        self.region = ttk.Combobox(region_row, state="readonly", values=["all", "us", "de", "sg", "cn", "ru", "i2"], width=16)
        self.region.set("all")
        self.region.pack(side="left")
        self.cloud_button = self.app._button(cloud, "Buscar mi E10", self.cloud_login, accent=True)
        self.cloud_button.pack(anchor="e", padx=16, pady=(8, 14))

        manual = tk.Frame(self, bg=PANEL)
        manual.pack(fill="x", padx=24, pady=12)
        tk.Label(manual, text="Conexión manual", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.ip = self._entry(manual, "IP del robot", initial=self.app.settings.get("ip", ""))
        self.token = self._entry(manual, "Token (32 caracteres)", initial=self.app.settings.get("token", ""), show="•")
        self.app._button(manual, "Guardar y conectar", self.manual_connect, accent=True).pack(anchor="e", padx=16, pady=(8, 14))

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=560, justify="left")
        self.status.pack(fill="x", padx=24, pady=4)

    def _entry(self, parent, label, initial="", show=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=16, pady=5)
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, width=19, anchor="w").pack(side="left")
        var = tk.StringVar(value=initial)
        entry = tk.Entry(row, textvariable=var, show=show or "", bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        return var

    def cloud_login(self):
        username = self.user.get().strip()
        password = self.password.get()
        if not username or not password:
            messagebox.showwarning("Datos incompletos", "Ingresá tu cuenta y contraseña Xiaomi.", parent=self)
            return
        self.cloud_button.configure(state="disabled")
        self.status.configure(text="Consultando tus dispositivos Xiaomi…")

        def worker():
            try:
                devices = discover_from_xiaomi(username, password, self.region.get())
                if not devices:
                    raise RuntimeError("No encontré un Xiaomi Vacuum E10 en esa cuenta/región.")
                device = devices[0]
                self.after(0, lambda: self._cloud_success(device, len(devices)))
            except Exception as exc:
                self.after(0, lambda: self._cloud_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _cloud_success(self, device, count):
        self.password.set("")
        self.ip.set(device["ip"])
        self.token.set(device["token"])
        suffix = f" ({count} encontrados; usando el primero)" if count > 1 else ""
        self.status.configure(text=f"Encontrado: {device['name']} · {device['ip']} · región {device['locale']}{suffix}")
        self.cloud_button.configure(state="normal")

    def _cloud_error(self, error):
        self.password.set("")
        self.status.configure(text="Xiaomi no permitió completar el acceso. Podés probar otra región o usar IP/token manuales.")
        self.cloud_button.configure(state="normal")
        messagebox.showerror("No se pudo acceder a Xiaomi", error, parent=self)

    def manual_connect(self):
        ip = self.ip.get().strip()
        token = self.token.get().strip()
        if not ip or len(token) != 32:
            messagebox.showwarning("Datos inválidos", "Ingresá la IP del robot y un token Xiaomi de 32 caracteres.", parent=self)
            return
        self.app.connect_device(ip, token)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()

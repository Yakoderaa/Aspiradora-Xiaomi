import io
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from settings_store import SettingsStore
from updater import check_for_update, download_and_install
from version import APP_NAME, VERSION
from xiaomi_cloud_qr import XiaomiQrLogin, discover_e10_from_qr
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
        self.geometry("980x700")
        self.minsize(900, 630)
        self.configure(bg=BG)
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

    def _button(self, parent, text, command, accent=False, compact=False):
        return tk.Button(
            parent, text=text, command=command,
            bg=ACCENT if accent else PANEL_2, fg="white",
            activebackground="#328edb" if accent else "#2a303b",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9 if compact else 10, "bold"),
            padx=12 if compact else 14, pady=6 if compact else 9,
        )

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
        controls = tk.Frame(main, bg=PANEL)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side = tk.Frame(main, bg=PANEL)
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        tk.Label(controls, text="Limpieza", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        mode_row = tk.Frame(controls, bg=PANEL)
        mode_row.pack(fill="x", padx=20, pady=5)
        self.mode_var = tk.StringVar(value="Aspirar")
        self.mode_combo = ttk.Combobox(mode_row, textvariable=self.mode_var, state="readonly", values=["Aspirar", "Aspirar + trapear", "Trapear"], width=22)
        self.mode_combo.pack(side="left", fill="x", expand=True)
        self._button(mode_row, "Iniciar", self.start_clean, accent=True).pack(side="left", padx=(10, 0))

        cmd = tk.Frame(controls, bg=PANEL)
        cmd.pack(fill="x", padx=20, pady=7)
        self._button(cmd, "Detener", self.stop_clean).pack(side="left", fill="x", expand=True)
        self._button(cmd, "Volver a base", self.dock).pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._button(cmd, "Encontrar", self.locate).pack(side="left", fill="x", expand=True, padx=(10, 0))

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
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(side="left", fill="x", expand=True, padx=6)
        tk.Label(frame, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        value = tk.Label(frame, text=initial, bg=PANEL, fg=TEXT, font=("Segoe UI", 18, "bold"))
        value.pack(anchor="w", padx=16, pady=(0, 13))
        return value

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

        scale = tk.Scale(wrap, from_=minimum, to=maximum, orient="horizontal", variable=variable, command=changed,
                         showvalue=False, bg=PANEL, fg=TEXT, troughcolor=PANEL_2, highlightthickness=0, activebackground=ACCENT)
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
            self._set_banner("Configurá el robot. La opción recomendada es vincular tu cuenta Xiaomi mediante QR.")

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
                msg = str(exc).strip() or "El robot no respondió correctamente."
                self.after(0, lambda: self._on_connect_error(msg, quiet))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected(self, ip):
        self._set_connection(True, f"Conectado · {ip}")
        self._set_banner("Control local activo. PC y robot se comunican por tu router.")
        self._start_polling()

    def _on_connect_error(self, error, quiet):
        self._set_connection(False)
        self._set_banner("No se pudo conectar. Revisá que el robot siga conectado al mismo router.")
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
        for widget, remaining in [
            (self.side_brush_info, s.side_brush_life), (self.main_brush_info, s.main_brush_life),
            (self.hepa_info, s.hepa_life), (self.mop_life_info, s.mop_life),
        ]:
            label, bar = widget
            label.configure(text=f"{remaining}%")
            bar["value"] = remaining
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
                self.after(0, lambda: messagebox.showerror("Error", str(exc) or "El robot rechazó el comando."))

        threading.Thread(target=worker, daemon=True).start()

    def start_clean(self):
        mode = {"Aspirar": 0, "Aspirar + trapear": 1, "Trapear": 2}[self.mode_var.get()]
        self._run_command("Iniciando limpieza…", lambda: self.vacuum.start(mode))

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
                try:
                    if self.winfo_exists():
                        self.after(30 * 60 * 1000, self._schedule_update_check)
                except tk.TclError:
                    pass

        threading.Thread(target=worker, daemon=True).start()


class SetupDialog(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.qr_window = None
        self.title("Configurar Xiaomi Vacuum E10")
        self.geometry("650x650")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()

        tk.Label(self, text="Configurar robot", bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        tk.Label(self, text="Recomendado: vinculá tu cuenta con un QR. No tenés que escribir ni guardar tu contraseña de Xiaomi.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=580, justify="left").pack(anchor="w", padx=24, pady=(0, 14))

        qr = tk.Frame(self, bg=PANEL)
        qr.pack(fill="x", padx=24, pady=5)
        tk.Label(qr, text="Vincular con Xiaomi", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(qr, text="Generamos un QR de inicio de sesión de Xiaomi. Escanealo con tu celular y aprobá el acceso.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=540, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        region_row = tk.Frame(qr, bg=PANEL)
        region_row.pack(fill="x", padx=16, pady=6)
        tk.Label(region_row, text="Región", bg=PANEL, fg=MUTED, width=19, anchor="w").pack(side="left")
        self.region = ttk.Combobox(region_row, state="readonly", values=["all", "us", "de", "sg", "cn", "ru", "tw", "in", "i2"], width=16)
        self.region.set("all")
        self.region.pack(side="left")
        self.qr_button = self.app._button(qr, "Conectar con QR", self.start_qr, accent=True)
        self.qr_button.pack(anchor="e", padx=16, pady=(8, 14))

        password_box = tk.Frame(self, bg=PANEL)
        password_box.pack(fill="x", padx=24, pady=12)
        tk.Label(password_box, text="Cuenta y contraseña · alternativo", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(password_box, text="Puede fallar si Xiaomi exige CAPTCHA o verificación en dos pasos.", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(0, 6))
        self.user = self._entry(password_box, "Correo / teléfono / ID")
        self.password = self._entry(password_box, "Contraseña", show="•")
        self.password_button = self.app._button(password_box, "Probar contraseña", self.cloud_login)
        self.password_button.pack(anchor="e", padx=16, pady=(7, 12))

        manual = tk.Frame(self, bg=PANEL)
        manual.pack(fill="x", padx=24, pady=2)
        tk.Label(manual, text="Conexión manual", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        self.ip = self._entry(manual, "IP del robot", initial=self.app.settings.get("ip", ""))
        self.token = self._entry(manual, "Token (32 caracteres)", initial=self.app.settings.get("token", ""), show="•")
        self.app._button(manual, "Guardar y conectar", self.manual_connect, accent=True).pack(anchor="e", padx=16, pady=(7, 12))

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=580, justify="left")
        self.status.pack(fill="x", padx=24, pady=8)

    def _entry(self, parent, label, initial="", show=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, width=19, anchor="w").pack(side="left")
        var = tk.StringVar(value=initial)
        tk.Entry(row, textvariable=var, show=show or "", bg=PANEL_2, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=7)
        return var

    def start_qr(self):
        self.qr_button.configure(state="disabled")
        self.status.configure(text="Generando código QR seguro de Xiaomi…")

        def worker():
            try:
                login = XiaomiQrLogin()
                info = login.begin()
                self.after(0, lambda: self._show_qr(login, info))
            except Exception as exc:
                msg = str(exc).strip() or "Xiaomi no permitió generar el código QR."
                self.after(0, lambda: self._qr_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _show_qr(self, login, info):
        self.status.configure(text="QR listo. Escanealo con tu celular y completá el inicio de sesión de Xiaomi.")
        self.qr_window = QrDialog(self, info)

        def worker():
            try:
                login.wait_for_login()
                devices = discover_e10_from_qr(login, self.region.get())
                if not devices:
                    raise RuntimeError("La cuenta inició sesión, pero no encontré un Xiaomi Vacuum E10. Dejá Región en 'all' y probá nuevamente.")
                device = devices[0]
                self.after(0, lambda: self._qr_success(device, len(devices)))
            except Exception as exc:
                msg = str(exc).strip() or "No se pudo completar el inicio de sesión por QR."
                self.after(0, lambda: self._qr_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _qr_success(self, device, count):
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.destroy()
        self.ip.set(device["ip"])
        self.token.set(device["token"])
        suffix = f" ({count} E10 encontrados; usando el primero)" if count > 1 else ""
        self.status.configure(text=f"Encontrado: {device['name']} · {device['ip']} · región {device['locale']}{suffix}")
        self.app.connect_device(device["ip"], device["token"])
        self.after(700, self.destroy)

    def _qr_error(self, error):
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.destroy()
        self.qr_button.configure(state="normal")
        self.status.configure(text=error)
        messagebox.showerror("No se pudo vincular con Xiaomi", error, parent=self)

    def cloud_login(self):
        username = self.user.get().strip()
        password = self.password.get()
        if not username or not password:
            messagebox.showwarning("Datos incompletos", "Ingresá tu cuenta y contraseña Xiaomi.", parent=self)
            return
        self.password_button.configure(state="disabled")
        self.status.configure(text="Probando el método de contraseña…")

        def worker():
            try:
                devices = discover_from_xiaomi(username, password, self.region.get())
                if not devices:
                    raise RuntimeError("No encontré un Xiaomi Vacuum E10 en esa cuenta/región.")
                self.after(0, lambda: self._password_success(devices[0], len(devices)))
            except Exception as exc:
                msg = str(exc).strip()
                if not msg or msg.lower() == "none":
                    msg = "Xiaomi rechazó el inicio por contraseña. Usá 'Conectar con QR', que soporta las verificaciones actuales de la cuenta."
                self.after(0, lambda: self._password_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _password_success(self, device, count):
        self.password.set("")
        self.password_button.configure(state="normal")
        self.ip.set(device["ip"])
        self.token.set(device["token"])
        self.status.configure(text=f"Encontrado: {device['name']} · {device['ip']} · región {device['locale']}")
        self.app.connect_device(device["ip"], device["token"])
        self.after(700, self.destroy)

    def _password_error(self, error):
        self.password.set("")
        self.password_button.configure(state="normal")
        self.status.configure(text=error)
        messagebox.showerror("No se pudo acceder a Xiaomi", error, parent=self)

    def manual_connect(self):
        ip = self.ip.get().strip()
        token = self.token.get().strip()
        if not ip or len(token) != 32:
            messagebox.showwarning("Datos inválidos", "Ingresá la IP del robot y un token Xiaomi de 32 caracteres.", parent=self)
            return
        self.app.connect_device(ip, token)
        self.destroy()


class QrDialog(tk.Toplevel):
    def __init__(self, parent, info):
        super().__init__(parent)
        self.title("Iniciar sesión con Xiaomi")
        self.geometry("430x520")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent)

        tk.Label(self, text="Escaneá el QR", bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(pady=(20, 4))
        tk.Label(self, text="Usá la cámara de tu celular y completá el inicio de sesión de Xiaomi. No compartas este QR.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=370, justify="center").pack(padx=20, pady=(0, 12))

        image = Image.open(io.BytesIO(info.image)).convert("RGB")
        image.thumbnail((300, 300), Image.Resampling.LANCZOS)
        self.qr_photo = ImageTk.PhotoImage(image)
        tk.Label(self, image=self.qr_photo, bg="white", padx=12, pady=12).pack(pady=4)
        tk.Label(self, text=f"El código vence aproximadamente en {info.expires_seconds} segundos.", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=(8, 4))
        parent.app._button(self, "Abrir inicio de sesión en el navegador", lambda: webbrowser.open(info.login_url)).pack(pady=8)


if __name__ == "__main__":
    App().mainloop()

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import app_v18
from robot_plans import start_whole_clean, sync_virtual_walls, wait_for_cleaning_cycle
from windows_integration import (
    apply_window_icon,
    mi_home_ico,
    mi_home_png,
    set_app_user_model_id,
    set_run_at_login,
)

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray = None
    Image = None
    ImageDraw = None

CARD = app_v18.CARD
CARD_ALT = app_v18.CARD_ALT
TEXT = app_v18.TEXT
MUTED = app_v18.MUTED
BORDER = app_v18.BORDER
GREEN = app_v18.GREEN
RED = app_v18.RED
ACCENT = app_v18.app_v17.ACCENT


class App(app_v18.App):
    """v19: integración Windows completa, bandeja y acciones rápidas."""

    MAX_QUICK_ACTIONS = 6

    def __init__(self):
        # El AppUserModelID debe existir antes de crear la ventana Tk para que
        # Windows use el icono del ejecutable también en la barra de tareas.
        set_app_user_model_id()
        self._tray_icon = None
        self._tray_thread = None
        self._tray_ready = False
        self._tray_force_exit = False
        self._quick_panel = None
        self._quick_config_window = None
        self._last_tray_battery = None
        self._last_tray_status_name = "Sin conexión"
        self._started_with_tray_flag = "--tray" in sys.argv
        super().__init__()

        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._window_close_requested)
        self._install_windows_settings_card()
        self._sync_startup_registration(quiet=True)
        self._start_tray_icon()

        if self._started_with_tray_flag:
            # Esperamos a que el icono exista antes de ocultar la ventana, para
            # no dejar una app invisible si la bandeja no pudo inicializarse.
            self.after(900, self._startup_minimize_if_ready)

    # ---------------------------------------------------------- icono/bandeja
    def _tray_image(self):
        if Image is None:
            return None
        for path in (mi_home_png(), mi_home_ico()):
            try:
                if path.exists():
                    return Image.open(path).convert("RGBA")
            except Exception:
                pass
        # Fallback visual sólo si el recurso empaquetado faltara.
        image = Image.new("RGBA", (128, 128), (30, 199, 151, 255))
        if ImageDraw is not None:
            draw = ImageDraw.Draw(image)
            draw.ellipse((34, 34, 94, 94), outline="white", width=9)
            draw.rectangle((57, 22, 71, 44), fill="white")
        return image

    def _tray_battery_text(self):
        if self._last_tray_battery is None:
            return "Batería: —"
        return f"Batería: {int(self._last_tray_battery)}% · {self._last_tray_status_name}"

    def _build_tray_menu(self):
        if pystray is None:
            return None
        Item = pystray.MenuItem
        Menu = pystray.Menu
        return Menu(
            # En Windows un item default invisible se activa con clic izquierdo.
            Item("Acciones rápidas", lambda icon, item: self._post_ui("tray_primary"), default=True, visible=False),
            Item(lambda item: self._tray_battery_text(), lambda icon, item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Abrir Aspiradora Xiaomi", lambda icon, item: self._post_ui("tray_open")),
            Item("Volver a la base", lambda icon, item: self._post_ui("tray_dock")),
            Item("Detener / pausar", lambda icon, item: self._post_ui("tray_stop")),
            Item("Iniciar mapeo…", lambda icon, item: self._post_ui("tray_quick_action", "map")),
            pystray.Menu.SEPARATOR,
            Item("Buscar actualizaciones", lambda icon, item: self._post_ui("tray_update")),
            Item("Salir", lambda icon, item: self._post_ui("tray_exit")),
        )

    def _start_tray_icon(self):
        if pystray is None or self._tray_icon is not None:
            return
        image = self._tray_image()
        if image is None:
            return
        try:
            self._tray_icon = pystray.Icon(
                "Aspiradora Xiaomi",
                image,
                "Aspiradora Xiaomi",
                self._build_tray_menu(),
            )
        except Exception:
            self._tray_icon = None
            return

        def runner():
            try:
                self._tray_icon.run(setup=self._tray_setup)
            except Exception:
                self._tray_ready = False

        self._tray_thread = threading.Thread(target=runner, name="AspiradoraXiaomiTray", daemon=True)
        self._tray_thread.start()

    def _tray_setup(self, icon):
        try:
            icon.visible = True
            self._tray_ready = True
            self._post_ui("tray_ready")
        except Exception:
            self._tray_ready = False

    def _update_tray_metadata(self):
        icon = self._tray_icon
        if not icon or not self._tray_ready:
            return
        try:
            icon.title = f"Aspiradora Xiaomi · {self._tray_battery_text()}"
            icon.update_menu()
        except Exception:
            pass

    def _startup_minimize_if_ready(self):
        if self._tray_ready and bool(self.settings.get("start_minimized_to_tray", True)):
            self._hide_to_tray()

    def _hide_to_tray(self):
        if self._tray_ready:
            try:
                if self._quick_panel and self._quick_panel.winfo_exists():
                    self._quick_panel.destroy()
                self.withdraw()
            except Exception:
                pass

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _window_close_requested(self):
        if bool(self.settings.get("close_to_tray", True)) and self._tray_ready:
            self._hide_to_tray()
            return
        self._exit_application()

    def _exit_application(self):
        self._tray_force_exit = True
        self.destroy()

    def destroy(self):
        self._closing = True
        icon = self._tray_icon
        self._tray_icon = None
        self._tray_ready = False
        if icon:
            try:
                icon.stop()
            except Exception:
                pass
        try:
            super().destroy()
        except tk.TclError:
            pass

    # --------------------------------------------------------- panel izquierdo
    def _quick_action_options(self):
        options = [
            ("Aspirar toda la casa", "clean_all"),
            ("Volver a la base", "dock"),
            ("Detener / pausar", "stop"),
            ("Iniciar mapeo", "map"),
            ("Aspirar y después mapear", "clean_map"),
            ("Abrir aplicación", "open"),
        ]
        if self.plan_store:
            for zone in self.plan_store.snapshot().get("zones", []):
                options.append((f"Aspirar zona · {zone.get('name', 'Zona')}", f"zone:{zone.get('id')}"))
        return options

    def _quick_action_label(self, code):
        mapping = dict((value, label) for label, value in self._quick_action_options())
        if code in mapping:
            return mapping[code]
        if str(code).startswith("zone:"):
            return "Zona eliminada"
        return str(code)

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
        outer = tk.Frame(win, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=CARD, padx=14, pady=12)
        body.pack(fill="both", expand=True)

        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="Aspiradora Xiaomi", bg=CARD, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(
            top,
            text="×",
            command=win.destroy,
            bg=CARD,
            fg=MUTED,
            relief="flat",
            bd=0,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        ).pack(side="right")

        battery = self._tray_battery_text()
        tk.Label(body, text=battery, bg=CARD, fg=GREEN if self._last_tray_battery is not None else MUTED, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 10))

        actions = list(self.settings.get("tray_quick_actions") or [])[: self.MAX_QUICK_ACTIONS]
        if not actions:
            tk.Label(body, text="No hay acciones rápidas configuradas.", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=8)
        for code in actions:
            label = self._quick_action_label(code)
            button = tk.Button(
                body,
                text=label,
                command=lambda c=code: self._quick_panel_action(c),
                bg=CARD_ALT,
                fg=TEXT,
                activebackground="#eeeeee",
                relief="flat",
                bd=0,
                anchor="w",
                padx=10,
                pady=7,
                cursor="hand2",
                font=("Segoe UI", 9),
            )
            button.pack(fill="x", pady=2)

        tk.Button(
            body,
            text="Abrir aplicación",
            command=lambda: self._quick_panel_action("open"),
            bg="#e8f5ee",
            fg=GREEN,
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", pady=(8, 0))

        win.update_idletasks()
        width = max(330, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        px, py = self.winfo_pointerxy()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(max(8, px - width + 20), max(8, sw - width - 8))
        y = min(max(8, py - height - 12), max(8, sh - height - 8))
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.bind("<Escape>", lambda event: win.destroy())
        try:
            win.focus_force()
        except Exception:
            pass

    def _quick_panel_action(self, code):
        if self._quick_panel and self._quick_panel.winfo_exists():
            self._quick_panel.destroy()
        self._quick_panel = None
        self._execute_quick_action(code)

    # ------------------------------------------------------ ejecutar acciones
    def _need_robot(self):
        if self.vacuum:
            return True
        self._restore_from_tray()
        messagebox.showwarning("Robot desconectado", "El E10 todavía no está conectado.", parent=self)
        return False

    def _execute_quick_action(self, code):
        code = str(code or "")
        if code == "open":
            self._restore_from_tray()
            return
        if not self._need_robot():
            return

        if code == "dock":
            self._run_command("Volviendo a la base…", self.vacuum.dock)
            return
        if code == "stop":
            if self.mapping_active:
                self.finish_mapping()
            else:
                self._run_command("Deteniendo…", self.vacuum.stop)
            return
        if code == "map":
            self._restore_from_tray()
            self.after(80, self.start_new_mapping)
            return
        if code == "clean_all":
            suction = max(1, int(self.suction_var.get() or 1))
            vacuum = self.vacuum
            plan = self.plan_store.snapshot() if self.plan_store else {}

            def command():
                sync_virtual_walls(vacuum, plan)
                return start_whole_clean(vacuum, "vacuum", suction, 0)

            self._run_command("Aspirando toda la casa…", command)
            return
        if code.startswith("zone:"):
            zone_id = code.split(":", 1)[1]
            plan = self.plan_store.snapshot() if self.plan_store else {}
            zone = next((z for z in plan.get("zones", []) if str(z.get("id")) == zone_id), None)
            if not zone:
                self._restore_from_tray()
                messagebox.showwarning("Acción rápida", "Esa zona ya no existe en el mapa activo.", parent=self)
                return
            self._run_zones_now([zone], "vacuum", max(1, int(self.suction_var.get() or 1)), 0)
            return
        if code == "clean_map":
            self._restore_from_tray()
            if not messagebox.askyesno(
                "Aspirar y mapear",
                "Primero voy a aspirar toda la casa. Cuando termine, abriré el Paso 1 de mapeo para que confirmes el mapa nuevo.\n\n¿Continuar?",
                parent=self,
            ):
                return
            suction = max(1, int(self.suction_var.get() or 1))
            vacuum = self.vacuum
            plan = self.plan_store.snapshot() if self.plan_store else {}

            def worker():
                try:
                    sync_virtual_walls(vacuum, plan)
                    start_whole_clean(vacuum, "vacuum", suction, 0)
                    wait_for_cleaning_cycle(vacuum)
                    self._post_ui("tray_clean_then_map_ready")
                except Exception as exc:
                    self._post_ui("tray_clean_then_map_error", str(exc).strip() or "No se pudo completar la aspiración previa.")

            threading.Thread(target=worker, daemon=True).start()
            self._set_banner("Aspirando toda la casa. Después continuará el mapeo…")
            return

    # ---------------------------------------------------------- eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "status_ok" and payload:
            status = payload[0]
            try:
                self._last_tray_battery = int(getattr(status, "battery", 0) or 0)
                self._last_tray_status_name = str(getattr(status, "status_name", "Conectado"))
            except Exception:
                pass
            result = super()._handle_ui_event(kind, payload)
            self._update_tray_metadata()
            return result
        if kind == "connect_error":
            self._last_tray_status_name = "Sin conexión"
            self._last_tray_battery = None
            result = super()._handle_ui_event(kind, payload)
            self._update_tray_metadata()
            return result
        if kind == "tray_ready":
            self._update_tray_metadata()
            return
        if kind == "tray_primary":
            self._show_quick_panel()
            return
        if kind == "tray_open":
            self._restore_from_tray()
            return
        if kind == "tray_dock":
            self._execute_quick_action("dock")
            return
        if kind == "tray_stop":
            self._execute_quick_action("stop")
            return
        if kind == "tray_update":
            self._restore_from_tray()
            self.manual_check_for_updates()
            return
        if kind == "tray_exit":
            self._exit_application()
            return
        if kind == "tray_quick_action":
            self._execute_quick_action(payload[0] if payload else "")
            return
        if kind == "tray_clean_then_map_ready":
            self._restore_from_tray()
            self._set_banner("Aspiración terminada. Listo para comenzar el mapeo.")
            self.after(100, self.start_new_mapping)
            return
        if kind == "tray_clean_then_map_error":
            self._restore_from_tray()
            messagebox.showerror("Aspirar y mapear", str(payload[0]), parent=self)
            return
        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------- configuración UI
    def _install_windows_settings_card(self):
        page = self._page("settings")
        card = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=5)
        tk.Label(card, text="Windows y bandeja de sistema", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 5))
        tk.Label(
            card,
            text="El clic izquierdo sobre el icono de Mi Home muestra batería y acciones rápidas. El clic derecho abre el menú de control.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=760,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        self.start_windows_var = tk.BooleanVar(value=bool(self.settings.get("start_with_windows", False)))
        self.close_tray_var = tk.BooleanVar(value=bool(self.settings.get("close_to_tray", True)))

        tk.Checkbutton(
            card,
            text="Iniciar Aspiradora Xiaomi con Windows, minimizada en la bandeja",
            variable=self.start_windows_var,
            command=self._toggle_start_with_windows,
            bg=CARD,
            activebackground=CARD,
            fg=TEXT,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=4)
        tk.Checkbutton(
            card,
            text="Al cerrar con X, mantener la aplicación en la bandeja",
            variable=self.close_tray_var,
            command=self._toggle_close_to_tray,
            bg=CARD,
            activebackground=CARD,
            fg=TEXT,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=4)

        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=20, pady=(10, 18))
        self._button(row, "Configurar acciones rápidas", self.open_quick_actions_config, accent=True).pack(side="left")
        tk.Label(row, text="Hasta 6 accesos · las zonas dependen del mapa activo", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)

    def _toggle_start_with_windows(self):
        enabled = bool(self.start_windows_var.get())
        old = bool(self.settings.get("start_with_windows", False))
        self.settings["start_with_windows"] = enabled
        self.settings["start_minimized_to_tray"] = True
        try:
            set_run_at_login(enabled, minimized=True)
            self.store.save(self.settings)
            self._set_banner("Inicio con Windows activado." if enabled else "Inicio con Windows desactivado.")
        except Exception as exc:
            self.settings["start_with_windows"] = old
            self.start_windows_var.set(old)
            messagebox.showerror("Inicio con Windows", str(exc), parent=self)

    def _toggle_close_to_tray(self):
        self.settings["close_to_tray"] = bool(self.close_tray_var.get())
        self.store.save(self.settings)

    def _sync_startup_registration(self, quiet=False):
        try:
            set_run_at_login(bool(self.settings.get("start_with_windows", False)), minimized=True)
        except Exception as exc:
            if not quiet:
                messagebox.showerror("Inicio con Windows", str(exc), parent=self)

    def open_quick_actions_config(self):
        if self._quick_config_window and self._quick_config_window.winfo_exists():
            self._quick_config_window.destroy()
        win = tk.Toplevel(self)
        self._quick_config_window = win
        win.title("Acciones rápidas de la bandeja")
        win.geometry("520x500")
        win.resizable(False, False)
        win.transient(self)
        apply_window_icon(win)

        frame = tk.Frame(win, padx=20, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Acciones del clic izquierdo", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="Elegí hasta seis acciones. Las zonas mostradas pertenecen al mapa activo.",
            fg="#777",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 14))

        options = self._quick_action_options()
        labels = ["—"] + [label for label, code in options]
        label_to_code = {label: code for label, code in options}
        code_to_label = {code: label for label, code in options}
        current = list(self.settings.get("tray_quick_actions") or [])[: self.MAX_QUICK_ACTIONS]
        vars_ = []
        for index in range(self.MAX_QUICK_ACTIONS):
            row = tk.Frame(frame)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=f"{index + 1}", width=3, anchor="w", font=("Segoe UI", 9, "bold")).pack(side="left")
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
            self._set_banner("Acciones rápidas de la bandeja actualizadas.")
            self._update_tray_metadata()

        self._button(frame, "Guardar", save, accent=True).pack(fill="x", pady=(18, 0))


if __name__ == "__main__":
    app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

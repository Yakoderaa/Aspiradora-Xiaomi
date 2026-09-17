import math
import tkinter as tk
from tkinter import messagebox, simpledialog

import app_v23

BG = app_v23.BG
SURFACE = app_v23.SURFACE
SURFACE_2 = app_v23.SURFACE_2
SIDEBAR = app_v23.SIDEBAR
SIDEBAR_MUTED = app_v23.SIDEBAR_MUTED
TEXT = app_v23.TEXT
MUTED = app_v23.MUTED
BORDER = app_v23.BORDER
ACCENT = app_v23.ACCENT
ACCENT_HOVER = app_v23.ACCENT_HOVER
ACCENT_SOFT = app_v23.ACCENT_SOFT
GREEN = app_v23.GREEN
GREEN_SOFT = app_v23.GREEN_SOFT
RED = app_v23.RED


class App(app_v23.App):
    """v24: pantalla inicial de dispositivos + navegación dentro de Emilia."""

    GENERIC_DEVICE_NAMES = {
        "",
        "xiaomi robot vacuum e10",
        "xiaomi vacuum e10",
        "vacuum e10",
    }

    def __init__(self):
        self._device_shell = None
        self._devices_home = None
        self._device_name_label = None
        self._device_status_label = None
        self._device_battery_label = None
        self._device_card_name = None
        self._device_visual = None
        self._inside_device = False
        super().__init__()
        self.after(80, self._refresh_device_card)

    # ---------------------------------------------------------- shell / inicio
    def _build_ui(self):
        # Construye toda la UI funcional v23 y luego la convierte en el segundo
        # nivel de navegación. Así el backend sigue usando exactamente los mismos
        # widgets/atributos y no arriesgamos la lógica del E10.
        super()._build_ui()
        self._device_shell = self.sidebar.master
        self._device_shell.pack_forget()
        self._build_devices_home()
        self._install_back_to_devices_button()
        self._show_devices_home()

    def _build_devices_home(self):
        home = tk.Frame(self, bg=BG)
        self._devices_home = home

        header = tk.Frame(home, bg=BG)
        header.pack(fill="x", padx=42, pady=(34, 20))
        title = tk.Frame(header, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Dispositivos", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 28)).pack(anchor="w")
        tk.Label(
            title,
            text="Tus dispositivos Xiaomi conectados a esta PC.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(5, 0))

        account = tk.Frame(header, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        account.pack(side="right")
        tk.Label(account, text="Cuenta Xiaomi", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
            anchor="e", padx=14, pady=(8, 1)
        )
        self._device_account_label = tk.Label(
            account,
            text="Conectada por QR" if self._xiaomi_linked() else "Sin vincular",
            bg=SURFACE,
            fg=GREEN if self._xiaomi_linked() else MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self._device_account_label.pack(anchor="e", padx=14, pady=(0, 8))

        body = tk.Frame(home, bg=BG)
        body.pack(fill="both", expand=True, padx=42, pady=(0, 36))

        card = tk.Frame(body, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        card.pack(anchor="nw", fill="x", ipadx=0, ipady=0)
        card.bind("<Button-1>", lambda _e: self._open_device())

        visual_wrap = tk.Frame(card, bg="#f3f4f6", width=310, height=250, cursor="hand2")
        visual_wrap.pack(side="left", fill="y")
        visual_wrap.pack_propagate(False)
        visual_wrap.bind("<Button-1>", lambda _e: self._open_device())

        self._device_visual = tk.Canvas(visual_wrap, width=310, height=250, bg="#f3f4f6", highlightthickness=0)
        self._device_visual.pack(fill="both", expand=True)
        self._device_visual.bind("<Button-1>", lambda _e: self._open_device())
        self._draw_e10_visual()

        info = tk.Frame(card, bg=SURFACE, cursor="hand2")
        info.pack(side="left", fill="both", expand=True, padx=28, pady=26)
        info.bind("<Button-1>", lambda _e: self._open_device())

        state_row = tk.Frame(info, bg=SURFACE)
        state_row.pack(fill="x")
        state_row.bind("<Button-1>", lambda _e: self._open_device())
        self._device_status_label = tk.Label(
            state_row,
            text="●  Conectando…",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self._device_status_label.pack(side="left")
        self._device_status_label.bind("<Button-1>", lambda _e: self._open_device())

        self._device_battery_label = tk.Label(
            state_row,
            text="Batería —",
            bg=GREEN_SOFT,
            fg=GREEN,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        )
        self._device_battery_label.pack(side="right")
        self._device_battery_label.bind("<Button-1>", lambda _e: self._open_device())

        self._device_card_name = tk.Label(
            info,
            text=self._device_display_name(),
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI Semibold", 24),
        )
        self._device_card_name.pack(anchor="w", pady=(24, 3))
        self._device_card_name.bind("<Button-1>", lambda _e: self._open_device())

        model = tk.Label(
            info,
            text="Xiaomi Robot Vacuum E10",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 11),
        )
        model.pack(anchor="w")
        model.bind("<Button-1>", lambda _e: self._open_device())

        detail = tk.Label(
            info,
            text="Aspiración · trapeado · mapas · zonas · rutinas",
            bg=SURFACE,
            fg="#94a3b8",
            font=("Segoe UI", 9),
        )
        detail.pack(anchor="w", pady=(6, 0))
        detail.bind("<Button-1>", lambda _e: self._open_device())

        actions = tk.Frame(info, bg=SURFACE)
        actions.pack(fill="x", side="bottom", pady=(26, 0))
        self._button(actions, "Abrir dispositivo", self._open_device, accent=True).pack(side="left")
        self._button(actions, "Renombrar", self._rename_device_dialog, compact=True).pack(side="left", padx=(8, 0))

        future = tk.Frame(body, bg=BG)
        future.pack(anchor="nw", fill="x", pady=(18, 0))
        tk.Label(
            future,
            text="Más adelante vas a poder ver otros dispositivos Xiaomi acá.",
            bg=BG,
            fg="#94a3b8",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

    def _draw_e10_visual(self):
        c = self._device_visual
        if not c:
            return
        c.delete("all")
        # Ilustración tipo producto, sin depender de una imagen web o del diseño
        # de Mi Home. Se mantiene nítida con cualquier escala de Windows.
        c.create_oval(57, 49, 263, 231, fill="#d8dde4", outline="")
        c.create_oval(49, 39, 255, 221, fill="#ffffff", outline="#d9dee5", width=2)
        c.create_arc(49, 39, 255, 221, start=205, extent=130, style="arc", outline="#cdd3da", width=4)
        c.create_oval(117, 70, 187, 134, fill="#f8fafc", outline="#d7dce3", width=2)
        c.create_oval(137, 88, 167, 116, fill="#e9edf2", outline="#cfd5dc")
        c.create_oval(146, 97, 158, 109, fill="#64748b", outline="")
        c.create_oval(112, 164, 126, 178, fill="#eef2f6", outline="#d5dbe2")
        c.create_oval(133, 164, 147, 178, fill="#eef2f6", outline="#d5dbe2")
        c.create_line(67, 177, 48, 192, fill="#94a3b8", width=3)
        c.create_line(70, 181, 55, 201, fill="#94a3b8", width=2)
        c.create_text(152, 236, text="Robot Vacuum E10", fill="#94a3b8", font=("Segoe UI", 8, "bold"))

    def _install_back_to_devices_button(self):
        if not self._v23_nav or "home" not in self._v23_nav:
            return
        nav = self._v23_nav["home"][0].master
        btn = tk.Button(
            nav,
            text="  ←    Dispositivos",
            command=self._show_devices_home,
            bg="#182235",
            fg="#cbd5e1",
            activebackground="#253149",
            activeforeground="white",
            relief="flat",
            bd=0,
            anchor="w",
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=10,
        )
        btn.pack(fill="x", pady=(0, 10), before=self._v23_nav["home"][0])

    def _show_devices_home(self):
        self._inside_device = False
        if self._device_shell:
            self._device_shell.pack_forget()
        if self._devices_home:
            self._devices_home.pack(fill="both", expand=True)
            self._devices_home.tkraise()
        self.title("Aspiradora Xiaomi · Dispositivos")
        self._refresh_device_card()

    def _open_device(self):
        self._inside_device = True
        if self._devices_home:
            self._devices_home.pack_forget()
        if self._device_shell:
            self._device_shell.pack(fill="both", expand=True)
        self.title(f"{self._device_display_name()} · Xiaomi Robot Vacuum E10")
        self.show_page("home")

    # -------------------------------------------------------------- identidad
    def _device_display_name(self):
        value = str(self.settings.get("device_name") or "").strip()
        if value.lower() in self.GENERIC_DEVICE_NAMES:
            # Migración de esta instalación: el nombre que el usuario ya usa en
            # Xiaomi Home es Emilia. Los futuros QR guardarán el nombre cloud.
            value = "Emilia"
        return value or "Emilia"

    def _rename_device_dialog(self):
        old = self._device_display_name()
        new = simpledialog.askstring(
            "Renombrar dispositivo",
            "Nombre del dispositivo:",
            initialvalue=old,
            parent=self,
        )
        if new is None:
            return
        new = new.strip()
        if not new:
            messagebox.showinfo("Nombre", "El nombre no puede quedar vacío.", parent=self)
            return
        if len(new) > 64:
            messagebox.showinfo("Nombre", "Usá un nombre de hasta 64 caracteres.", parent=self)
            return
        self.settings["device_name"] = new
        self.store.save(self.settings)
        self._refresh_device_card()
        if self._inside_device:
            self.title(f"{new} · Xiaomi Robot Vacuum E10")
        messagebox.showinfo(
            "Nombre actualizado",
            "El nombre quedó guardado en esta aplicación.\n\n"
            "La sesión cloud actual todavía no expone una operación de renombrado verificada, "
            "por lo que no voy a afirmar que Mi Home cambió hasta poder confirmar esa llamada con Xiaomi.",
            parent=self,
        )

    def _refresh_device_card(self):
        name = self._device_display_name()
        if self._device_card_name and self._device_card_name.winfo_exists():
            self._device_card_name.configure(text=name)
        if hasattr(self, "_device_account_label") and self._device_account_label.winfo_exists():
            linked = self._xiaomi_linked()
            self._device_account_label.configure(
                text="Conectada por QR" if linked else "Sin vincular",
                fg=GREEN if linked else MUTED,
            )
        if self._device_status_label and self._device_status_label.winfo_exists():
            connected = bool(self.vacuum)
            status = self._last_tray_status_name if connected else "Desconectado"
            self._device_status_label.configure(
                text=f"●  {status}",
                fg=GREEN if connected else MUTED,
            )
        if self._device_battery_label and self._device_battery_label.winfo_exists():
            if self._last_tray_battery is None:
                self._device_battery_label.configure(text="Batería —", bg=SURFACE_2, fg=MUTED)
            else:
                self._device_battery_label.configure(
                    text=f"Batería {int(self._last_tray_battery)}%",
                    bg=GREEN_SOFT,
                    fg=GREEN,
                )

    # --------------------------------------------------------------- eventos
    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("status_ok", "connect_ok", "connect_error"):
            self.after(0, self._refresh_device_card)
        return result

    def _restore_from_tray(self):
        result = super()._restore_from_tray()
        if not self._inside_device:
            self.after(0, self._show_devices_home)
        return result


if __name__ == "__main__":
    app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

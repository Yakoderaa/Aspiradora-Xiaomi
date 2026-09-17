import tkinter as tk

import app_v20

CARD = app_v20.CARD
TEXT = app_v20.TEXT
MUTED = app_v20.MUTED
BORDER = app_v20.BORDER
GREEN = app_v20.GREEN


class App(app_v20.App):
    """v21: consolidación final de Configuración sobre una única página."""

    def _settings_page(self):
        return self._pages.get("settings") or self._page("settings")

    def _install_windows_settings_card(self):
        page = self._settings_page()
        card = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=5)
        tk.Label(
            card,
            text="Windows y bandeja de sistema",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 5))
        tk.Label(
            card,
            text=(
                "Clic izquierdo: batería y acciones rápidas configurables. "
                "Clic derecho: Abrir, Volver a base, Detener, Mapear, Actualizar y Salir."
            ),
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
        tk.Label(
            row,
            text="Hasta 6 accesos · las zonas dependen del mapa activo",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=10)

    def _install_xiaomi_account_card(self):
        page = self._settings_page()
        card = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=5)
        self._account_card = card

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=20, pady=(16, 5))
        tk.Label(head, text="Cuenta Xiaomi", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        self._account_status_label = tk.Label(head, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self._account_status_label.pack(side="right")

        self._account_user_label = tk.Label(card, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self._account_user_label.pack(fill="x", padx=20, pady=(3, 10))
        self._account_button = self._button(card, "", self.open_setup, accent=True, compact=True)
        self._account_button.pack(anchor="w", padx=20, pady=(0, 16))


if __name__ == "__main__":
    app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

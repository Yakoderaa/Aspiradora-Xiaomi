import tkinter as tk
from tkinter import messagebox, simpledialog

import app_v26


class App(app_v26.App):
    """v27: posición fresca, succión en caliente y updates de repo privado."""

    def __init__(self):
        super().__init__()
        self.after(120, self._install_private_updates_card)

    # ------------------------------------------------------- succión en caliente
    def _choose_suction(self, value):
        """Cambia potencia sin detener ni reiniciar la limpieza actual."""
        level = max(1, min(4, int(value)))
        self.suction_var.set(level)
        self.settings["suction"] = level
        self.store.save(self.settings)
        self._refresh_choice_buttons()

        if not self.vacuum:
            return

        # Es sólo una escritura de la propiedad fan-speed (7/5). No llamamos a
        # start(), stop(), pause() ni cambiamos sweep-type, por lo que la tarea
        # actual continúa exactamente donde está.
        labels = {1: "Silenciosa", 2: "Normal", 3: "Fuerte", 4: "Turbo"}
        self._run_command(
            f"Cambiando succión a {labels.get(level, level)}…",
            lambda: self.vacuum.set_suction(level),
        )

    # ------------------------------------------------- GitHub repo privado
    def _install_private_updates_card(self):
        page = getattr(self, "_pages", {}).get("settings")
        if page is None or not page.winfo_exists():
            return
        if getattr(self, "_private_updates_card", None):
            return

        card = tk.Frame(page, bg="#ffffff", highlightthickness=1, highlightbackground="#e2e8f0")
        card.pack(fill="x", padx=5, pady=6)
        self._private_updates_card = card

        tk.Label(
            card,
            text="Actualizaciones privadas",
            bg="#ffffff",
            fg="#111827",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(
            card,
            text=(
                "Como el repositorio de GitHub es privado, la app necesita acceso de sólo lectura "
                "para consultar y descargar sus releases. El token se cifra con DPAPI de Windows."
            ),
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=820,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        row = tk.Frame(card, bg="#ffffff")
        row.pack(fill="x", padx=20, pady=(0, 16))
        self._github_update_status = tk.Label(
            row,
            text="",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 9, "bold"),
        )
        self._github_update_status.pack(side="left")

        self._button(row, "Configurar acceso", self._configure_github_updates, compact=True).pack(side="right", padx=(8, 0))
        self._button(row, "Quitar acceso", self._clear_github_updates, compact=True).pack(side="right")
        self._refresh_github_update_status()

    def _refresh_github_update_status(self):
        label = getattr(self, "_github_update_status", None)
        if label is None:
            return
        configured = bool(str(self.settings.get("github_token") or "").strip())
        label.configure(
            text="Acceso configurado" if configured else "Acceso pendiente",
            fg="#16a34a" if configured else "#b45309",
        )

    def _configure_github_updates(self):
        token = simpledialog.askstring(
            "Acceso a GitHub privado",
            "Pegá un Fine-grained personal access token de GitHub con acceso de lectura a este repositorio.\n\n"
            "El token queda cifrado para tu usuario de Windows.",
            parent=self,
            show="•",
        )
        if token is None:
            return
        token = token.strip()
        if not token:
            messagebox.showwarning("GitHub", "El token está vacío.", parent=self)
            return
        self.settings["github_token"] = token
        self.store.save(self.settings)
        self._refresh_github_update_status()
        self._set_banner("Acceso a releases privadas de GitHub configurado.")

    def _clear_github_updates(self):
        self.settings["github_token"] = ""
        self.store.save(self.settings)
        self._refresh_github_update_status()
        self._set_banner("Acceso privado de GitHub eliminado de esta PC.")


if __name__ == "__main__":
    app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
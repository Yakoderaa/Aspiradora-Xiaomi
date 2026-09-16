import threading
from tkinter import messagebox

import app_v6
from updater import check_for_update, download_and_install
from version import VERSION


class App(app_v6.App):
    """v7: agrega búsqueda manual de actualizaciones visible en la cabecera."""

    def __init__(self):
        super().__init__()
        self._add_manual_update_button()

    def _add_manual_update_button(self):
        parent = self.connection_label.master
        self.manual_update_button = self._button(
            parent,
            "Buscar actualizaciones",
            self.manual_check_for_updates,
            compact=True,
        )
        self.manual_update_button.pack(side="left", padx=(8, 0))

    def _set_manual_update_idle(self):
        self.updating = False
        if hasattr(self, "manual_update_button") and self.manual_update_button.winfo_exists():
            self.manual_update_button.configure(text="Buscar actualizaciones", state="normal")

    def manual_check_for_updates(self):
        if self.updating:
            messagebox.showinfo(
                "Actualizaciones",
                "Ya estoy comprobando o instalando una actualización.",
                parent=self,
            )
            return

        self.updating = True
        self.manual_update_button.configure(text="Buscando…", state="disabled")
        self._set_banner("Buscando actualizaciones en GitHub…")

        def worker():
            try:
                update = check_for_update()
                if not update:
                    self.after(0, self._manual_no_update)
                    return
                self.after(0, lambda: self._manual_update_found(update))
            except Exception as exc:
                msg = str(exc).strip() or "No se pudo consultar GitHub."
                self.after(0, lambda: self._manual_update_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _manual_no_update(self):
        self._set_banner(f"Aspiradora Xiaomi v{VERSION} está actualizada.")
        messagebox.showinfo(
            "Sin actualizaciones",
            f"Ya tenés la última versión disponible: v{VERSION}.",
            parent=self,
        )
        self._set_manual_update_idle()

    def _manual_update_found(self, update):
        version = update.get("version", "nueva")
        self._set_banner(f"Actualización v{version} disponible.")
        install = messagebox.askyesno(
            "Actualización disponible",
            f"Hay una nueva versión: v{version}.\n\n¿Querés descargarla e instalarla ahora?",
            parent=self,
        )
        if not install:
            self._set_manual_update_idle()
            return

        self.manual_update_button.configure(text="Descargando…", state="disabled")

        def worker():
            try:
                download_and_install(
                    update,
                    lambda text: self.after(0, lambda t=text: self._set_banner(t)),
                )
                self.after(0, self.destroy)
            except Exception as exc:
                msg = str(exc).strip() or "No se pudo instalar la actualización."
                self.after(0, lambda: self._manual_update_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _manual_update_error(self, message):
        self._set_banner(f"Error al actualizar: {message}")
        messagebox.showerror("Actualización", message, parent=self)
        self._set_manual_update_idle()


if __name__ == "__main__":
    App().mainloop()

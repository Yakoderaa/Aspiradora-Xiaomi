import os
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import app_v8

CARD = app_v8.CARD
MUTED = app_v8.MUTED


class App(app_v8.App):
    """v9: corrige el montaje de la pantalla de mapeo y evita el crash al abrir."""

    def _build_map_page(self):
        # Importante: saltamos la implementación de app_v8 porque destruía un
        # botón y luego intentaba recorrer ese mismo widget ya destruido.
        app_v8.app_v7.App._build_map_page(self)

        page = self._pages.get("map")
        header_parent = None

        def walk(widget):
            nonlocal header_parent
            try:
                children = list(widget.winfo_children())
            except tk.TclError:
                return

            for child in children:
                removed = False
                if isinstance(child, tk.Button):
                    try:
                        text = child.cget("text")
                    except tk.TclError:
                        text = ""
                    if text in ("Crear desde cero", "Finalizar"):
                        header_parent = child.master
                        try:
                            child.destroy()
                        except tk.TclError:
                            pass
                        removed = True

                # Nunca intentamos inspeccionar un widget después de destruirlo.
                if not removed:
                    walk(child)

        if page:
            walk(page)

        if header_parent is None:
            return

        controls = tk.Frame(header_parent, bg=CARD)
        controls.pack(side="right")

        self.stop_mapping_button = self._button(
            controls,
            "Detener",
            self.finish_mapping,
            compact=True,
        )
        self.stop_mapping_button.pack(side="right", padx=(8, 0))

        self.step2_mapping_button = self._button(
            controls,
            "Paso 2 · Interior",
            self.start_interior_mapping,
            compact=True,
        )
        self.step2_mapping_button.pack(side="right", padx=(8, 0))

        self.step1_mapping_button = self._button(
            controls,
            "Paso 1 · Perímetro",
            self.start_new_mapping,
            accent=True,
            compact=True,
        )
        self.step1_mapping_button.pack(side="right")

        info_parent = self.map_status_label.master
        self.mapping_steps_info = tk.Label(
            info_parent,
            text="Paso 1: borde de habitaciones · Paso 2: completar interior",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.mapping_steps_info.pack(side="left", padx=(12, 0))


def _save_crash_log(text: str):
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
        base.mkdir(parents=True, exist_ok=True)
        (base / "crash.log").write_text(text, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        details = traceback.format_exc()
        _save_crash_log(details)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Aspiradora Xiaomi",
                "La aplicación encontró un error y guardó el detalle en:\n"
                "%LOCALAPPDATA%\\Aspiradora Xiaomi\\crash.log",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass

import tkinter as tk

import app_v24
from windows_integration import resource_path

try:
    from PIL import Image, ImageOps, ImageTk
except Exception:
    Image = None
    ImageOps = None
    ImageTk = None

SURFACE = app_v24.SURFACE
SURFACE_2 = app_v24.SURFACE_2
TEXT = app_v24.TEXT
MUTED = app_v24.MUTED
RED = app_v24.RED


class App(app_v24.App):
    """v25: foto oficial del E10 y fila Error sólo ante un fallo real."""

    # Xiaomi y otros firmwares de su ecosistema reutilizan a veces el campo de
    # error para estados operativos. No deben verse como una avería en la UI.
    NON_ERROR_STATE_CODES = {
        2102: "Volviendo a la base",
        2103: "Cargando",
        2104: "Volviendo a la base",
        2105: "Carga completa",
        2108: "Retomando recorrido",
        2109: "Continuando limpieza",
        2110: "Comprobando estado",
    }

    # Mensajes seguros y generales para fallos que sí son conocidos. Para un
    # código desconocido mostramos el número sin inventar una causa.
    FAULT_TEXT = {
        500: "Sensor de navegación sin respuesta",
        501: "Ruedas bloqueadas",
        502: "Batería demasiado baja",
        503: "Depósito no detectado",
        507: "No pudo reposicionarse",
        508: "Superficie irregular",
        509: "Revisá los sensores anticaída",
        510: "Revisá el sensor de colisión",
        511: "No pudo volver a la base",
        512: "No pudo volver a la base",
        513: "No pudo navegar",
        514: "La aspiradora está atascada",
        515: "Problema de carga",
        521: "Depósito de agua no detectado",
        522: "Mopa no detectada",
        527: "Retirá la mopa",
        528: "Depósito no detectado",
    }

    def __init__(self):
        self._e10_product_photo = None
        self._fault_row = None
        self._fault_separator = None
        super().__init__()

    # ----------------------------------------------------------- foto E10 real
    def _draw_e10_visual(self):
        canvas = getattr(self, "_device_visual", None)
        if not canvas:
            return
        canvas.delete("all")

        path = resource_path("assets", "xiaomi_robot_vacuum_e10.jpg")
        if Image is None or ImageTk is None or ImageOps is None or not path.exists():
            # Sólo como contingencia de un build incompleto: conserva un fallback
            # reconocible, pero el build final exige que la foto oficial exista.
            return super()._draw_e10_visual()

        try:
            image = Image.open(path).convert("RGB")
            # La imagen oficial es apaisada. La adaptamos a la tarjeta sin
            # deformarla y con un pequeño margen visual.
            fitted = ImageOps.fit(
                image,
                (286, 226),
                method=Image.Resampling.LANCZOS,
                centering=(0.50, 0.50),
            )
            self._e10_product_photo = ImageTk.PhotoImage(fitted)
            canvas.create_rectangle(0, 0, 310, 250, fill="#f6f7f9", outline="")
            canvas.create_image(155, 125, image=self._e10_product_photo, anchor="center")
            canvas.create_text(
                16,
                232,
                text="Xiaomi Robot Vacuum E10 · B112",
                anchor="w",
                fill="#64748b",
                font=("Segoe UI", 8, "bold"),
            )
        except Exception:
            super()._draw_e10_visual()

    # ---------------------------------------------------------- fila de error
    def _build_robot_page_v22(self):
        super()._build_robot_page_v22()
        try:
            self._fault_row = self.fault_info.master
            parent = self._fault_row.master
            children = list(parent.winfo_children())
            index = children.index(self._fault_row)
            self._fault_separator = children[index + 1] if index + 1 < len(children) else None
            self._fault_row.pack_forget()
        except Exception:
            self._fault_row = None
            self._fault_separator = None

    @staticmethod
    def _fault_code(status):
        try:
            return int(getattr(status, "fault", 0) or 0)
        except Exception:
            return 0

    def _is_real_fault(self, status):
        code = self._fault_code(status)
        if code == 0:
            return False
        if code in self.NON_ERROR_STATE_CODES:
            return False
        return True

    def _show_fault_row(self, code):
        if not self._fault_row or not self.fault_info:
            return
        description = self.FAULT_TEXT.get(code)
        text = f"{description} · Código {code}" if description else f"Fallo detectado · Código {code}"
        self.fault_info.configure(text=text, fg=RED)
        try:
            if not self._fault_row.winfo_manager():
                kwargs = {"fill": "x", "pady": 6}
                if self._fault_separator is not None:
                    kwargs["before"] = self._fault_separator
                self._fault_row.pack(**kwargs)
        except Exception:
            pass

    def _hide_fault_row(self):
        if not self._fault_row:
            return
        try:
            self.fault_info.configure(text="", fg=TEXT)
            if self._fault_row.winfo_manager():
                self._fault_row.pack_forget()
        except Exception:
            pass

    def _render_status(self, status):
        result = super()._render_status(status)
        code = self._fault_code(status)
        if self._is_real_fault(status):
            self._show_fault_row(code)
        else:
            self._hide_fault_row()
        return result


if __name__ == "__main__":
    app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

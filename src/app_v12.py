import threading
import tkinter as tk
from tkinter import messagebox, ttk

import app_v11
from updater import download_and_install


class App(app_v11.App):
    """v12: actualización visual con descarga, instalación y relanzado automático."""

    def __init__(self):
        self._update_window = None
        self._update_progress = None
        self._update_stage_label = None
        self._update_detail_label = None
        self._update_progress_mode = None
        super().__init__()

    # --------------------------------------------------------- eventos update
    def _handle_ui_event(self, kind, payload):
        if kind == "update_stage":
            self._set_update_stage(str(payload[0]))
            return
        if kind == "update_progress":
            percent, done, total = payload
            self._set_update_progress(percent, int(done or 0), int(total or 0))
            return
        if kind == "update_install_done":
            self._set_update_stage(
                "Descarga y verificación completadas.",
                "Ahora se cerrará esta ventana y continuará el instalador. Al terminar, Aspiradora Xiaomi se abrirá sola.",
            )
            self.after(900, self.destroy)
            return
        if kind == "update_error":
            self._close_update_window()
            return super()._handle_ui_event(kind, payload)
        return super()._handle_ui_event(kind, payload)

    # ---------------------------------------------------------- ventana update
    def _open_update_window(self, version):
        self._close_update_window()
        win = tk.Toplevel(self)
        win.title("Actualizar Aspiradora Xiaomi")
        win.geometry("510x230")
        win.resizable(False, False)
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = tk.Frame(win, padx=24, pady=22)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=f"Actualizando a v{version}",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        self._update_stage_label = tk.Label(
            frame,
            text="Preparando descarga…",
            font=("Segoe UI", 10),
            anchor="w",
        )
        self._update_stage_label.pack(fill="x", pady=(14, 8))

        self._update_progress = ttk.Progressbar(frame, mode="determinate", maximum=100, value=0)
        self._update_progress.pack(fill="x")
        self._update_progress_mode = "determinate"

        self._update_detail_label = tk.Label(
            frame,
            text="0%",
            font=("Segoe UI", 9),
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=450,
        )
        self._update_detail_label.pack(fill="x", pady=(9, 0))

        tk.Label(
            frame,
            text="Después de descargar, el instalador mostrará su propio progreso y la app volverá a abrirse automáticamente.",
            font=("Segoe UI", 9),
            fg="#777777",
            justify="left",
            wraplength=450,
        ).pack(anchor="w", pady=(14, 0))

        self._update_window = win
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _set_update_stage(self, text, detail=None):
        if self._update_stage_label and self._update_stage_label.winfo_exists():
            self._update_stage_label.configure(text=text)
        if detail is not None and self._update_detail_label and self._update_detail_label.winfo_exists():
            self._update_detail_label.configure(text=detail)
        self._set_banner(text)

    def _set_update_progress(self, percent, done, total):
        if not self._update_progress or not self._update_progress.winfo_exists():
            return

        if percent is None:
            if self._update_progress_mode != "indeterminate":
                self._update_progress.stop()
                self._update_progress.configure(mode="indeterminate")
                self._update_progress.start(12)
                self._update_progress_mode = "indeterminate"
        else:
            if self._update_progress_mode != "determinate":
                self._update_progress.stop()
                self._update_progress.configure(mode="determinate", maximum=100)
                self._update_progress_mode = "determinate"
            self._update_progress.configure(value=max(0, min(100, int(percent))))

        done_mb = done / (1024 * 1024)
        if total > 0:
            total_mb = total / (1024 * 1024)
            text = f"{int(percent or 0)}% · {done_mb:.1f} MB de {total_mb:.1f} MB"
        else:
            text = f"Descargados {done_mb:.1f} MB…"
        if self._update_detail_label and self._update_detail_label.winfo_exists():
            self._update_detail_label.configure(text=text)

    def _close_update_window(self):
        win = self._update_window
        self._update_window = None
        self._update_progress = None
        self._update_stage_label = None
        self._update_detail_label = None
        self._update_progress_mode = None
        if win:
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass

    # --------------------------------------------------------- flujo update
    def _manual_update_found_safe(self, update):
        version = update.get("version", "nueva")
        self._set_banner(f"Actualización v{version} disponible.")
        if not messagebox.askyesno(
            "Actualización disponible",
            f"Hay una nueva versión: v{version}.\n\n"
            "¿Querés descargarla, instalarla y abrir automáticamente la versión nueva?",
            parent=self,
        ):
            self._set_manual_update_idle()
            return

        self.manual_update_button.configure(text="Actualizando…", state="disabled")
        self._open_update_window(version)
        self._set_update_stage(f"Descargando actualización v{version}…")

        def worker():
            try:
                download_and_install(
                    update,
                    status_callback=lambda text: self._post_ui("update_stage", text),
                    progress_callback=lambda percent, done, total: self._post_ui(
                        "update_progress", percent, done, total
                    ),
                )
                self._post_ui("update_install_done")
            except Exception as exc:
                self._post_ui(
                    "update_error",
                    str(exc).strip() or "No se pudo instalar la actualización.",
                )

        threading.Thread(target=worker, daemon=True).start()

    def _manual_update_error(self, message):
        self._close_update_window()
        return super()._manual_update_error(message)


if __name__ == "__main__":
    app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

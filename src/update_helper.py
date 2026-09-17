import argparse
import ctypes
import os
import queue
import subprocess
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from backup_bundle import auto_backup
from cleaning_plan import CleaningPlanStore
from local_mapping import LocalMapStore
from windows_integration import apply_window_icon, set_app_user_model_id

APPDATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
LOG_PATH = APPDATA_DIR / "update.log"
SCHEDULER_EXE_NAME = "Aspiradora Xiaomi Scheduler.exe"


def log(message: str):
    try:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def wait_for_process(pid: int, timeout_ms: int = 60000):
    if pid <= 0:
        return
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, timeout_ms)
        if result == WAIT_TIMEOUT:
            raise TimeoutError("La aplicación anterior no se cerró a tiempo.")
    finally:
        kernel32.CloseHandle(handle)


def stop_scheduler():
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["taskkill", "/IM", SCHEDULER_EXE_NAME, "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )
        log("Programador detenido para actualizar.")
    except Exception as exc:
        log(f"No pude detener el programador: {exc}")


def backup_user_data():
    try:
        maps = LocalMapStore(APPDATA_DIR)
        plan = CleaningPlanStore(APPDATA_DIR)
        target = auto_backup(
            APPDATA_DIR,
            maps.library_snapshot(),
            plan.snapshot_all(),
            prefix="antes-de-actualizar",
            keep=8,
        )
        log(f"Respaldo previo creado: {target}")
        return target
    except Exception as exc:
        log(f"No pude crear respaldo previo adicional: {exc}")
        return None


class UpdateWindow(tk.Tk):
    def __init__(self, parent_pid: int, installer: Path, app_exe: Path, version: str):
        set_app_user_model_id()
        super().__init__()
        self.parent_pid = int(parent_pid)
        self.installer = Path(installer)
        self.app_exe = Path(app_exe)
        self.version = str(version)
        self._events = queue.Queue()
        self.title("Actualizando Aspiradora Xiaomi")
        self.geometry("470x190")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        apply_window_icon(self)

        frame = tk.Frame(self, padx=24, pady=22)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=f"Actualizando a v{self.version}", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.status_label = tk.Label(frame, text="Esperando que se cierre la aplicación…", font=("Segoe UI", 10))
        self.status_label.pack(anchor="w", pady=(12, 8))

        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=410)
        self.progress.pack(fill="x")
        self.progress.start(12)

        self.detail_label = tk.Label(
            frame,
            text="No cierres esta ventana. La aplicación volverá a abrirse automáticamente.",
            font=("Segoe UI", 9),
            fg="#666666",
            wraplength=410,
            justify="left",
        )
        self.detail_label.pack(anchor="w", pady=(10, 0))

        self.after(50, self._drain_events)
        self.after(150, lambda: threading.Thread(target=self._run_update, daemon=True).start())

    def _post(self, kind, *payload):
        self._events.put((kind, payload))

    def _drain_events(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "status":
                    text = str(payload[0])
                    detail = payload[1] if len(payload) > 1 else None
                    self.status_label.configure(text=text)
                    if detail is not None:
                        self.detail_label.configure(text=str(detail))
                elif kind == "error":
                    self._show_error(str(payload[0]))
                elif kind == "complete":
                    self.status_label.configure(text="Instalación completada.")
                    self.detail_label.configure(text="Aspiradora Xiaomi se abrió con la nueva versión.")
                    self.after(700, self.destroy)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_events)

    def _run_update(self):
        try:
            log(f"Inicio helper v{self.version}. PID anterior={self.parent_pid}")
            self._post("status", "Cerrando la versión anterior…")
            wait_for_process(self.parent_pid)
            stop_scheduler()

            self._post(
                "status",
                "Guardando mapas y programaciones…",
                "Creando un respaldo automático antes de instalar la nueva versión.",
            )
            backup_user_data()

            if not self.installer.exists():
                raise FileNotFoundError(f"No se encontró el instalador: {self.installer}")

            self._post(
                "status",
                "Instalando actualización…",
                "El instalador de Windows mostrará el progreso real de la instalación.",
            )
            log(f"Ejecutando instalador: {self.installer}")
            proc = subprocess.Popen([
                str(self.installer),
                "/SILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/CLOSEAPPLICATIONS",
            ])
            code = proc.wait()
            log(f"Instalador finalizó con código {code}")
            if code != 0:
                raise RuntimeError(f"El instalador terminó con código {code}.")

            self._post("status", "Instalación completada.", "Abriendo Aspiradora Xiaomi…")
            time.sleep(0.8)
            if not self.app_exe.exists():
                fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Aspiradora Xiaomi" / "Aspiradora Xiaomi.exe"
                if fallback.exists():
                    self.app_exe = fallback
            if not self.app_exe.exists():
                raise FileNotFoundError(f"La actualización terminó, pero no encontré {self.app_exe}")

            subprocess.Popen([str(self.app_exe)], close_fds=True)
            log(f"Aplicación relanzada: {self.app_exe}")
            self._post("complete")
        except Exception as exc:
            log("ERROR: " + traceback.format_exc())
            self._post("error", str(exc).strip() or "No se pudo completar la actualización.")

    def _show_error(self, message: str):
        self.progress.stop()
        self.status_label.configure(text="No se pudo completar la actualización.")
        self.detail_label.configure(text=message)
        messagebox.showerror(
            "Actualización de Aspiradora Xiaomi",
            message + f"\n\nDetalle guardado en:\n{LOG_PATH}",
            parent=self,
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    UpdateWindow(args.parent_pid, Path(args.installer), Path(args.app), args.version).mainloop()


if __name__ == "__main__":
    main()

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

PALETTES = {
    "light": {
        "bg": "#f4f5f7", "card": "#ffffff", "text": "#17181a",
        "muted": "#7b8088", "border": "#e8eaed", "accent": "#ff6900",
    },
    "dark": {
        "bg": "#0f1115", "card": "#171a21", "text": "#f3f5f7",
        "muted": "#9aa3ad", "border": "#2a303b", "accent": "#ff6900",
    },
}
WORDS = {
    "es": {
        "title": "Actualización de Aspiradora",
        "head": "Instalando v{version}",
        "wait": "Esperando que se cierre la aplicación…",
        "backup": "Guardando mapas y programaciones…",
        "backup_detail": "Creando un respaldo automático antes de instalar.",
        "install": "Instalando actualización…",
        "install_detail": "La instalación se ejecuta en segundo plano, sin CMD ni ventanas externas.",
        "done": "Instalación completada.",
        "open": "Abriendo Aspiradora…",
        "keep": "No cierres esta ventana. Aspiradora volverá a abrirse automáticamente.",
        "error": "No se pudo completar la actualización.",
    },
    "en": {
        "title": "Aspiradora Update",
        "head": "Installing v{version}",
        "wait": "Waiting for the application to close…",
        "backup": "Saving maps and schedules…",
        "backup_detail": "Creating an automatic backup before installation.",
        "install": "Installing update…",
        "install_detail": "Installation runs in the background with no CMD or external installer windows.",
        "done": "Installation complete.",
        "open": "Opening Aspiradora…",
        "keep": "Do not close this window. Aspiradora will reopen automatically.",
        "error": "The update could not be completed.",
    },
    "pt": {
        "title": "Atualização do Aspiradora",
        "head": "Instalando v{version}",
        "wait": "Aguardando o aplicativo fechar…",
        "backup": "Salvando mapas e agendamentos…",
        "backup_detail": "Criando um backup automático antes da instalação.",
        "install": "Instalando atualização…",
        "install_detail": "A instalação roda em segundo plano, sem CMD ou janelas externas.",
        "done": "Instalação concluída.",
        "open": "Abrindo Aspiradora…",
        "keep": "Não feche esta janela. O Aspiradora abrirá novamente automaticamente.",
        "error": "Não foi possível concluir a atualização.",
    },
}


def log(message: str):
    try:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _hidden_startupinfo():
    if os.name != "nt":
        return None
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return startup


def _hidden_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


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
            stdin=subprocess.DEVNULL,
            timeout=8,
            check=False,
            creationflags=_hidden_flags(),
            startupinfo=_hidden_startupinfo(),
        )
        log("Scheduler stopped for update.")
    except Exception as exc:
        log(f"Could not stop scheduler: {exc}")


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
        log(f"Pre-update backup: {target}")
        return target
    except Exception as exc:
        log(f"Backup warning: {exc}")
        return None


class UpdateWindow(tk.Tk):
    def __init__(self, parent_pid: int, installer: Path, app_exe: Path, version: str, theme: str, language: str):
        set_app_user_model_id()
        super().__init__()
        self.parent_pid = int(parent_pid)
        self.installer = Path(installer)
        self.app_exe = Path(app_exe)
        self.version = str(version)
        self.theme = "dark" if str(theme).lower() == "dark" else "light"
        self.language = str(language).lower() if str(language).lower() in WORDS else "es"
        self.words = WORDS[self.language]
        self.palette = PALETTES[self.theme]
        self._events = queue.Queue()

        self.title(self.words["title"])
        self.geometry("520x240")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.configure(bg=self.palette["bg"])
        apply_window_icon(self)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Updater.Horizontal.TProgressbar",
            troughcolor=self.palette["border"],
            background=self.palette["accent"],
            bordercolor=self.palette["border"],
            lightcolor=self.palette["accent"],
            darkcolor=self.palette["accent"],
        )

        frame = tk.Frame(
            self, bg=self.palette["card"], padx=24, pady=22,
            highlightthickness=1, highlightbackground=self.palette["border"],
        )
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            frame, text=self.words["head"].format(version=self.version),
            bg=self.palette["card"], fg=self.palette["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.status_label = tk.Label(
            frame, text=self.words["wait"], bg=self.palette["card"],
            fg=self.palette["text"], font=("Segoe UI", 10),
        )
        self.status_label.pack(anchor="w", pady=(12, 8))

        self.progress = ttk.Progressbar(
            frame, mode="indeterminate", length=440,
            style="Updater.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")
        self.progress.start(12)

        self.detail_label = tk.Label(
            frame, text=self.words["keep"], bg=self.palette["card"],
            fg=self.palette["muted"], font=("Segoe UI", 9),
            wraplength=440, justify="left",
        )
        self.detail_label.pack(anchor="w", pady=(10, 0))

        self.after(50, self._drain_events)
        self.after(120, lambda: threading.Thread(target=self._run_update, daemon=True).start())

    def _post(self, kind, *payload):
        self._events.put((kind, payload))

    def _drain_events(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "status":
                    self.status_label.configure(text=str(payload[0]))
                    if len(payload) > 1 and payload[1] is not None:
                        self.detail_label.configure(text=str(payload[1]))
                elif kind == "error":
                    self._show_error(str(payload[0]))
                elif kind == "complete":
                    self.status_label.configure(text=self.words["done"])
                    self.detail_label.configure(text=self.words["open"])
                    self.after(650, self.destroy)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_events)

    def _run_update(self):
        try:
            log(f"GUI updater v{self.version}. Previous PID={self.parent_pid}")
            self._post("status", self.words["wait"])
            wait_for_process(self.parent_pid)
            stop_scheduler()

            self._post("status", self.words["backup"], self.words["backup_detail"])
            backup_user_data()

            if not self.installer.exists():
                raise FileNotFoundError(f"Installer not found: {self.installer}")

            self._post("status", self.words["install"], self.words["install_detail"])
            log(f"Running hidden installer: {self.installer}")
            proc = subprocess.Popen(
                [
                    str(self.installer),
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    "/CLOSEAPPLICATIONS",
                    "/NOCANCEL",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_hidden_flags(),
                startupinfo=_hidden_startupinfo(),
                close_fds=True,
            )
            code = proc.wait()
            log(f"Installer exit code={code}")
            if code != 0:
                raise RuntimeError(f"Installer exit code {code}.")

            self._post("status", self.words["done"], self.words["open"])
            time.sleep(0.65)
            if not self.app_exe.exists():
                fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Aspiradora Xiaomi" / "Aspiradora Xiaomi.exe"
                if fallback.exists():
                    self.app_exe = fallback
            if not self.app_exe.exists():
                raise FileNotFoundError(f"Application not found after update: {self.app_exe}")

            subprocess.Popen(
                [str(self.app_exe), "--after-update"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_hidden_flags(),
                startupinfo=_hidden_startupinfo(),
                close_fds=True,
            )
            log(f"Application relaunched: {self.app_exe}")
            self._post("complete")
        except Exception as exc:
            log("ERROR: " + traceback.format_exc())
            self._post("error", str(exc).strip() or self.words["error"])

    def _show_error(self, message: str):
        try:
            self.progress.stop()
        except Exception:
            pass
        self.status_label.configure(text=self.words["error"])
        self.detail_label.configure(text=message)
        messagebox.showerror(
            self.words["title"],
            message + f"\n\nLog:\n{LOG_PATH}",
            parent=self,
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--theme", default="light")
    parser.add_argument("--language", default="es")
    args = parser.parse_args()
    UpdateWindow(
        args.parent_pid,
        Path(args.installer),
        Path(args.app),
        args.version,
        args.theme,
        args.language,
    ).mainloop()


if __name__ == "__main__":
    main()

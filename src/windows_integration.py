import ctypes
import os
import sys
from pathlib import Path

APP_USER_MODEL_ID = "Yakoderaa.AspiradoraXiaomi"
RUN_VALUE_NAME = "Aspiradora Xiaomi"


def resource_path(*parts: str) -> Path:
    """Ruta compatible con ejecución fuente y PyInstaller onedir."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def mi_home_ico() -> Path:
    return resource_path("assets", "mi_home.ico")


def mi_home_png() -> Path:
    return resource_path("assets", "mi_home.png")


def set_app_user_model_id():
    """Hace que Windows agrupe la ventana con el icono del ejecutable correcto."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_window_icon(window):
    """Fija explícitamente el icono Tk para título, Alt+Tab y barra de tareas."""
    ico = mi_home_ico()
    png = mi_home_png()
    try:
        if ico.exists():
            window.iconbitmap(default=str(ico))
    except Exception:
        pass
    try:
        if png.exists():
            import tkinter as tk

            image = tk.PhotoImage(file=str(png))
            window.iconphoto(True, image)
            window._mi_home_window_icon = image
    except Exception:
        pass


def _startup_command(minimized=True) -> str:
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        parts = [str(exe)]
    else:
        app = Path(__file__).resolve().parent / "app_v20.py"
        parts = [str(exe), str(app)]
    if minimized:
        parts.append("--tray")
    return " ".join(f'"{part}"' if " " in part or "\t" in part else part for part in parts)


def set_run_at_login(enabled: bool, minimized=True):
    if os.name != "nt":
        return
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, _startup_command(minimized=minimized))
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


def run_at_login_command() -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(value)
    except Exception:
        return None

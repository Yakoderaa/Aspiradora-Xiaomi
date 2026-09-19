import ctypes
import os
import sys
import threading
import time

DISPLAY_NAME = "Aspiradora"
APP_USER_MODEL_ID = "Yakoderaa.Aspiradora"
SCAN_INTERVAL_SECONDS = 2.0

_lock = threading.Lock()
_started = False
_diag = {
    "display_name": DISPLAY_NAME,
    "app_user_model_id": APP_USER_MODEL_ID,
    "app_user_model_id_ok": False,
    "scans": 0,
    "renamed_sessions": 0,
    "last_error": None,
}


def _set_app_user_model_id():
    if sys.platform != "win32":
        return False
    try:
        shell32 = ctypes.windll.shell32
        fn = shell32.SetCurrentProcessExplicitAppUserModelID
        fn.argtypes = [ctypes.c_wchar_p]
        fn.restype = ctypes.c_long
        result = int(fn(APP_USER_MODEL_ID))
        ok = result == 0
        with _lock:
            _diag["app_user_model_id_ok"] = ok
            if not ok:
                _diag["last_error"] = f"SetCurrentProcessExplicitAppUserModelID={result}"
        return ok
    except Exception as exc:
        with _lock:
            _diag["last_error"] = str(exc).strip() or type(exc).__name__
        return False


def _session_pid(session):
    try:
        pid = getattr(session, "ProcessId", None)
        if callable(pid):
            pid = pid()
        if pid is not None:
            return int(pid)
    except Exception:
        pass
    try:
        process = getattr(session, "Process", None)
        pid = getattr(process, "pid", None)
        if pid is not None:
            return int(pid)
    except Exception:
        pass
    return None


def _set_session_display_name(session):
    try:
        session.DisplayName = DISPLAY_NAME
        return True
    except Exception:
        pass
    try:
        control = getattr(session, "_ctl", None)
        if control is None:
            return False
        control.SetDisplayName(DISPLAY_NAME, None)
        return True
    except Exception:
        return False


def _rename_own_audio_sessions_once():
    if sys.platform != "win32":
        return 0
    from pycaw.pycaw import AudioUtilities

    own_pid = os.getpid()
    renamed = 0
    for session in AudioUtilities.GetAllSessions():
        if _session_pid(session) != own_pid:
            continue
        if _set_session_display_name(session):
            renamed += 1
    with _lock:
        _diag["scans"] += 1
        if renamed:
            _diag["renamed_sessions"] = max(
                int(_diag.get("renamed_sessions", 0) or 0),
                renamed,
            )
            _diag["last_error"] = None
    return renamed


def _worker():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        comtypes = None

    try:
        while True:
            try:
                _rename_own_audio_sessions_once()
            except Exception as exc:
                with _lock:
                    _diag["scans"] += 1
                    _diag["last_error"] = str(exc).strip() or type(exc).__name__
            time.sleep(SCAN_INTERVAL_SECONDS)
    finally:
        try:
            if comtypes is not None:
                comtypes.CoUninitialize()
        except Exception:
            pass


def install():
    global _started
    _set_app_user_model_id()
    if sys.platform != "win32":
        return False
    with _lock:
        if _started:
            return True
        _started = True
    threading.Thread(
        target=_worker,
        name="AspiradoraAudioIdentity",
        daemon=True,
    ).start()
    return True


def snapshot():
    with _lock:
        return dict(_diag)

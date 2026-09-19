import atexit
import ctypes
import os
from pathlib import Path
import sys
import threading
import time
import wave

DISPLAY_NAME = "Aspiradora"
APP_USER_MODEL_ID = "Yakoderaa.Aspiradora"
SCAN_INTERVAL_SECONDS = 1.0

_lock = threading.Lock()
_started = False
_silence_path = None
_diag = {
    "display_name": DISPLAY_NAME,
    "app_user_model_id": APP_USER_MODEL_ID,
    "app_user_model_id_ok": False,
    "scans": 0,
    "own_sessions_seen": 0,
    "renamed_sessions": 0,
    "silent_session_started": False,
    "last_session_name": None,
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


def _make_silent_wav():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "aspiradora-audio-session.wav"
    if path.exists() and path.stat().st_size > 1000:
        return path
    sample_rate = 8000
    frames = b"\x00\x00" * sample_rate
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return path


def _stop_silent_session():
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.PlaySound(None, 0)
    except Exception:
        pass


def _ensure_silent_session():
    global _silence_path
    if sys.platform != "win32":
        return False
    try:
        import winsound
        _silence_path = _make_silent_wav()
        flags = (
            winsound.SND_FILENAME
            | winsound.SND_ASYNC
            | winsound.SND_LOOP
            | winsound.SND_NODEFAULT
        )
        winsound.PlaySound(str(_silence_path), flags)
        with _lock:
            _diag["silent_session_started"] = True
        return True
    except Exception as exc:
        with _lock:
            _diag["silent_session_started"] = False
            _diag["last_error"] = str(exc).strip() or type(exc).__name__
        return False


def _session_pid(session):
    for attr in ("ProcessId", "ProcessID", "process_id"):
        try:
            value = getattr(session, attr, None)
            if callable(value):
                value = value()
            if value is not None:
                return int(value)
        except Exception:
            pass

    try:
        process = getattr(session, "Process", None)
        pid = getattr(process, "pid", None)
        if callable(pid):
            pid = pid()
        if pid is not None:
            return int(pid)
    except Exception:
        pass

    for attr in ("_ctl2", "_ctl"):
        try:
            control = getattr(session, attr, None)
            if control is None:
                continue
            for method in ("GetProcessId", "GetProcessID"):
                fn = getattr(control, method, None)
                if callable(fn):
                    return int(fn())
        except Exception:
            pass
    return None


def _session_name(session):
    try:
        value = getattr(session, "DisplayName", None)
        if callable(value):
            value = value()
        return str(value or "")
    except Exception:
        return ""


def _set_session_display_name(session):
    for attr in ("_ctl2", "_ctl"):
        try:
            control = getattr(session, attr, None)
            fn = getattr(control, "SetDisplayName", None) if control is not None else None
            if callable(fn):
                fn(DISPLAY_NAME, None)
                return True
        except Exception:
            pass
    try:
        session.DisplayName = DISPLAY_NAME
        return True
    except Exception:
        return False


def _rename_own_audio_sessions_once():
    if sys.platform != "win32":
        return 0
    from pycaw.pycaw import AudioUtilities

    own_pid = os.getpid()
    seen = 0
    renamed = 0
    last_name = None
    for session in AudioUtilities.GetAllSessions():
        if _session_pid(session) != own_pid:
            continue
        seen += 1
        before = _session_name(session)
        if _set_session_display_name(session):
            renamed += 1
        after = _session_name(session)
        last_name = after or before or DISPLAY_NAME

    with _lock:
        _diag["scans"] += 1
        _diag["own_sessions_seen"] = max(
            int(_diag.get("own_sessions_seen", 0) or 0),
            seen,
        )
        if renamed:
            _diag["renamed_sessions"] = max(
                int(_diag.get("renamed_sessions", 0) or 0),
                renamed,
            )
        if last_name:
            _diag["last_session_name"] = last_name
        if seen and renamed:
            _diag["last_error"] = None
    return renamed


def _worker():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        comtypes = None

    try:
        # Damos tiempo a que WASAPI publique la sesión silenciosa.
        time.sleep(0.35)
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

    _ensure_silent_session()
    atexit.register(_stop_silent_session)
    threading.Thread(
        target=_worker,
        name="AspiradoraAudioIdentity",
        daemon=True,
    ).start()
    return True


def snapshot():
    with _lock:
        return dict(_diag)

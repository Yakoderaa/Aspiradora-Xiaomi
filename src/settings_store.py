import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from version import APP_NAME


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes):
    buf = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    return blob, buf


def protect_text(value: str) -> str:
    if os.name != "nt":
        return "plain:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
    in_blob, _in_buf = _blob_from_bytes(value.encode("utf-8"))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Aspiradora Xiaomi",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return "dpapi:" + base64.b64encode(data).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def unprotect_text(value: str) -> str:
    if not value:
        return ""
    if value.startswith("plain:"):
        return base64.b64decode(value[6:]).decode("utf-8")
    if not value.startswith("dpapi:"):
        return ""
    raw = base64.b64decode(value[6:])
    if os.name != "nt":
        return ""
    in_blob, _in_buf = _blob_from_bytes(raw)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class SettingsStore:
    PROTECTED_FIELDS = ("token", "cloud_session")

    def __init__(self):
        appdata = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        self.folder = appdata / APP_NAME
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "settings.json"

    def load(self) -> dict:
        defaults = {
            "ip": "",
            "token": "",
            "device_name": "Xiaomi Robot Vacuum E10",
            "device_did": "",
            "device_region": "",
            "cloud_session": "",
            "mop_enabled": False,
            "mop_water_level": 1,
            "auto_update": True,
            "poll_seconds": 5,
            # Integración con Windows / bandeja de sistema.
            "start_with_windows": False,
            "close_to_tray": True,
            "start_minimized_to_tray": True,
            "tray_quick_actions": [
                "clean_all",
                "dock",
                "map",
                "stop",
            ],
        }
        if not self.path.exists():
            return defaults
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            defaults.update(data)
            for field in self.PROTECTED_FIELDS:
                if defaults.get(field):
                    defaults[field] = unprotect_text(defaults[field])
            actions = defaults.get("tray_quick_actions")
            if not isinstance(actions, list):
                defaults["tray_quick_actions"] = ["clean_all", "dock", "map", "stop"]
        except Exception:
            return defaults
        return defaults

    def save(self, settings: dict):
        data = dict(settings)
        for field in self.PROTECTED_FIELDS:
            value = data.get(field, "")
            data[field] = protect_text(value) if value else ""
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

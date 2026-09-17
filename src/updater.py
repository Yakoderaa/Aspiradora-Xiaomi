import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from version import GITHUB_REPO, VERSION

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALLER_NAME = "Aspiradora-Xiaomi-Setup.exe"
CHECKSUM_NAME = INSTALLER_NAME + ".sha256"
APP_EXE_NAME = "Aspiradora Xiaomi.exe"
UPDATER_EXE_NAME = "Aspiradora Xiaomi Updater.exe"


def _version_tuple(value: str):
    value = value.strip().lstrip("vV")
    parts = []
    for item in value.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0])[:3])


def _request_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Aspiradora-Xiaomi/{VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path, progress_callback=None):
    callback = progress_callback or (lambda _percent, _done, _total: None)
    req = urllib.request.Request(url, headers={"User-Agent": f"Aspiradora-Xiaomi/{VERSION}"})
    with urllib.request.urlopen(req, timeout=90) as response, destination.open("wb") as out:
        try:
            total = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        downloaded = 0
        callback(0 if total else None, 0, total)
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            percent = min(100, int(downloaded * 100 / total)) if total else None
            callback(percent, downloaded, total)
        callback(100, downloaded, total or downloaded)


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def check_for_update():
    if "dev" in VERSION.lower():
        return None
    release = _request_json(API_URL)
    latest = release.get("tag_name", "").lstrip("vV")
    if not latest or _version_tuple(latest) <= _version_tuple(VERSION):
        return None
    assets = {
        asset.get("name"): asset.get("browser_download_url")
        for asset in release.get("assets", [])
    }
    installer_url = assets.get(INSTALLER_NAME)
    checksum_url = assets.get(CHECKSUM_NAME)
    if not installer_url or not checksum_url:
        return None
    return {
        "version": latest,
        "installer_url": installer_url,
        "checksum_url": checksum_url,
        "notes": release.get("body", ""),
        "release_url": release.get("html_url", ""),
    }


def _installed_app_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Aspiradora Xiaomi" / APP_EXE_NAME


def _bundled_helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / UPDATER_EXE_NAME
    return Path(__file__).resolve().parent.parent / "dist" / UPDATER_EXE_NAME


def _launch_update_helper(installer: Path, version: str):
    source_helper = _bundled_helper_path()
    if not source_helper.exists():
        raise RuntimeError(
            "No encontré el componente visual de actualización. "
            "Instalá esta versión manualmente una vez para reparar el actualizador."
        )

    folder = installer.parent
    helper_copy = folder / UPDATER_EXE_NAME
    shutil.copy2(source_helper, helper_copy)
    app_exe = _installed_app_path()

    creationflags = 0
    creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)

    subprocess.Popen(
        [
            str(helper_copy),
            "--parent-pid",
            str(os.getpid()),
            "--installer",
            str(installer),
            "--app",
            str(app_exe),
            "--version",
            str(version),
        ],
        creationflags=creationflags,
        close_fds=True,
    )


def download_and_install(update: dict, status_callback=None, progress_callback=None):
    status = status_callback or (lambda _text: None)
    progress = progress_callback or (lambda _percent, _done, _total: None)
    version = update["version"]
    folder = Path(tempfile.gettempdir()) / "AspiradoraXiaomiUpdates" / version
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / INSTALLER_NAME
    checksum_file = folder / CHECKSUM_NAME

    status(f"Descargando actualización v{version}…")
    _download(update["installer_url"], installer, progress)

    status("Descarga completa. Verificando integridad…")
    _download(update["checksum_url"], checksum_file)
    expected = checksum_file.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = _sha256(installer)
    if not expected or actual != expected:
        try:
            installer.unlink(missing_ok=True)
        finally:
            raise RuntimeError("La verificación SHA-256 de la actualización falló.")

    status("Verificación correcta. Preparando instalación…")
    _launch_update_helper(installer, version)
    status("Actualizador listo. Cerrando la aplicación para instalar…")
    return True
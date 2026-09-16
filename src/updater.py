import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from version import GITHUB_REPO, VERSION

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALLER_NAME = "Aspiradora-Xiaomi-Setup.exe"
CHECKSUM_NAME = INSTALLER_NAME + ".sha256"


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
        headers={"User-Agent": f"Aspiradora-Xiaomi/{VERSION}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path):
    req = urllib.request.Request(url, headers={"User-Agent": f"Aspiradora-Xiaomi/{VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as response, destination.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


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
    assets = {asset.get("name"): asset.get("browser_download_url") for asset in release.get("assets", [])}
    installer_url = assets.get(INSTALLER_NAME)
    checksum_url = assets.get(CHECKSUM_NAME)
    if not installer_url or not checksum_url:
        return None
    return {
        "version": latest,
        "installer_url": installer_url,
        "checksum_url": checksum_url,
        "notes": release.get("body", ""),
    }


def download_and_install(update: dict, status_callback=None):
    callback = status_callback or (lambda _text: None)
    version = update["version"]
    folder = Path(tempfile.gettempdir()) / "AspiradoraXiaomiUpdates" / version
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / INSTALLER_NAME
    checksum_file = folder / CHECKSUM_NAME

    callback(f"Descargando actualización {version}…")
    _download(update["installer_url"], installer)
    _download(update["checksum_url"], checksum_file)

    expected = checksum_file.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = _sha256(installer)
    if not expected or actual != expected:
        try:
            installer.unlink(missing_ok=True)
        finally:
            raise RuntimeError("La verificación SHA-256 de la actualización falló.")

    callback(f"Instalando actualización {version}…")
    flags = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(flags, creationflags=creationflags, close_fds=True)
    return True

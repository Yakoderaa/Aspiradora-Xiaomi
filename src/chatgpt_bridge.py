import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import zipfile
from ctypes import wintypes
from pathlib import Path

import requests
import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import JSONResponse


APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi" / "chatgpt"
SNAPSHOT_PATH = APP_DATA / "snapshot.json"
SECRET_PATH = APP_DATA / "openai_runtime_key.dpapi"
TUNNEL_DIR = APP_DATA / "tunnel-client"
TUNNEL_LOG = APP_DATA / "tunnel-client.log"
HEALTH_URL_FILE = APP_DATA / "tunnel-health-url.txt"

GITHUB_LATEST_RELEASE = "https://api.github.com/repos/openai/tunnel-client/releases/latest"
PLATFORM_TUNNELS_URL = "https://platform.openai.com/settings/organization/tunnels"
PLATFORM_API_KEYS_URL = "https://platform.openai.com/settings/organization/api-keys"
CHATGPT_CONNECTORS_URL = "https://chatgpt.com/#settings/Connectors"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _ensure_dir():
    APP_DATA.mkdir(parents=True, exist_ok=True)


def _protect_windows(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("El guardado seguro de la clave está disponible sólo en Windows.")
    buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Aspiradora Xiaomi ChatGPT".encode("utf-16-le"),
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _unprotect_windows(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("El guardado seguro de la clave está disponible sólo en Windows.")
    buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    flags = 0x01
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def save_runtime_key(key: str):
    key = str(key or "").strip()
    if not key:
        raise ValueError("La clave de API está vacía.")
    _ensure_dir()
    protected = _protect_windows(key.encode("utf-8"))
    SECRET_PATH.write_bytes(base64.b64encode(protected))


def load_runtime_key() -> str:
    try:
        raw = base64.b64decode(SECRET_PATH.read_bytes())
        return _unprotect_windows(raw).decode("utf-8")
    except Exception:
        return ""


def clear_runtime_key():
    try:
        SECRET_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def sanitize(value):
    sensitive = {
        "token", "password", "passwd", "api_key", "apikey",
        "authorization", "secret", "username", "email",
        "ip", "localip", "signed_url", "url",
    }
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            k = str(key)
            if k.lower() in sensitive or any(word in k.lower() for word in ("token", "password", "secret", "api_key")):
                clean[k] = "[redacted]"
            else:
                clean[k] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        text = value
        text = re.sub(r"\bsk-[A-Za-z0-9_\-]{12,}\b", "[redacted-openai-key]", text)
        text = re.sub(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", "[redacted-ip]", text)
        return text
    return value


def atomic_write_snapshot(payload: dict):
    _ensure_dir()
    payload = sanitize(payload)
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, SNAPSHOT_PATH)


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema": 1,
            "available": False,
            "message": "La aplicación todavía no publicó una instantánea.",
        }


def _pick_free_port(start=8765, end=8795):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No encontré un puerto local libre para el servidor MCP.")


class AspiradoraMCPServer:
    def __init__(self, snapshot_path=SNAPSHOT_PATH):
        self.snapshot_path = Path(snapshot_path)
        self.port = None
        self.endpoint = None
        self.server = None
        self.thread = None
        self._mcp = None

    def _snapshot(self):
        return load_snapshot()

    def _build(self):
        mcp = MCPServer(
            "Aspiradora Xiaomi",
            instructions=(
                "Integración read-only con Xiaomi Vacuum E10. "
                "Nunca mueve el robot ni modifica mapas. Usa estas herramientas "
                "para leer estado, mapeo, geometría y diagnóstico de la app."
            ),
        )

        @mcp.tool()
        def get_robot_status() -> dict:
            """Devuelve el último estado físico conocido del E10."""
            return sanitize(self._snapshot().get("robot", {}))

        @mcp.tool()
        def get_mapping_state() -> dict:
            """Devuelve fase de mapeo, transición, órdenes recientes y estado físico."""
            snap = self._snapshot()
            return sanitize({
                "updated_at": snap.get("updated_at"),
                "mapping": snap.get("mapping", {}),
                "recent_events": snap.get("recent_events", []),
            })

        @mcp.tool()
        def get_map_data() -> dict:
            """Devuelve el snapshot local del mapa, incluido native_grid Xiaomi si existe."""
            snap = self._snapshot()
            return sanitize({
                "updated_at": snap.get("updated_at"),
                "map": snap.get("map", {}),
            })

        @mcp.tool()
        def get_recent_events() -> dict:
            """Devuelve auditoría reciente de START, dock, fases y errores."""
            snap = self._snapshot()
            return sanitize({
                "updated_at": snap.get("updated_at"),
                "events": snap.get("recent_events", []),
            })

        @mcp.tool()
        def get_full_diagnostic() -> str:
            """Devuelve el diagnóstico F12 completo y saneado de la aplicación."""
            snap = self._snapshot()
            return str(snap.get("diagnostic") or "Diagnóstico todavía no disponible.")

        @mcp.tool()
        def get_full_snapshot() -> dict:
            """Devuelve toda la instantánea read-only publicada por Aspiradora Xiaomi."""
            return sanitize(self._snapshot())

        @mcp.custom_route("/health", methods=["GET"])
        async def health(_request):
            return JSONResponse({"ok": True, "read_only": True})

        self._mcp = mcp
        return mcp

    def start(self):
        if self.server is not None and self.thread is not None and self.thread.is_alive():
            return self.endpoint

        port = _pick_free_port()
        mcp = self._build()
        app = mcp.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=server.run,
            name="AspiradoraChatGPTMCP",
            daemon=True,
        )
        thread.start()

        deadline = time.monotonic() + 10.0
        health = f"http://127.0.0.1:{port}/health"
        last_error = None
        while time.monotonic() < deadline:
            try:
                response = requests.get(health, timeout=0.6)
                if response.status_code == 200:
                    self.port = port
                    self.endpoint = f"http://127.0.0.1:{port}/mcp"
                    self.server = server
                    self.thread = thread
                    return self.endpoint
            except Exception as exc:
                last_error = exc
            time.sleep(0.15)

        server.should_exit = True
        raise RuntimeError(
            "El servidor MCP local no inició correctamente."
            + (f" {last_error}" if last_error else "")
        )

    def stop(self):
        if self.server is not None:
            try:
                self.server.should_exit = True
            except Exception:
                pass
        self.server = None
        self.thread = None
        self.endpoint = None
        self.port = None


class TunnelClientManager:
    def __init__(self):
        self.process = None
        self.health_url = None
        self.client_path = None

    @staticmethod
    def _creationflags():
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    def ensure_client(self, progress=None) -> Path:
        _ensure_dir()
        TUNNEL_DIR.mkdir(parents=True, exist_ok=True)

        if progress:
            progress("Buscando la versión oficial más reciente de tunnel-client…")

        meta = requests.get(
            GITHUB_LATEST_RELEASE,
            headers={"User-Agent": "Aspiradora-Xiaomi"},
            timeout=20,
        )
        meta.raise_for_status()
        release = meta.json()
        tag = str(release.get("tag_name") or "unknown")
        assets = list(release.get("assets") or [])
        candidates = [
            a for a in assets
            if re.search(r"^tunnel-client-v.*-windows-amd64\.zip$", str(a.get("name") or ""), re.I)
        ]
        if not candidates:
            raise RuntimeError("OpenAI no publicó un tunnel-client Windows amd64 reconocible.")
        asset = candidates[0]
        expected = str(asset.get("digest") or "")
        marker = TUNNEL_DIR / "installed.json"
        exe = TUNNEL_DIR / "tunnel-client.exe"

        if exe.exists() and marker.exists():
            try:
                installed = json.loads(marker.read_text(encoding="utf-8"))
                if installed.get("tag") == tag and installed.get("digest") == expected:
                    self.client_path = exe
                    return exe
            except Exception:
                pass

        if progress:
            progress(f"Descargando tunnel-client oficial {tag}…")

        url = str(asset.get("browser_download_url") or "")
        if not url:
            raise RuntimeError("La release oficial no incluye URL de descarga.")
        archive = TUNNEL_DIR / "tunnel-client.zip"
        digest = hashlib.sha256()
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with archive.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    digest.update(chunk)

        actual = "sha256:" + digest.hexdigest()
        if expected and actual.lower() != expected.lower():
            archive.unlink(missing_ok=True)
            raise RuntimeError("La firma SHA-256 del tunnel-client oficial no coincide.")

        staging = TUNNEL_DIR / "_extract"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(staging)
        found = list(staging.rglob("tunnel-client.exe"))
        if not found:
            raise RuntimeError("El paquete oficial no contenía tunnel-client.exe.")
        shutil.copy2(found[0], exe)
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
        marker.write_text(
            json.dumps({"tag": tag, "digest": expected}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.client_path = exe
        return exe

    @staticmethod
    def build_command(exe: Path, tunnel_id: str, mcp_endpoint: str):
        return [
            str(exe),
            "run",
            f"--control-plane.tunnel-id={tunnel_id}",
            "--control-plane.api-key=env:CONTROL_PLANE_API_KEY",
            f"--mcp.server-url={mcp_endpoint}",
            "--health.listen-addr=127.0.0.1:0",
            f"--health.url-file={HEALTH_URL_FILE}",
            "--log.level=info",
            "--log.format=struct-text",
        ]

    def start(self, tunnel_id: str, api_key: str, mcp_endpoint: str, progress=None):
        tunnel_id = str(tunnel_id or "").strip()
        api_key = str(api_key or "").strip()
        if not re.fullmatch(r"tunnel_[0-9a-f]{32}", tunnel_id):
            raise ValueError("El tunnel_id no tiene el formato esperado (tunnel_ + 32 caracteres hex).")
        if not api_key:
            raise ValueError("Falta la clave de API de ejecución.")

        self.stop()
        exe = self.ensure_client(progress=progress)
        try:
            HEALTH_URL_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        env = os.environ.copy()
        env["CONTROL_PLANE_API_KEY"] = api_key
        cmd = self.build_command(exe, tunnel_id, mcp_endpoint)

        log_handle = TUNNEL_LOG.open("w", encoding="utf-8", errors="replace")
        self.process = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=self._creationflags(),
        )
        log_handle.close()

        deadline = time.monotonic() + 20.0
        last = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                if HEALTH_URL_FILE.exists():
                    url = HEALTH_URL_FILE.read_text(encoding="utf-8").strip().rstrip("/")
                    if url:
                        self.health_url = url
                        response = requests.get(url + "/readyz", timeout=1.0)
                        if response.status_code == 200:
                            return {
                                "ready": True,
                                "health_url": url,
                                "pid": self.process.pid,
                            }
                        last = f"readyz HTTP {response.status_code}"
            except Exception as exc:
                last = str(exc)
            time.sleep(0.35)

        detail = last or "tunnel-client no llegó a estado Ready"
        try:
            if TUNNEL_LOG.exists():
                tail = TUNNEL_LOG.read_text(encoding="utf-8", errors="replace")[-2500:]
                tail = sanitize(tail)
                if tail:
                    detail += "\n" + str(tail)
        except Exception:
            pass
        self.stop()
        raise RuntimeError(detail)

    def stop(self):
        process = self.process
        self.process = None
        self.health_url = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=4)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def connected(self):
        return bool(self.process is not None and self.process.poll() is None)

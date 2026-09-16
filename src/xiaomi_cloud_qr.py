import random
import string
import time
from dataclasses import dataclass
from typing import Any

import requests
from micloud import MiCloud

MODEL = "xiaomi.vacuum.b112"
SERVERS = ["cn", "de", "us", "ru", "tw", "sg", "in", "i2"]


def _strip_xiaomi_json(text: str) -> dict[str, Any]:
    prefix = "&&&START&&&"
    if text.startswith(prefix):
        text = text[len(prefix):]
    import json
    return json.loads(text)


def _cookie_value(session: requests.Session, name: str) -> str | None:
    for cookie in session.cookies:
        if cookie.name == name and cookie.value:
            return cookie.value
    return None


def _user_agent() -> str:
    left = "".join(random.choice(string.ascii_lowercase) for _ in range(18))
    right = "".join(random.choice("ABCDE") for _ in range(13))
    return f"{left}-{right} APP/com.xiaomi.mihome APPV/10.5.201"


@dataclass
class QrLoginInfo:
    image: bytes
    login_url: str
    expires_seconds: int


class XiaomiQrLogin:
    """Xiaomi Cloud login using the official account QR/long-polling flow."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _user_agent()})
        self.user_id: str | None = None
        self.ssecurity: str | None = None
        self.cuser_id: str | None = None
        self.pass_token: str | None = None
        self.service_token: str | None = None
        self.location: str | None = None
        self._long_poll_url: str | None = None
        self._timeout = 120

    def begin(self) -> QrLoginInfo:
        params = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "es_AR",
            "_dc": str(int(time.time() * 1000)),
        }
        response = self.session.get(
            "https://account.xiaomi.com/longPolling/loginUrl",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = _strip_xiaomi_json(response.text)
        qr_url = data.get("qr")
        login_url = data.get("loginUrl")
        self._long_poll_url = data.get("lp")
        self._timeout = int(data.get("timeout") or 120)
        if not qr_url or not login_url or not self._long_poll_url:
            raise RuntimeError("Xiaomi no devolvió los datos necesarios para iniciar sesión por QR.")

        qr_response = self.session.get(qr_url, timeout=15)
        qr_response.raise_for_status()
        return QrLoginInfo(
            image=qr_response.content,
            login_url=login_url,
            expires_seconds=self._timeout,
        )

    def wait_for_login(self) -> None:
        if not self._long_poll_url:
            raise RuntimeError("Primero hay que generar el código QR.")

        started = time.time()
        last_response = None
        while time.time() - started <= self._timeout + 10:
            try:
                last_response = self.session.get(self._long_poll_url, timeout=10)
            except requests.Timeout:
                continue
            except requests.RequestException as exc:
                raise RuntimeError(f"Se perdió la conexión con Xiaomi: {exc}") from exc

            if last_response.status_code == 200:
                data = _strip_xiaomi_json(last_response.text)
                self.user_id = str(data.get("userId") or "") or None
                self.ssecurity = data.get("ssecurity")
                self.cuser_id = data.get("cUserId")
                self.pass_token = data.get("passToken")
                self.location = data.get("location")
                break

            # 202/204 and similar statuses mean Xiaomi is still waiting for the QR approval.
            time.sleep(0.35)
        else:
            raise RuntimeError("El código QR venció. Generá uno nuevo e intentá otra vez.")

        if not self.user_id or not self.ssecurity or not self.location:
            raise RuntimeError("Xiaomi confirmó el QR pero no devolvió una sesión válida.")

        token_response = self.session.get(
            self.location,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        token_response.raise_for_status()
        self.service_token = _cookie_value(self.session, "serviceToken")
        if not self.service_token:
            self.service_token = _cookie_value(token_response, "serviceToken") if hasattr(token_response, "cookies") else None
        if not self.service_token:
            raise RuntimeError("Xiaomi inició sesión pero no entregó el token de servicio.")

    def make_cloud(self) -> MiCloud:
        if not self.user_id or not self.service_token or not self.ssecurity:
            raise RuntimeError("La sesión de Xiaomi todavía no está lista.")
        cloud = MiCloud()
        cloud.user_id = self.user_id
        cloud.service_token = self.service_token
        cloud.ssecurity = self.ssecurity
        cloud.cuser_id = self.cuser_id
        cloud.pass_token = self.pass_token
        return cloud


def discover_e10_from_qr(login: XiaomiQrLogin, locale: str = "all") -> list[dict[str, Any]]:
    cloud = login.make_cloud()
    servers = SERVERS if locale == "all" else [locale]
    found: dict[str, dict[str, Any]] = {}
    errors = []

    for server in servers:
        try:
            devices = cloud.get_devices(country=server) or []
        except Exception as exc:
            errors.append(f"{server}: {exc}")
            continue

        for dev in devices:
            if dev.get("model") != MODEL or dev.get("parent_id"):
                continue
            did = str(dev.get("did") or f"{server}:{dev.get('localip', '')}")
            token = str(dev.get("token") or "").strip()
            ip = str(dev.get("localip") or "").strip()
            if len(token) != 32 or not ip:
                continue
            found[did] = {
                "name": dev.get("name") or "Xiaomi Robot Vacuum E10",
                "ip": ip,
                "token": token,
                "locale": server,
                "online": bool(dev.get("isOnline", True)),
                "did": did,
            }

    if not found and errors and len(errors) == len(servers):
        raise RuntimeError("No pude consultar los servidores de Xiaomi después del inicio de sesión.")
    return list(found.values())

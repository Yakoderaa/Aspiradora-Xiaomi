import time
from typing import Any

import requests
from micloud import MiCloud

from xiaomi_cloud_qr import XiaomiQrLogin as _BaseQrLogin
from xiaomi_cloud_qr import _cookie_value, _strip_xiaomi_json

MODEL = "xiaomi.vacuum.b112"
# Para cuentas de América conviene probar US primero. Si no está ahí, se recorren las demás.
SERVERS = ["us", "de", "sg", "cn", "ru", "tw", "in", "i2"]


class XiaomiQrLogin(_BaseQrLogin):
    """Versión corregida del login QR."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account_display = None
        self.account_email = None
        self.account_phone = None

    def wait_for_login(self) -> None:
        if not self._long_poll_url:
            raise RuntimeError("Primero hay que generar el código QR.")

        headers = {
            "User-Agent": self.session.headers.get("User-Agent", ""),
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "keep-alive",
        }

        try:
            response = self.session.get(
                self._long_poll_url,
                headers=headers,
                timeout=max(30, int(self._timeout) + 20),
            )
        except requests.Timeout as exc:
            raise RuntimeError("El código QR venció o Xiaomi no confirmó el acceso. Generá uno nuevo e intentá otra vez.") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Se perdió la conexión con Xiaomi mientras esperaba la confirmación: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Xiaomi no confirmó el QR (HTTP {response.status_code}).")

        try:
            data = _strip_xiaomi_json(response.text.lstrip("\ufeff \t\r\n"))
        except Exception as exc:
            raise RuntimeError("Xiaomi confirmó el QR pero devolvió una respuesta que no pude interpretar.") from exc

        code = data.get("code", 0)
        if code not in (0, "0", None):
            description = data.get("desc") or data.get("description") or f"código {code}"
            raise RuntimeError(f"Xiaomi rechazó la confirmación del QR: {description}")

        self.user_id = str(data.get("userId") or "") or None
        self.ssecurity = data.get("ssecurity")
        self.cuser_id = data.get("cUserId")
        self.pass_token = data.get("passToken")
        self.location = data.get("location")

        # Xiaomi no siempre devuelve correo/nickname en este endpoint. Guardamos
        # el mejor identificador disponible para mostrarlo en Configuración.
        self.account_email = str(data.get("email") or "").strip() or None
        self.account_phone = str(data.get("phone") or data.get("phoneNumber") or "").strip() or None
        display = (
            data.get("userName")
            or data.get("username")
            or data.get("nickName")
            or data.get("nickname")
            or self.account_email
            or self.account_phone
            or self.user_id
        )
        self.account_display = str(display).strip() if display is not None else None

        if not self.user_id or not self.ssecurity or not self.location:
            raise RuntimeError("Xiaomi aceptó el QR pero no devolvió una sesión completa.")

        try:
            token_response = self.session.get(
                self.location,
                headers={
                    "User-Agent": headers["User-Agent"],
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=25,
                allow_redirects=True,
            )
            token_response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Xiaomi aceptó el QR pero no pude terminar de crear la sesión: {exc}") from exc

        self.service_token = token_response.cookies.get("serviceToken") or _cookie_value(self.session, "serviceToken")
        if not self.cuser_id:
            self.cuser_id = token_response.cookies.get("cUserId") or _cookie_value(self.session, "cUserId")

        if not self.service_token:
            raise RuntimeError("Xiaomi inició sesión correctamente pero no entregó el token de servicio.")


def _make_cloud(login: XiaomiQrLogin) -> MiCloud:
    if not login.user_id or not login.service_token or not login.ssecurity:
        raise RuntimeError("La sesión de Xiaomi todavía no está lista.")
    cloud = MiCloud()
    cloud.user_id = login.user_id
    cloud.service_token = login.service_token
    cloud.ssecurity = login.ssecurity
    cloud.cuser_id = login.cuser_id
    cloud.pass_token = login.pass_token
    cloud.session = None
    return cloud


def discover_e10_from_qr(login: XiaomiQrLogin, locale: str = "all") -> list[dict[str, Any]]:
    """Busca el E10 una vez que el QR ya fue confirmado."""
    cloud = _make_cloud(login)
    servers = SERVERS if locale == "all" else [locale]
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

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

        if found:
            break

    if not found and errors and len(errors) == len(servers):
        raise RuntimeError("El inicio de sesión funcionó, pero no pude consultar los servidores de Xiaomi.")

    return list(found.values())

import json
from typing import Any

from micloud import MiCloud


class XiaomiCloudTelemetry:
    """Lectura de propiedades MIoT a través de Xiaomi Cloud.

    No modifica el robot. Se usa como fallback cuando la lectura LAN del E10
    queda congelada durante el mapeo.
    """

    PROPERTIES = [
        ("cur_map_id", 10, 2),
        ("cur_cleaning_path", 10, 5),
        ("charging_base", 10, 22),
        ("robot_location", 10, 24),
    ]

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings or {}
        self.did = str(self.settings.get("device_did") or "").strip()
        self.region = str(self.settings.get("device_region") or "").strip() or "us"
        raw_session = self.settings.get("cloud_session") or ""
        if not raw_session:
            raise RuntimeError("No hay una sesión Xiaomi Cloud guardada.")
        if not self.did:
            raise RuntimeError("Falta el ID del robot para consultar Xiaomi Cloud.")
        try:
            self.session_data = json.loads(raw_session)
        except Exception as exc:
            raise RuntimeError("La sesión Xiaomi Cloud guardada no se pudo interpretar.") from exc

    def _cloud(self) -> MiCloud:
        data = self.session_data
        required = ("user_id", "service_token", "ssecurity")
        if not all(data.get(key) for key in required):
            raise RuntimeError("La sesión Xiaomi Cloud está incompleta.")
        cloud = MiCloud()
        cloud.user_id = data["user_id"]
        cloud.service_token = data["service_token"]
        cloud.ssecurity = data["ssecurity"]
        cloud.cuser_id = data.get("cuser_id")
        cloud.pass_token = data.get("pass_token")
        cloud.session = None
        return cloud

    @staticmethod
    def decode_response(response: Any) -> dict[str, Any]:
        # micloud.request_country() devuelve el payload RC4 ya descifrado, pero
        # dependiendo de la versión de pycryptodome/micloud puede llegar como bytes.
        # Aceptamos ambas variantes antes de intentar json.loads().
        if isinstance(response, (bytes, bytearray, memoryview)):
            try:
                response = bytes(response).decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                preview = bytes(response)[:80].hex()
                raise RuntimeError(
                    f"Xiaomi Cloud devolvió bytes no UTF-8 (primeros bytes: {preview})."
                ) from exc

        if isinstance(response, str):
            text = response.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            try:
                response = json.loads(text)
            except Exception as exc:
                preview = text[:220].replace("\r", " ").replace("\n", " ")
                raise RuntimeError(f"Xiaomi Cloud devolvió una respuesta no JSON: {preview!r}") from exc

        if not isinstance(response, dict):
            raise RuntimeError(f"Respuesta MIoT Cloud inesperada: {type(response).__name__}")
        code = response.get("code", 0)
        if code not in (0, "0", None):
            message = response.get("message") or response.get("description") or response.get("msg") or "sin detalle"
            raise RuntimeError(f"MIoT Cloud rechazó la consulta: código {code} · {message}")
        result = response.get("result")
        if not isinstance(result, list):
            raise RuntimeError(
                f"MIoT Cloud no devolvió una lista de propiedades. result={type(result).__name__}: {result!r}"
            )

        values: dict[str, Any] = {}
        meta: dict[str, dict[str, Any]] = {}
        by_key = {(siid, piid): name for name, siid, piid in XiaomiCloudTelemetry.PROPERTIES}
        for item in result:
            if not isinstance(item, dict):
                continue
            name = by_key.get((item.get("siid"), item.get("piid")))
            if not name:
                continue
            item_code = item.get("code", 0)
            meta[name] = {
                "code": item_code,
                "updateTime": item.get("updateTime"),
                "exe_time": item.get("exe_time"),
            }
            if item_code in (0, "0", None):
                values[name] = item.get("value")
        return {
            "values": values,
            "meta": meta,
            "response_code": response.get("code", 0),
            "message": response.get("message") or "",
        }

    def read_map_properties(self) -> dict[str, Any]:
        cloud = self._cloud()
        params = [
            {"did": self.did, "siid": siid, "piid": piid}
            for _, siid, piid in self.PROPERTIES
        ]
        payload = {"params": params, "datasource": 2}
        response = cloud.request_country(
            "/miotspec/prop/get",
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        decoded = self.decode_response(response)
        decoded["region"] = self.region
        decoded["did"] = self.did
        return decoded

import base64
import json
from dataclasses import dataclass
from typing import Any

import requests
from micloud import MiCloud
from PIL.Image import Image as PILImage
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_xiaomi.map_data_parser import XiaomiMapDataParser

from xiaomi_e10 import MODEL, XiaomiE10


@dataclass
class MapSnapshot:
    image: PILImage
    map_data: Any
    transformer: Any
    map_name: str


class XiaomiE10MapClient:
    """Descarga y decodifica el mapa que Mi Home guarda en Xiaomi Cloud.

    El control de movimiento sigue siendo local. Xiaomi Cloud se usa solamente para
    obtener el archivo de mapa porque el E10 no entrega la imagen completa por LAN.
    """

    def __init__(self, vacuum: XiaomiE10, settings: dict):
        self.vacuum = vacuum
        self.settings = settings
        self.did = str(settings.get("device_did") or "").strip()
        self.region = str(settings.get("device_region") or "").strip() or "us"
        raw_session = settings.get("cloud_session") or ""
        if not raw_session:
            raise RuntimeError(
                "Para ver el mapa necesitás vincular la cuenta Xiaomi una vez con QR desde Configurar."
            )
        try:
            self.session_data = json.loads(raw_session)
        except Exception as exc:
            raise RuntimeError("La sesión guardada de Xiaomi no se pudo leer. Volvé a vincular con QR.") from exc
        if not self.did:
            raise RuntimeError("Falta el ID del robot. Volvé a vincular el E10 con QR.")

    def _cloud(self) -> MiCloud:
        data = self.session_data
        required = ("user_id", "service_token", "ssecurity")
        if not all(data.get(key) for key in required):
            raise RuntimeError("La sesión Xiaomi guardada está incompleta. Volvé a vincular con QR.")
        cloud = MiCloud()
        cloud.user_id = data["user_id"]
        cloud.service_token = data["service_token"]
        cloud.ssecurity = data["ssecurity"]
        cloud.cuser_id = data.get("cuser_id")
        cloud.pass_token = data.get("pass_token")
        cloud.session = None
        return cloud

    @staticmethod
    def _extract_url(response) -> str | None:
        """Extrae la URL temporal de Xiaomi Cloud.

        micloud devuelve el cuerpo RC4 ya descifrado como ``bytes`` en algunas
        versiones. La implementación anterior sólo aceptaba str/dict y por eso
        descartaba una respuesta válida como si Xiaomi no hubiese dado una URL.
        """
        if response is None:
            return None
        if isinstance(response, (bytes, bytearray, memoryview)):
            try:
                response = bytes(response).decode("utf-8-sig")
            except UnicodeDecodeError:
                return None
        if isinstance(response, str):
            try:
                response = json.loads(response.lstrip("\ufeff"))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        if not isinstance(response, dict):
            return None

        result = response.get("result")
        if isinstance(result, dict):
            for key in ("url", "file_url", "download_url"):
                value = result.get(key)
                if value:
                    return str(value)
        return None

    def _map_download_url(self, map_name: str) -> str:
        cloud = self._cloud()
        user_id = str(self.session_data["user_id"])
        # En algunos firmwares 10/2 ya devuelve una ruta completa. En ese caso
        # usamos únicamente el nombre final, igual que Mi Home.
        map_name = str(map_name).rstrip("/").split("/")[-1]
        obj_name = f"{user_id}/{self.did}/{map_name}"
        params = {"data": json.dumps({"obj_name": obj_name}, separators=(",", ":"))}

        errors = []
        responses = []
        for endpoint in ("/v2/home/get_interim_file_url_pro", "/v2/home/get_interim_file_url"):
            try:
                response = cloud.request_country(endpoint, self.region, dict(params))
                responses.append(type(response).__name__)
                url = self._extract_url(response)
                if url:
                    return url
            except Exception as exc:
                errors.append(str(exc))

        detail_parts = []
        if responses:
            detail_parts.append("respuesta=" + "/".join(responses))
        if errors:
            detail_parts.append(errors[-1])
        detail = " (" + " · ".join(detail_parts) + ")" if detail_parts else ""
        raise RuntimeError("Xiaomi Cloud respondió, pero no pude extraer la URL temporal del mapa." + detail)

    @staticmethod
    def _normalize_raw_map(raw_map: bytes) -> bytes:
        # Algunos servidores devuelven el binario directamente y otros lo envuelven
        # en un JSON con un campo data en base64.
        try:
            parsed = json.loads(raw_map)
            if isinstance(parsed, dict) and parsed.get("data"):
                return base64.decodebytes(str(parsed["data"]).encode("latin1"))
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            pass
        return raw_map

    def load(self) -> MapSnapshot:
        map_name = self.vacuum.current_map_name()
        url = self._map_download_url(map_name)
        response = requests.get(url, timeout=35)
        response.raise_for_status()
        raw_map = self._normalize_raw_map(response.content)

        parser = XiaomiMapDataParser(
            ColorsPalette(),
            Sizes(),
            [],
            ImageConfig(),
            [],
        )
        try:
            unpacked = parser.unpack_map(
                raw_map.hex(),
                model=MODEL.replace("xiaomi", "mi"),
                device_id=self.did,
            )
            map_data = parser.parse(unpacked)
        except Exception as exc:
            raise RuntimeError(f"Pude descargar el mapa pero no decodificarlo: {exc}") from exc

        if not map_data.image or map_data.image.is_empty or map_data.image.data is None:
            raise RuntimeError("El mapa descargado está vacío.")

        image = map_data.image.data.convert("RGBA")
        return MapSnapshot(
            image=image,
            map_data=map_data,
            transformer=parser.coord_transformer,
            map_name=map_name,
        )

import base64
import hashlib
import json
import zlib
from dataclasses import dataclass
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from micloud import MiCloud
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_xiaomi.map_data_parser import XiaomiMapDataParser

from xiaomi_e10 import MODEL, XiaomiE10


_XIAOMI_MAP_IV = b"ABCDEF1234123412"


@dataclass
class MapSnapshot:
    image: Any
    map_data: Any
    transformer: Any
    map_name: str
    crypto_mode: str = "unknown"
    raw_size: int = 0
    envelope_version: Any = None


class XiaomiE10MapClient:
    """Descarga y decodifica el mapa que Xiaomi Home guarda en Xiaomi Cloud.

    El E10 usa el formato de mapa JSON v2 de Xiaomi. Ese formato no usa el nombre
    de modelo completo como clave AES: Xiaomi Home toma solamente los últimos
    16 caracteres del model string, deriva una segunda clave con MD5 y recién
    entonces descifra/descomprime el JSON del mapa.
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
        """Extrae la URL temporal incluso si micloud devuelve bytes."""
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
    def _envelope_version(raw_map: bytes):
        try:
            parsed = json.loads(raw_map)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed.get("version")
        return None

    @staticmethod
    def decrypt_xiaomi_v2(raw_map: bytes, model: str, device_id: str) -> str:
        """Replica el descifrado usado por Xiaomi Home para mapas JSON v2.

        Xiaomi Home usa ``model.slice(-16)`` como clave AES-128 inicial. La
        librería genérica que usábamos recibía ``mi.vacuum.b112`` (14 bytes),
        de ahí el error exacto ``Incorrect AES key length (14 bytes)``.
        """
        envelope = json.loads(raw_map)
        if not isinstance(envelope, dict) or int(envelope.get("version", -1)) != 2:
            raise ValueError(f"El archivo no es un mapa Xiaomi v2: version={getattr(envelope, 'get', lambda *_: None)('version')!r}")
        data = envelope.get("data")
        if not data:
            raise ValueError("El mapa Xiaomi v2 no contiene el campo data.")

        model_text = str(model)
        model_key = model_text[-16:].encode("latin1")
        if len(model_key) != 16:
            raise ValueError(
                f"No se pudo derivar la clave AES-128 del modelo {model_text!r}: {len(model_key)} bytes."
            )
        did_bytes = str(device_id).encode("latin1")
        ciphertext = base64.b64decode(data)

        original_work = model_key + did_bytes
        first_key_material = AES.new(model_key, AES.MODE_CBC, _XIAOMI_MAP_IV).encrypt(
            pad(original_work, AES.block_size)
        )
        decrypt_key = hashlib.md5(first_key_material).digest()
        compressed = unpad(
            AES.new(decrypt_key, AES.MODE_CBC, _XIAOMI_MAP_IV).decrypt(ciphertext),
            AES.block_size,
        )
        return zlib.decompress(compressed).decode("utf-8")

    @staticmethod
    def _normalize_raw_map(raw_map: bytes) -> bytes:
        """Compatibilidad con mapas antiguos envueltos sólo en un campo data."""
        try:
            parsed = json.loads(raw_map)
            if isinstance(parsed, dict) and parsed.get("data"):
                return base64.decodebytes(str(parsed["data"]).encode("latin1"))
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            pass
        return raw_map

    @staticmethod
    def _parser() -> XiaomiMapDataParser:
        return XiaomiMapDataParser(
            ColorsPalette(),
            Sizes(),
            [],
            ImageConfig(),
            [],
        )

    def load(self) -> MapSnapshot:
        map_name = self.vacuum.current_map_name()
        url = self._map_download_url(map_name)
        response = requests.get(url, timeout=35)
        response.raise_for_status()
        downloaded = bytes(response.content)
        raw_size = len(downloaded)
        envelope_version = self._envelope_version(downloaded)

        parser = self._parser()
        crypto_mode = "legacy-parser"
        try:
            if envelope_version in (2, "2"):
                # No pasamos por vacuum-map-parser-xiaomi.unpack_map: su versión
                # actual usa el model string como clave AES sin recortarlo.
                unpacked = self.decrypt_xiaomi_v2(downloaded, MODEL, self.did)
                crypto_mode = "xiaomi-home-v2-suffix16"
            else:
                raw_map = self._normalize_raw_map(downloaded)
                # Fallback conservador para mapas anteriores: incluso aquí la
                # clave debe tener una longitud AES válida.
                model_key = MODEL[-16:]
                unpacked = parser.unpack_map(
                    raw_map.hex(),
                    model=model_key,
                    device_id=self.did,
                )
                crypto_mode = "legacy-parser-suffix16"
            map_data = parser.parse(unpacked)
        except Exception as exc:
            raise RuntimeError(
                "Pude descargar el mapa pero no decodificarlo "
                f"(formato={envelope_version!r}, modelo-key={MODEL[-16:]!r}/16): {exc}"
            ) from exc

        # Para seguir la posición no exigimos que el renderer haya podido crear
        # una imagen. vacuum_position y charger son suficientes para el mapa local.
        image = None
        try:
            if map_data.image and not map_data.image.is_empty and map_data.image.data is not None:
                image = map_data.image.data.convert("RGBA")
        except Exception:
            image = None

        return MapSnapshot(
            image=image,
            map_data=map_data,
            transformer=parser.coord_transformer,
            map_name=map_name,
            crypto_mode=crypto_mode,
            raw_size=raw_size,
            envelope_version=envelope_version,
        )

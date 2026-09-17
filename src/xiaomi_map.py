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
_IJAI_WIFI_SN_LENGTHS = (18, 20)
_IJAI_MODELS = {
    "xiaomi.vacuum.b106bk",
    "xiaomi.vacuum.b106tr",
    "xiaomi.vacuum.b112",
    "xiaomi.vacuum.b112bk",
    "xiaomi.vacuum.b112gl",
    "xiaomi.vacuum.b112tr",
    "xiaomi.vacuum.c101",
    "xiaomi.vacuum.c101eu",
    "xiaomi.vacuum.c102",
    "xiaomi.vacuum.c104",
    "xiaomi.vacuum.e101gl",
}


@dataclass
class MapSnapshot:
    image: Any
    map_data: Any
    transformer: Any
    map_name: str
    crypto_mode: str = "unknown"
    raw_size: int = 0
    envelope_version: Any = None
    map_id: Any = None
    resolution: Any = None
    raw_robot: tuple[float, float] | None = None
    raw_base: tuple[float, float] | None = None
    raw_path: list[tuple[float, float]] | None = None
    parser_error: str | None = None
    decoder_family: str = "unknown"
    wifi_sn_found: bool = False
    wifi_sn_length: int = 0
    mac_found: bool = False
    raw_prefix_hex: str = ""


class XiaomiE10MapClient:
    """Descarga y decodifica el mapa que Xiaomi Home guarda en Xiaomi Cloud.

    El E10 xiaomi.vacuum.b112 pertenece a la familia de mapas IJAI: el blob
    descargado es base64 + AES-ECB + zlib y la clave se deriva de Wi-Fi SN,
    owner/user id, DID, modelo y MAC. Algunas familias Xiaomi nuevas usan en
    cambio un JSON v2 con AES-CBC; conservamos ese decoder como fallback.
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
        # b112/IJAI suele usar _pro; mantenemos el endpoint simple de fallback.
        endpoints = ("/v2/home/get_interim_file_url_pro", "/v2/home/get_interim_file_url")
        for endpoint in endpoints:
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
        envelope = json.loads(raw_map)
        version = envelope.get("version") if isinstance(envelope, dict) else None
        if not isinstance(envelope, dict) or int(version if version is not None else -1) != 2:
            raise ValueError(f"El archivo no es un mapa Xiaomi v2: version={version!r}")
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
    def _xiaomi_parser() -> XiaomiMapDataParser:
        return XiaomiMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])

    @staticmethod
    def _ijai_parser():
        from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser
        return IjaiMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])

    @staticmethod
    def _point_xy(value) -> tuple[float, float] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            try:
                return float(value["x"]), float(value["y"])
            except (KeyError, TypeError, ValueError):
                return None
        try:
            return float(value.x), float(value.y)
        except Exception:
            return None

    @classmethod
    def _flatten_path_points(cls, value) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        seen: set[tuple[int, int]] = set()

        def add(item):
            point = cls._point_xy(item)
            if point is not None:
                key = (round(point[0] * 1000), round(point[1] * 1000))
                if key not in seen:
                    seen.add(key)
                    result.append(point)
                return
            if isinstance(item, dict):
                for key in ("points", "path", "paths"):
                    if key in item:
                        add(item[key])
                return
            if isinstance(item, (list, tuple)):
                for child in item:
                    add(child)
                return
            for attr in ("points", "path", "paths"):
                try:
                    child = getattr(item, attr)
                except Exception:
                    continue
                if child is not None:
                    add(child)

        add(value)
        return result

    @staticmethod
    def _valid_wifi_sn(value) -> str | None:
        text = str(value or "").strip().replace('"', "")
        if len(text) in _IJAI_WIFI_SN_LENGTHS and text.isalnum() and text.isupper():
            return text
        return None

    def _get_wifi_sn(self) -> str | None:
        # Igual que el extractor IJAI probado: 1/3 y 1/5; fallback 7/45.
        for piid in (3, 5):
            try:
                data = self.vacuum.device.get_property_by(1, piid)
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    value = self._valid_wifi_sn(data[0].get("value"))
                    if value:
                        return value
            except Exception:
                pass
        try:
            data = self.vacuum.device.get_property_by(7, 45)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                raw = str(data[0].get("value") or "")
                owner = str(self.session_data.get("user_id") or "")
                for item in raw.split(","):
                    cleaned = item.replace('"', "").strip()
                    if owner and owner in cleaned:
                        cleaned = cleaned.split(";", 1)[0]
                    value = self._valid_wifi_sn(cleaned)
                    if value:
                        return value
        except Exception:
            pass
        return None

    def _get_device_mac(self) -> str | None:
        try:
            info = self.vacuum.info()
            for attr in ("mac", "mac_address"):
                value = str(getattr(info, attr, "") or "").strip()
                if value:
                    return value
            raw = getattr(info, "data", None) or getattr(info, "raw", None)
            if isinstance(raw, dict):
                for key in ("mac", "mac_address"):
                    value = str(raw.get(key) or "").strip()
                    if value:
                        return value
        except Exception:
            pass
        # Algunos get_devices ya traen MAC; dejamos soporte si se persiste en una versión futura.
        value = str(self.settings.get("device_mac") or "").strip()
        return value or None

    @classmethod
    def _payload_telemetry(cls, payload: Any):
        if not isinstance(payload, dict):
            return None, None, []
        robot = cls._point_xy(payload.get("position"))
        base = None
        if payload.get("have_pile"):
            try:
                base = (float(payload.get("pile_x", 0)), float(payload.get("pile_y", 0)))
            except (TypeError, ValueError):
                base = None
        source = payload.get("paths")
        path = cls._flatten_path_points(source)
        return robot, base, path

    def _decode_ijai(self, downloaded: bytes):
        wifi_sn = self._get_wifi_sn()
        mac = self._get_device_mac()
        owner_id = str(self.session_data.get("user_id") or "").strip()
        missing = []
        if not wifi_sn:
            missing.append("Wi-Fi SN")
        if not mac:
            missing.append("MAC")
        if not owner_id:
            missing.append("owner id")
        if missing:
            raise RuntimeError("Faltan datos para descifrar IJAI: " + ", ".join(missing))

        parser = self._ijai_parser()
        unpacked = parser.unpack_map(
            downloaded,
            wifi_sn=wifi_sn,
            owner_id=owner_id,
            device_id=self.did,
            model=MODEL,
            device_mac=mac,
        )
        map_data = parser.parse(unpacked)
        robot = self._point_xy(getattr(map_data, "vacuum_position", None))
        base = self._point_xy(getattr(map_data, "charger", None))
        path = self._flatten_path_points(getattr(map_data, "path", None))
        image = None
        try:
            if map_data.image and not map_data.image.is_empty and map_data.image.data is not None:
                image = map_data.image.data.convert("RGBA")
        except Exception:
            image = None
        return parser, map_data, image, robot, base, path, wifi_sn, mac

    def load(self) -> MapSnapshot:
        map_name = self.vacuum.current_map_name()
        url = self._map_download_url(map_name)
        response = requests.get(url, timeout=35)
        response.raise_for_status()
        downloaded = bytes(response.content)
        raw_size = len(downloaded)
        envelope_version = self._envelope_version(downloaded)
        raw_prefix_hex = downloaded[:24].hex()

        decoder_family = "unknown"
        crypto_mode = "unknown"
        parser_error = None
        map_data = None
        image = None
        transformer = None
        raw_robot = None
        raw_base = None
        raw_path: list[tuple[float, float]] = []
        map_id = None
        resolution = None
        wifi_sn = None
        mac = None

        errors = []

        # b112 es IJAI. Para blobs sin envelope JSON intentamos primero IJAI.
        if MODEL in _IJAI_MODELS and envelope_version is None:
            try:
                parser, map_data, image, raw_robot, raw_base, raw_path, wifi_sn, mac = self._decode_ijai(downloaded)
                transformer = getattr(parser, "coord_transformer", None)
                decoder_family = "ijai"
                crypto_mode = "ijai-aes-ecb-zlib"
            except Exception as exc:
                errors.append("IJAI: " + (str(exc).strip() or type(exc).__name__))

        # Xiaomi JSON v2 (otras familias o fallback si Xiaomi cambia el blob).
        if map_data is None and envelope_version in (2, "2"):
            try:
                unpacked = self.decrypt_xiaomi_v2(downloaded, MODEL, self.did)
                decoder_family = "xiaomi-json-v2"
                crypto_mode = "xiaomi-home-v2-suffix16"
                payload = json.loads(unpacked)
                raw_robot, raw_base, raw_path = self._payload_telemetry(payload)
                map_id = payload.get("map_id") if isinstance(payload, dict) else None
                resolution = payload.get("resolution") if isinstance(payload, dict) else None
                parser = self._xiaomi_parser()
                transformer = getattr(parser, "coord_transformer", None)
                try:
                    map_data = parser.parse(unpacked)
                except Exception as exc:
                    parser_error = str(exc).strip() or type(exc).__name__
                if map_data is not None:
                    if raw_robot is None:
                        raw_robot = self._point_xy(getattr(map_data, "vacuum_position", None))
                    if raw_base is None:
                        raw_base = self._point_xy(getattr(map_data, "charger", None))
                    if not raw_path:
                        raw_path = self._flatten_path_points(getattr(map_data, "path", None))
                    try:
                        if map_data.image and not map_data.image.is_empty and map_data.image.data is not None:
                            image = map_data.image.data.convert("RGBA")
                    except Exception:
                        pass
            except Exception as exc:
                errors.append("Xiaomi JSON v2: " + (str(exc).strip() or type(exc).__name__))

        # Último fallback: parser Xiaomi antiguo, sólo para aportar diagnóstico.
        if map_data is None and envelope_version is None and MODEL not in _IJAI_MODELS:
            try:
                parser = self._xiaomi_parser()
                unpacked = parser.unpack_map(downloaded.hex(), model=MODEL[-16:], device_id=self.did)
                map_data = parser.parse(unpacked)
                decoder_family = "xiaomi-legacy"
                crypto_mode = "legacy-parser-suffix16"
                transformer = getattr(parser, "coord_transformer", None)
                raw_robot = self._point_xy(getattr(map_data, "vacuum_position", None))
                raw_base = self._point_xy(getattr(map_data, "charger", None))
                raw_path = self._flatten_path_points(getattr(map_data, "path", None))
            except Exception as exc:
                errors.append("Xiaomi legacy: " + (str(exc).strip() or type(exc).__name__))

        if map_data is None and raw_robot is None and not raw_path:
            detail = " | ".join(errors) if errors else "formato de mapa no reconocido"
            raise RuntimeError(
                f"Pude descargar el mapa ({raw_size} bytes) pero no descifrarlo. {detail}"
            )

        if raw_robot is None and raw_path:
            raw_robot = raw_path[-1]

        return MapSnapshot(
            image=image,
            map_data=map_data,
            transformer=transformer,
            map_name=map_name,
            crypto_mode=crypto_mode,
            raw_size=raw_size,
            envelope_version=envelope_version,
            map_id=map_id,
            resolution=resolution,
            raw_robot=raw_robot,
            raw_base=raw_base,
            raw_path=raw_path,
            parser_error=parser_error,
            decoder_family=decoder_family,
            wifi_sn_found=bool(wifi_sn),
            wifi_sn_length=len(wifi_sn or ""),
            mac_found=bool(mac),
            raw_prefix_hex=raw_prefix_hex,
        )

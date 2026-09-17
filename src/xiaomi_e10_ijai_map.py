import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests
from micloud import MiCloud
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai import RobotMap_pb2 as RobotMap
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser

from xiaomi_e10 import MODEL, XiaomiE10


@dataclass
class IjaiMapSnapshot:
    """Mapa Cloud del E10 ya descifrado.

    Mantiene también los nombres de atributos que consume app_v39 para poder
    reutilizar su pipeline de trayectoria sin convertir el E10 a un formato
    ficticio de Xiaomi JSON.
    """

    image: Any = None
    map_data: Any = None
    transformer: Any = None
    map_name: str = ""
    crypto_mode: str = "ijai-aes-ecb+zlib"
    raw_size: int = 0
    envelope_version: Any = "ijai-protobuf"
    map_id: Any = None
    resolution: Any = None
    raw_robot: tuple[float, float] | None = None
    raw_base: tuple[float, float] | None = None
    raw_path: list[tuple[float, float]] = field(default_factory=list)
    parser_error: str | None = None

    # Diagnóstico específico v40.
    slot: str = ""
    endpoint: str = ""
    decrypted_size: int = 0
    raw_prefix_hex: str = ""
    wifi_sn_source: str = ""
    wifi_sn_length: int = 0
    mac_available: bool = False
    pose_id: int | None = None
    upload_date: int | None = None
    valid_slots: list[str] = field(default_factory=list)
    slot_errors: dict[str, str] = field(default_factory=dict)


class XiaomiE10IjaiMapClient:
    """Obtiene el mapa real del Xiaomi Robot Vacuum E10.

    xiaomi.vacuum.b112 usa el motor/formato IJAI para su archivo Cloud. La clave
    no depende de ``model[-16:]``: se deriva con wifi_sn + user_id + did y una
    segunda clave AES basada en MAC + sufijo del modelo. Es la misma ruta que
    usan los extractores IJAI actuales.
    """

    WIFI_SN_MIN_LEN = 16
    WIFI_SN_MAX_LEN = 24

    def __init__(self, vacuum: XiaomiE10, settings: dict):
        self.vacuum = vacuum
        self.settings = settings
        self.did = str(settings.get("device_did") or "").strip()
        self.region = str(settings.get("device_region") or "").strip() or "us"
        raw_session = settings.get("cloud_session") or ""
        if not raw_session:
            raise RuntimeError("No hay sesión Xiaomi Cloud guardada.")
        try:
            self.session_data = json.loads(raw_session)
        except Exception as exc:
            raise RuntimeError("La sesión Xiaomi Cloud guardada no se pudo leer.") from exc
        if not self.did:
            raise RuntimeError("Falta el DID del E10 en la vinculación Xiaomi.")

        self._cached_mac: str | None = None
        self._cached_wifi_sn: str | None = None
        self._cached_wifi_sn_source: str | None = None

    # -------------------------------------------------------------- Cloud API
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
            except Exception:
                return None
        if not isinstance(response, dict):
            return None
        result = response.get("result")
        if not isinstance(result, dict):
            return None
        for key in ("url", "file_url", "download_url"):
            value = result.get(key)
            if value:
                return str(value)
        return None

    def _map_download_url(self, slot: str) -> tuple[str, str]:
        cloud = self._cloud()
        user_id = str(self.session_data["user_id"])
        obj_name = f"{user_id}/{self.did}/{str(slot).rstrip('/').split('/')[-1]}"
        params = {"data": json.dumps({"obj_name": obj_name}, separators=(",", ":"))}
        errors: list[str] = []

        # IJAI usa normalmente _pro. Dejamos el endpoint simple como fallback
        # porque Xiaomi cambia este detalle por región/firmware.
        for endpoint in ("/v2/home/get_interim_file_url_pro", "/v2/home/get_interim_file_url"):
            try:
                response = cloud.request_country(endpoint, self.region, dict(params))
                url = self._extract_url(response)
                if url:
                    return url, endpoint.rsplit("/", 1)[-1]
                errors.append(f"{endpoint}: sin URL")
            except Exception as exc:
                errors.append(f"{endpoint}: {str(exc).strip() or type(exc).__name__}")

        raise RuntimeError("Xiaomi Cloud no entregó URL para el slot " + str(slot) + " · " + " | ".join(errors[-2:]))

    # --------------------------------------------------------- material clave
    @classmethod
    def _is_wifi_sn(cls, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        value = value.strip()
        return cls.WIFI_SN_MIN_LEN <= len(value) <= cls.WIFI_SN_MAX_LEN and value.isupper()

    @staticmethod
    def _property_value(device, siid: int, piid: int):
        result = device.get_property_by(siid, piid)
        if isinstance(result, list) and result:
            item = result[0]
            if isinstance(item, dict) and item.get("code", 0) == 0:
                return item.get("value")
        return None

    def _device_mac(self) -> str:
        if self._cached_mac:
            return self._cached_mac
        try:
            info = self.vacuum.info()
            value = str(getattr(info, "mac_address", "") or "").strip()
        except Exception:
            value = ""
        if not value:
            raise RuntimeError("No pude obtener la MAC local del E10 para descifrar el mapa IJAI.")
        self._cached_mac = value
        return value

    def _wifi_sn(self) -> tuple[str, str]:
        if self._cached_wifi_sn:
            return self._cached_wifi_sn, self._cached_wifi_sn_source or "cache"

        device = self.vacuum.device
        for piid in (5, 3):
            try:
                value = self._property_value(device, 1, piid)
            except Exception:
                value = None
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8")
                except Exception:
                    value = None
            if self._is_wifi_sn(value):
                serial = str(value).strip()
                self._cached_wifi_sn = serial
                self._cached_wifi_sn_source = f"1/{piid}"
                return serial, self._cached_wifi_sn_source

        # Algunos IJAI empaquetan el serial dentro de multi-prop-vacuum 7/45.
        try:
            raw = self._property_value(device, 7, 45)
        except Exception:
            raw = None
        for part in str(raw or "").strip("[]").split(","):
            candidate = part.replace('"', "").split(";")[0].strip()
            if self._is_wifi_sn(candidate) and candidate.isalnum():
                self._cached_wifi_sn = candidate
                self._cached_wifi_sn_source = "7/45"
                return candidate, self._cached_wifi_sn_source

        raise RuntimeError(
            "No pude obtener wifi_sn del E10 (probé 1/5, 1/3 y 7/45); sin ese serial no se puede derivar la clave IJAI."
        )

    # ---------------------------------------------------------- upload fresco
    @staticmethod
    def _parse_map_list_response(response) -> list[dict]:
        if not isinstance(response, dict):
            return []
        outs = response.get("out")
        if not isinstance(outs, list):
            return []
        for out in outs:
            if not isinstance(out, dict) or int(out.get("piid", -1) or -1) != 4:
                continue
            value = out.get("value")
            try:
                payload = json.loads(value) if isinstance(value, str) else value
            except Exception:
                payload = None
            if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
                return payload
        return []

    def _active_map_id(self) -> int:
        try:
            response = self.vacuum.device.call_action_by(10, 1, [])
            maps = self._parse_map_list_response(response)
            for item in maps:
                if item.get("cur") and item.get("id") is not None:
                    return int(item["id"])
            if maps and maps[0].get("id") is not None:
                return int(maps[0]["id"])
        except Exception:
            pass

        try:
            value = self.vacuum.current_map_reference()
            return int(float(value))
        except Exception:
            return 0

    def request_fresh_upload(self) -> dict[str, Any]:
        """Pide al firmware que suba una copia fresca del mapa activo."""
        map_id = self._active_map_id()
        errors: list[str] = []
        # b112 expone upload-by-mapid-ii (10/14) y el legado 10/2.
        for aiid in (14, 2):
            try:
                response = self.vacuum.device.call_action_by(10, aiid, [int(map_id)])
                return {
                    "ok": True,
                    "map_id": int(map_id),
                    "action": f"10/{aiid}",
                    "response_type": type(response).__name__,
                }
            except Exception as exc:
                errors.append(f"10/{aiid}: {str(exc).strip() or type(exc).__name__}")
        return {
            "ok": False,
            "map_id": int(map_id),
            "action": "—",
            "error": " | ".join(errors),
        }

    # -------------------------------------------------------------- parsing
    @staticmethod
    def _normalize_download(raw: bytes) -> bytes:
        """Devuelve el texto base64 cifrado que espera el decryptor IJAI."""
        data = bytes(raw or b"").strip()
        if not data:
            return data
        # Algunos proxies pueden envolver el base64 en JSON o como JSON string.
        if data[:1] in (b"{", b'"'):
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    for key in ("data", "content", "map"):
                        value = parsed.get(key)
                        if isinstance(value, str) and value:
                            return value.encode("utf-8")
                elif isinstance(parsed, str):
                    return parsed.encode("utf-8")
            except Exception:
                pass
        return data

    @staticmethod
    def _xy(value) -> tuple[float, float] | None:
        if value is None:
            return None
        try:
            return float(value.x), float(value.y)
        except Exception:
            return None

    def _decode_slot(self, slot: str, url: str, endpoint: str, raw: bytes, wifi_sn: str, wifi_source: str, mac: str) -> IjaiMapSnapshot:
        parser = IjaiMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])
        encoded = self._normalize_download(raw)
        if not encoded:
            raise RuntimeError("archivo vacío")

        unpacked = parser.unpack_map(
            encoded,
            wifi_sn=wifi_sn,
            owner_id=str(self.session_data["user_id"]),
            device_id=self.did,
            model=MODEL,
            device_mac=mac,
        )

        # Extraemos pose/historial directamente del protobuf. Así, aunque el
        # renderer falle con alguna variante de imagen, el movimiento sirve.
        robot_map = RobotMap.RobotMap()
        robot_map.ParseFromString(unpacked)

        robot = None
        base = None
        path: list[tuple[float, float]] = []
        pose_id = None
        upload_date = None
        map_id = None
        resolution = None

        try:
            if robot_map.HasField("currentPose"):
                robot = (float(robot_map.currentPose.x), float(robot_map.currentPose.y))
                pose_id = int(robot_map.currentPose.poseId)
        except Exception:
            pass
        try:
            if robot_map.HasField("chargeStation"):
                base = (float(robot_map.chargeStation.x), float(robot_map.chargeStation.y))
        except Exception:
            pass
        try:
            if robot_map.HasField("historyPose"):
                path = [(float(point.x), float(point.y)) for point in robot_map.historyPose.points]
        except Exception:
            path = []
        try:
            if robot_map.HasField("mapHead"):
                map_id = int(robot_map.mapHead.mapHeadId)
                resolution = float(robot_map.mapHead.resolution)
        except Exception:
            pass
        try:
            if robot_map.HasField("mapExtInfo"):
                upload_date = int(robot_map.mapExtInfo.mapUploadDate)
        except Exception:
            pass

        map_data = None
        image = None
        parser_error = None
        transformer = None
        try:
            map_data = parser.parse(unpacked)
            transformer = getattr(parser, "coord_transformer", None)
            if map_data.image and not map_data.image.is_empty and map_data.image.data is not None:
                image = map_data.image.data.convert("RGBA")
        except Exception as exc:
            parser_error = str(exc).strip() or type(exc).__name__

        # Fallback a MapData si el protobuf directo no marcó presencia.
        if map_data is not None:
            if robot is None:
                robot = self._xy(getattr(map_data, "vacuum_position", None))
            if base is None:
                base = self._xy(getattr(map_data, "charger", None))
            if not path:
                try:
                    path_obj = getattr(map_data, "path", None)
                    for subpath in getattr(path_obj, "path", []) or []:
                        for point in subpath:
                            xy = self._xy(point)
                            if xy is not None:
                                path.append(xy)
                except Exception:
                    pass

        return IjaiMapSnapshot(
            image=image,
            map_data=map_data,
            transformer=transformer,
            map_name=str(slot),
            raw_size=len(raw),
            map_id=map_id,
            resolution=resolution,
            raw_robot=robot,
            raw_base=base,
            raw_path=path,
            parser_error=parser_error,
            slot=str(slot),
            endpoint=endpoint,
            decrypted_size=len(unpacked),
            raw_prefix_hex=bytes(raw[:16]).hex(),
            wifi_sn_source=wifi_source,
            wifi_sn_length=len(wifi_sn),
            mac_available=bool(mac),
            pose_id=pose_id,
            upload_date=upload_date,
        )

    def load(self) -> IjaiMapSnapshot:
        wifi_sn, wifi_source = self._wifi_sn()
        mac = self._device_mac()

        candidates: list[str] = []
        try:
            current = str(self.vacuum.current_map_name()).strip()
            if current:
                candidates.append(current.rstrip("/").split("/")[-1])
        except Exception:
            pass
        # El firmware IJAI alterna dos objetos Cloud durante las actualizaciones.
        for slot in ("0", "1"):
            if slot not in candidates:
                candidates.append(slot)

        valid: list[IjaiMapSnapshot] = []
        errors: dict[str, str] = {}
        for slot in candidates:
            try:
                url, endpoint = self._map_download_url(slot)
                response = requests.get(url, timeout=25)
                response.raise_for_status()
                raw = bytes(response.content)
                snapshot = self._decode_slot(slot, url, endpoint, raw, wifi_sn, wifi_source, mac)
                valid.append(snapshot)
            except Exception as exc:
                errors[str(slot)] = str(exc).strip() or type(exc).__name__

        if not valid:
            detail = " | ".join(f"slot {slot}: {message}" for slot, message in errors.items())
            raise RuntimeError("No pude descifrar ningún slot IJAI del E10. " + detail)

        # Preferimos la subida más nueva. Si el firmware no informa fecha,
        # favorecemos pose-id/path más avanzados y luego el archivo más grande.
        def freshness(snapshot: IjaiMapSnapshot):
            return (
                int(snapshot.upload_date or 0),
                int(snapshot.pose_id or 0),
                len(snapshot.raw_path or []),
                int(snapshot.raw_size or 0),
            )

        selected = max(valid, key=freshness)
        selected.valid_slots = [item.slot for item in valid]
        selected.slot_errors = errors
        return selected

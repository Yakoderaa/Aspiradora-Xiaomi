import base64
import gzip
import hashlib
import json
import re
import zlib
from dataclasses import dataclass, field
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from micloud import MiCloud
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai import RobotMap_pb2 as RobotMap
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser

from xiaomi_e10 import MODEL, XiaomiE10


@dataclass
class ExhaustiveMapSnapshot:
    image: Any = None
    map_data: Any = None
    transformer: Any = None
    map_name: str = ""
    crypto_mode: str = "unknown"
    raw_size: int = 0
    envelope_version: Any = "ijai-or-auto"
    map_id: Any = None
    resolution: Any = None
    raw_robot: tuple[float, float] | None = None
    raw_base: tuple[float, float] | None = None
    raw_path: list[tuple[float, float]] = field(default_factory=list)
    parser_error: str | None = None

    slot: str = ""
    endpoint: str = ""
    decrypted_size: int = 0
    raw_prefix_hex: str = ""
    blob_sha256: str = ""
    blob_kind: str = ""
    wifi_sn_source: str = ""
    wifi_sn_length: int = 0
    mac_source: str = ""
    mac_available: bool = False
    owner_source: str = ""
    did_source: str = ""
    pose_id: int | None = None
    upload_date: int | None = None
    valid_slots: list[str] = field(default_factory=list)
    slot_errors: dict[str, str] = field(default_factory=dict)
    decode_attempts: int = 0
    candidate_counts: dict[str, int] = field(default_factory=dict)


class XiaomiE10MapV41:
    """Pipeline de mapa defensivo para xiaomi.vacuum.b112.

    No presupone que el blob sea siempre la variante IJAI publicada por una sola
    librería. Reúne varias fuentes de material de clave y prueba representaciones,
    derivaciones y capas de compresión compatibles, aceptando únicamente un
    resultado que se valide como RobotMap protobuf coherente.
    """

    WIFI_SN_MIN_LEN = 8
    WIFI_SN_MAX_LEN = 40
    CLOUD_SLOTS = ("0", "1")

    def __init__(self, vacuum: XiaomiE10, settings: dict):
        self.vacuum = vacuum
        self.settings = settings or {}
        self.did = str(self.settings.get("device_did") or "").strip()
        self.region = str(self.settings.get("device_region") or "").strip() or "us"
        raw_session = self.settings.get("cloud_session") or ""
        if not raw_session:
            raise RuntimeError("No hay sesión Xiaomi Cloud guardada.")
        try:
            self.session_data = json.loads(raw_session)
        except Exception as exc:
            raise RuntimeError("La sesión Xiaomi Cloud guardada no se pudo interpretar.") from exc
        if not self.did:
            raise RuntimeError("Falta el DID del E10.")

        self.last_key_diagnostics: dict[str, Any] = {}
        self.last_upload_diagnostics: dict[str, Any] = {}
        self.last_slot_diagnostics: dict[str, Any] = {}
        self.privacy_original: int | None = None
        self.privacy_temporarily_enabled = False
        self.decode_attempts = 0

    # ------------------------------------------------------------- utilidades
    @staticmethod
    def _dedupe(items):
        result = []
        seen = set()
        for value, source in items:
            key = str(value)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append((value, source))
        return result

    @staticmethod
    def _property_value(device, siid: int, piid: int):
        result = device.get_property_by(siid, piid)
        if isinstance(result, list) and result:
            item = result[0]
            if isinstance(item, dict) and item.get("code", 0) in (0, None):
                return item.get("value")
        return None

    @staticmethod
    def _extract_action_out(response):
        out = {}
        if isinstance(response, dict):
            for item in response.get("out") or []:
                if isinstance(item, dict) and item.get("piid") is not None:
                    out[str(item.get("piid"))] = item.get("value")
        return out

    @staticmethod
    def _safe_label(value):
        if value is None:
            return "—"
        text = str(value)
        return f"len={len(text)}"

    # -------------------------------------------------------------- Xiaomi Cloud
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
    def _decode_cloud_json(response):
        if isinstance(response, (bytes, bytearray, memoryview)):
            response = bytes(response).decode("utf-8-sig")
        if isinstance(response, str):
            text = response.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            response = json.loads(text)
        return response if isinstance(response, dict) else {}

    def _cloud_props(self, props):
        try:
            payload = {
                "params": [{"did": self.did, "siid": s, "piid": p} for s, p in props],
                "datasource": 2,
            }
            response = self._cloud().request_country(
                "/miotspec/prop/get",
                self.region,
                {"data": json.dumps(payload, separators=(",", ":"))},
            )
            decoded = self._decode_cloud_json(response)
            result = {}
            for item in decoded.get("result") or []:
                if isinstance(item, dict) and item.get("code", 0) in (0, None):
                    result[(int(item.get("siid")), int(item.get("piid")))] = item.get("value")
            return result
        except Exception:
            return {}

    def _cloud_device(self):
        try:
            devices = self._cloud().get_devices(country=self.region) or []
        except Exception:
            return None
        for item in devices:
            if not isinstance(item, dict):
                continue
            if str(item.get("did") or "") == self.did:
                return item
        for item in devices:
            if isinstance(item, dict) and item.get("model") == MODEL:
                return item
        return None

    # ---------------------------------------------------------- candidatos clave
    @staticmethod
    def _looks_serial(value):
        if not isinstance(value, str):
            return False
        text = value.strip().strip('"')
        if not (XiaomiE10MapV41.WIFI_SN_MIN_LEN <= len(text) <= XiaomiE10MapV41.WIFI_SN_MAX_LEN):
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9._:-]+", text))

    def _key_candidates(self):
        device = self.vacuum.device
        wifi = []
        owners = []
        dids = []
        macs = []

        user_id = str(self.session_data.get("user_id") or "").strip()
        cuser_id = str(self.session_data.get("cuser_id") or "").strip()
        if user_id:
            owners.append((user_id, "session.user_id"))
        if cuser_id:
            owners.append((cuser_id, "session.cuser_id"))
        if self.did:
            dids.append((self.did, "settings.did"))

        # Fuentes locales verificadas por integraciones IJAI y un barrido acotado
        # del servicio device-information para variantes de firmware.
        raw_745 = None
        for piid in range(1, 13):
            try:
                value = self._property_value(device, 1, piid)
            except Exception:
                value = None
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8")
                except Exception:
                    value = None
            if self._looks_serial(value):
                wifi.append((str(value).strip(), f"LAN 1/{piid}"))
        try:
            raw_745 = self._property_value(device, 7, 45)
        except Exception:
            raw_745 = None
        for part in str(raw_745 or "").strip("[]").split(","):
            cleaned = part.replace('"', "").strip()
            serial, sep, suffix = cleaned.partition(";")
            serial = serial.strip()
            if self._looks_serial(serial):
                wifi.append((serial, "LAN 7/45"))
                if sep and suffix.strip():
                    owners.append((suffix.strip(), "UID sufijo 7/45"))

        # Cloud puede exponer el mismo serial aun cuando una propiedad LAN dé error.
        cloud_values = self._cloud_props([(1, p) for p in range(1, 13)] + [(7, 45)])
        for (siid, piid), value in cloud_values.items():
            if siid == 7 and piid == 45:
                for part in str(value or "").strip("[]").split(","):
                    cleaned = part.replace('"', "").strip()
                    serial, sep, suffix = cleaned.partition(";")
                    if self._looks_serial(serial.strip()):
                        wifi.append((serial.strip(), "Cloud 7/45"))
                        if sep and suffix.strip():
                            owners.append((suffix.strip(), "Cloud UID sufijo 7/45"))
            elif self._looks_serial(value):
                wifi.append((str(value).strip(), f"Cloud {siid}/{piid}"))

        try:
            info = self.vacuum.info()
            mac = str(getattr(info, "mac_address", "") or "").strip()
            if mac:
                macs.append((mac, "miIO info"))
        except Exception:
            pass
        stored_mac = str(self.settings.get("device_mac") or "").strip()
        if stored_mac:
            macs.append((stored_mac, "settings.device_mac"))

        cloud_dev = self._cloud_device()
        if isinstance(cloud_dev, dict):
            cloud_did = str(cloud_dev.get("did") or "").strip()
            if cloud_did:
                dids.append((cloud_did, "Cloud device.did"))
            for key in ("mac", "macAddress", "mac_address"):
                value = str(cloud_dev.get(key) or "").strip()
                if value:
                    macs.append((value, f"Cloud device.{key}"))
            # Algunos backends guardan serial/SN como metadato no MIoT.
            for key, value in cloud_dev.items():
                key_l = str(key).lower()
                if any(word in key_l for word in ("serial", "wifi_sn", "wifisn", "sn")) and self._looks_serial(value):
                    wifi.append((str(value).strip(), f"Cloud device.{key}"))

        wifi = self._dedupe(wifi)
        owners = self._dedupe(owners)
        dids = self._dedupe(dids)
        macs = self._dedupe(macs)
        self.last_key_diagnostics = {
            "wifi_sources": [source for _, source in wifi],
            "owner_sources": [source for _, source in owners],
            "did_sources": [source for _, source in dids],
            "mac_sources": [source for _, source in macs],
            "wifi_count": len(wifi),
            "owner_count": len(owners),
            "did_count": len(dids),
            "mac_count": len(macs),
        }
        return wifi, owners, dids, macs

    @staticmethod
    def _normalize_mac(mac):
        return re.sub(r"[^0-9A-Fa-f]", "", str(mac or ""))

    @classmethod
    def _derive_keys(cls, wifi, owners, dids, macs):
        candidates = []
        model_tail = MODEL.split(".")[-1]
        for sn, sn_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    sources = [
                        f"{sn}+{owner}+{did}",
                        f"{sn}+{did}+{owner}",
                        f"{sn}{owner}{did}",
                        f"{sn}+{did}",
                    ]
                    for mac, mac_source in macs:
                        hex_mac = cls._normalize_mac(mac)
                        if len(hex_mac) != 12:
                            continue
                        temp_keys = [
                            (hex_mac.lower() + model_tail.lower(), "mac-lower/model-lower"),
                            (hex_mac.upper() + model_tail.lower(), "mac-upper/model-lower"),
                            (hex_mac.lower() + model_tail.upper(), "mac-lower/model-upper"),
                            (hex_mac.upper() + model_tail.upper(), "mac-upper/model-upper"),
                        ]
                        for temp_key, variant in temp_keys:
                            if len(temp_key.encode("utf-8")) not in (16, 24, 32):
                                continue
                            for source_index, original in enumerate(sources):
                                try:
                                    encrypted = AES.new(temp_key.encode("utf-8"), AES.MODE_ECB).encrypt(
                                        pad(original.encode("utf-8"), AES.block_size)
                                    )
                                except Exception:
                                    continue
                                b64 = base64.b64encode(encrypted)
                                # Upstream: MD5 del texto Base64. Además probamos el
                                # material binario para cubrir variantes conocidas.
                                keys = [
                                    (hashlib.md5(b64).digest(), "md5(base64)"),
                                    (hashlib.md5(encrypted).digest(), "md5(cipher)"),
                                ]
                                for key, md5_variant in keys:
                                    label = (
                                        f"{sn_source} | {owner_source} | {did_source} | {mac_source} | "
                                        f"{variant} | source#{source_index + 1} | {md5_variant}"
                                    )
                                    candidates.append((key, label))
        # dedupe por clave final para no multiplicar intentos equivalentes.
        seen = set()
        unique = []
        for key, label in candidates:
            if key in seen:
                continue
            seen.add(key)
            unique.append((key, label))
        return unique

    # --------------------------------------------------------------- privacidad
    def map_privacy_state(self):
        try:
            value = self._property_value(self.vacuum.device, 10, 23)
            return int(value) if value is not None else None
        except Exception:
            return None

    def enable_map_upload_temporarily(self):
        current = self.map_privacy_state()
        if self.privacy_original is None:
            self.privacy_original = current
        # Spec b112: 0=Enable, 1=DisEnable para permiso de subir mapa.
        if current == 1:
            try:
                self.vacuum.device.set_property_by(10, 23, 0)
                self.privacy_temporarily_enabled = True
                return True
            except Exception:
                return False
        return current == 0

    def restore_map_privacy(self):
        if not self.privacy_temporarily_enabled:
            return False
        if self.privacy_original is None:
            return False
        try:
            self.vacuum.device.set_property_by(10, 23, int(self.privacy_original))
            self.privacy_temporarily_enabled = False
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ mapa activo
    @staticmethod
    def _parse_map_list(response):
        if not isinstance(response, dict):
            return []
        for item in response.get("out") or []:
            if not isinstance(item, dict) or int(item.get("piid", -1) or -1) != 4:
                continue
            try:
                data = json.loads(item.get("value")) if isinstance(item.get("value"), str) else item.get("value")
            except Exception:
                data = None
            if isinstance(data, list) and all(isinstance(x, dict) for x in data):
                return data
        return []

    def active_map_id(self):
        try:
            response = self.vacuum.device.call_action_by(10, 1, [])
            maps = self._parse_map_list(response)
            for item in maps:
                if item.get("cur") and item.get("id") is not None:
                    return int(item["id"]), maps
            if maps and maps[0].get("id") is not None:
                return int(maps[0]["id"]), maps
        except Exception:
            maps = []
        try:
            raw = self._property_value(self.vacuum.device, 10, 2)
            value = int(float(raw))
            return value, maps
        except Exception:
            return None, maps

    def request_fresh_upload(self):
        """Agota las acciones de upload apropiadas sin usar map_id=0 por ID."""
        self.enable_map_upload_temporarily()
        map_id, maps = self.active_map_id()
        attempts = []

        def call(aiid, params, label):
            try:
                response = self.vacuum.device.call_action_by(10, aiid, params)
                attempts.append({
                    "action": f"10/{aiid}", "label": label, "ok": True,
                    "out": self._extract_action_out(response),
                })
                return True
            except Exception as exc:
                attempts.append({
                    "action": f"10/{aiid}", "label": label, "ok": False,
                    "error": str(exc).strip() or type(exc).__name__,
                })
                return False

        # Según el spec B112, éstas son las rutas correctas para mapa realtime.
        call(18, [], "upmapdata / solicitar subida")
        call(15, [0], "upload-by-maptype-ii / Realtime")
        call(6, [0], "upload-by-maptype / Realtime")
        if map_id is not None and int(map_id) > 0:
            call(14, [int(map_id)], "upload-by-mapid-ii")
            call(2, [int(map_id)], "upload-by-mapid")

        result = {
            "map_id": map_id,
            "map_list_count": len(maps),
            "attempts": attempts,
            "privacy_original": self.privacy_original,
            "privacy_now": self.map_privacy_state(),
            "privacy_temp": self.privacy_temporarily_enabled,
            "ok": any(x.get("ok") for x in attempts),
        }
        self.last_upload_diagnostics = result
        return result

    # --------------------------------------------------------------- descarga
    @staticmethod
    def _extract_url(response):
        try:
            response = XiaomiE10MapV41._decode_cloud_json(response)
        except Exception:
            return None
        result = response.get("result")
        if not isinstance(result, dict):
            return None
        for key in ("url", "file_url", "download_url"):
            if result.get(key):
                return str(result[key])
        return None

    def _map_download_url(self, slot):
        user_id = str(self.session_data.get("user_id") or "")
        obj_name = f"{user_id}/{self.did}/{slot}"
        params = {"data": json.dumps({"obj_name": obj_name}, separators=(",", ":"))}
        errors = []
        for endpoint in ("get_interim_file_url_pro", "get_interim_file_url"):
            try:
                response = self._cloud().request_country(
                    f"/v2/home/{endpoint}", self.region, dict(params)
                )
                url = self._extract_url(response)
                if url:
                    return url, endpoint
                errors.append(endpoint + ": sin URL")
            except Exception as exc:
                errors.append(endpoint + ": " + (str(exc).strip() or type(exc).__name__))
        raise RuntimeError(" | ".join(errors))

    @staticmethod
    def _blob_variants(raw):
        variants = []
        seen = set()

        def add(data, label):
            if not isinstance(data, (bytes, bytearray, memoryview)):
                return
            data = bytes(data).strip()
            if not data or data in seen:
                return
            seen.add(data)
            variants.append((data, label))

        add(raw, "raw")
        stripped = bytes(raw or b"").strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, str):
                add(parsed.encode(), "json-string")
            elif isinstance(parsed, dict):
                for key in ("data", "content", "map", "payload"):
                    value = parsed.get(key)
                    if isinstance(value, str):
                        add(value.encode(), f"json.{key}")
        except Exception:
            pass

        for data, label in list(variants):
            text = None
            try:
                text = data.decode("ascii").strip()
            except Exception:
                pass
            if text:
                if len(text) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", text):
                    try:
                        add(bytes.fromhex(text), label + "->hex")
                    except Exception:
                        pass
                compact = re.sub(r"\s+", "", text)
                if len(compact) >= 8 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
                    try:
                        padded = compact + "=" * ((4 - len(compact) % 4) % 4)
                        add(base64.urlsafe_b64decode(padded), label + "->b64")
                    except Exception:
                        pass
        # Algunas respuestas comprimen la capa externa antes del cifrado.
        for data, label in list(variants):
            for wbits, name in ((zlib.MAX_WBITS, "zlib"), (-zlib.MAX_WBITS, "deflate"), (16 + zlib.MAX_WBITS, "gzip")):
                try:
                    add(zlib.decompress(data, wbits), label + "->" + name)
                except Exception:
                    pass
        return variants

    @staticmethod
    def _post_decrypt_variants(data):
        variants = []
        seen = set()

        def add(payload, label):
            if not isinstance(payload, (bytes, bytearray, memoryview)):
                return
            payload = bytes(payload)
            if not payload or payload in seen:
                return
            seen.add(payload)
            variants.append((payload, label))

        add(data, "plain")
        try:
            text = bytes(data).decode("ascii").strip()
        except Exception:
            text = ""
        if text:
            if len(text) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", text):
                try:
                    add(bytes.fromhex(text), "plain->hex")
                except Exception:
                    pass
            if re.fullmatch(r"[A-Za-z0-9+/=_-]+", text):
                try:
                    padded = text + "=" * ((4 - len(text) % 4) % 4)
                    add(base64.urlsafe_b64decode(padded), "plain->b64")
                except Exception:
                    pass
        for payload, label in list(variants):
            for wbits, name in ((zlib.MAX_WBITS, "zlib"), (-zlib.MAX_WBITS, "deflate"), (16 + zlib.MAX_WBITS, "gzip")):
                try:
                    add(zlib.decompress(payload, wbits), label + "->" + name)
                except Exception:
                    pass
            try:
                add(gzip.decompress(payload), label + "->gzip-lib")
            except Exception:
                pass
        return variants

    @staticmethod
    def _protobuf_quality(payload):
        rm = RobotMap.RobotMap()
        try:
            rm.ParseFromString(payload)
        except Exception:
            return None
        score = 0
        try:
            if rm.HasField("mapHead"):
                score += 2
                if getattr(rm.mapHead, "resolution", 0):
                    score += 2
                if getattr(rm.mapHead, "sizeX", 0) and getattr(rm.mapHead, "sizeY", 0):
                    score += 3
        except Exception:
            pass
        try:
            if rm.HasField("currentPose"):
                score += 4
        except Exception:
            pass
        try:
            if rm.HasField("chargeStation"):
                score += 3
        except Exception:
            pass
        try:
            if rm.HasField("historyPose") and len(rm.historyPose.points):
                score += 4
        except Exception:
            pass
        try:
            if rm.HasField("mapData") and len(rm.mapData.mapData):
                score += 4
        except Exception:
            pass
        return (score, rm) if score >= 2 else None

    def _decode_exhaustive(self, raw, key_candidates):
        self.decode_attempts = 0
        winners = []
        blob_variants = self._blob_variants(raw)

        # Primero: blob ya legible/comprimido sin cifrado.
        for blob, blob_label in blob_variants:
            for payload, post_label in self._post_decrypt_variants(blob):
                self.decode_attempts += 1
                quality = self._protobuf_quality(payload)
                if quality:
                    winners.append((quality[0], payload, quality[1], f"sin AES | {blob_label} | {post_label}", "sin clave"))

        # Luego todas las derivaciones AES plausibles.
        for key, key_label in key_candidates:
            for blob, blob_label in blob_variants:
                if len(blob) < 16 or len(blob) % 16:
                    continue
                try:
                    decrypted = AES.new(key, AES.MODE_ECB).decrypt(blob)
                except Exception:
                    continue
                plains = [(decrypted, "aes-raw")]
                try:
                    plains.insert(0, (unpad(decrypted, AES.block_size, "pkcs7"), "aes-pkcs7"))
                except Exception:
                    pass
                for plain, aes_label in plains:
                    for payload, post_label in self._post_decrypt_variants(plain):
                        self.decode_attempts += 1
                        quality = self._protobuf_quality(payload)
                        if quality:
                            winners.append((
                                quality[0], payload, quality[1],
                                f"AES-ECB | {blob_label} | {aes_label} | {post_label}", key_label,
                            ))
        if not winners:
            raise RuntimeError(f"ninguna de {self.decode_attempts} variantes produjo un RobotMap válido")
        winners.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        return winners[0]

    @staticmethod
    def _xy(field):
        if field is None:
            return None
        try:
            return float(field.x), float(field.y)
        except Exception:
            return None

    def _snapshot_from_payload(self, slot, endpoint, raw, payload, robot_map, mode, key_label, key_diag):
        robot = base = None
        path = []
        pose_id = upload_date = map_id = resolution = None
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
                path = [(float(p.x), float(p.y)) for p in robot_map.historyPose.points]
        except Exception:
            pass
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

        parser = IjaiMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])
        map_data = None
        image = None
        parser_error = None
        try:
            map_data = parser.parse(payload)
            if robot is None:
                robot = self._xy(getattr(map_data, "vacuum_position", None))
            if base is None:
                base = self._xy(getattr(map_data, "charger", None))
            if map_data.image and not map_data.image.is_empty and map_data.image.data is not None:
                image = map_data.image.data.convert("RGBA")
        except Exception as exc:
            parser_error = str(exc).strip() or type(exc).__name__

        return ExhaustiveMapSnapshot(
            image=image,
            map_data=map_data,
            transformer=getattr(parser, "coord_transformer", None),
            map_name=str(slot),
            crypto_mode=mode,
            raw_size=len(raw),
            map_id=map_id,
            resolution=resolution,
            raw_robot=robot,
            raw_base=base,
            raw_path=path,
            parser_error=parser_error,
            slot=str(slot),
            endpoint=endpoint,
            decrypted_size=len(payload),
            raw_prefix_hex=bytes(raw[:24]).hex(),
            blob_sha256=hashlib.sha256(raw).hexdigest(),
            blob_kind=("ascii" if all(32 <= b < 127 for b in raw[:64]) else "binary"),
            wifi_sn_source=key_diag.get("wifi_source", ""),
            wifi_sn_length=int(key_diag.get("wifi_len", 0) or 0),
            mac_source=key_diag.get("mac_source", ""),
            mac_available=bool(key_diag.get("mac_source")),
            owner_source=key_diag.get("owner_source", ""),
            did_source=key_diag.get("did_source", ""),
            pose_id=pose_id,
            upload_date=upload_date,
            decode_attempts=self.decode_attempts,
            candidate_counts={k: int(v) for k, v in self.last_key_diagnostics.items() if k.endswith("_count")},
        )

    @staticmethod
    def _key_sources_from_label(label):
        parts = [p.strip() for p in str(label).split("|")]
        return {
            "wifi_source": parts[0] if len(parts) > 0 else "",
            "owner_source": parts[1] if len(parts) > 1 else "",
            "did_source": parts[2] if len(parts) > 2 else "",
            "mac_source": parts[3] if len(parts) > 3 else "",
        }

    def load(self):
        wifi, owners, dids, macs = self._key_candidates()
        key_candidates = self._derive_keys(wifi, owners, dids, macs)
        self.last_key_diagnostics["derived_key_count"] = len(key_candidates)

        valid = []
        errors = {}
        slot_diag = {}
        for slot in self.CLOUD_SLOTS:
            try:
                url, endpoint = self._map_download_url(slot)
                response = requests.get(url, timeout=30)
                status = int(response.status_code)
                raw = bytes(response.content or b"")
                slot_diag[str(slot)] = {
                    "http": status,
                    "bytes": len(raw),
                    "sha12": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
                    "endpoint": endpoint,
                }
                response.raise_for_status()
                score, payload, rm, mode, key_label = self._decode_exhaustive(raw, key_candidates)
                key_diag = self._key_sources_from_label(key_label)
                if key_label != "sin clave":
                    # Sólo longitud, nunca el serial/identificador real.
                    chosen_source = key_diag.get("wifi_source")
                    for value, source in wifi:
                        if source == chosen_source:
                            key_diag["wifi_len"] = len(str(value))
                            break
                snapshot = self._snapshot_from_payload(
                    slot, endpoint, raw, payload, rm, mode, key_label, key_diag
                )
                valid.append((score, snapshot))
            except Exception as exc:
                errors[str(slot)] = str(exc).strip() or type(exc).__name__

        self.last_slot_diagnostics = slot_diag
        if not valid:
            detail = " | ".join(f"slot {k}: {v}" for k, v in errors.items())
            raise RuntimeError("No pude validar ningún mapa después de agotar las variantes. " + detail)

        def freshness(item):
            score, snap = item
            return (
                int(snap.upload_date or 0), int(snap.pose_id or 0),
                len(snap.raw_path or []), score, int(snap.raw_size or 0),
            )

        _, selected = max(valid, key=freshness)
        selected.valid_slots = [snap.slot for _, snap in valid]
        selected.slot_errors = errors
        return selected

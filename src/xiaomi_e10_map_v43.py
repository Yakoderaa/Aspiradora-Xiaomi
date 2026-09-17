import base64
import hashlib
import json
import re
import zlib
from typing import Any

import requests
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.drawable import Drawable
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_xiaomi.map_data_parser import XiaomiMapDataParser

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41 import ExhaustiveMapSnapshot
from xiaomi_e10_map_v42 import XiaomiE10MapV42


class XiaomiE10MapV43(XiaomiE10MapV42):
    """v43: prueba primero la familia Xiaomi-JSON usada por el extractor Cloud.

    La evidencia específica para xiaomi.vacuum.b112 en Xiaomi Cloud Map Extractor
    lo enruta por XiaomiMapDataParser. El detalle decisivo es que el blob debe
    pasarse a ``unpack_map`` como TEXTO hexadecimal, no como bytes crudos.

    Para el modelo corto b112 el parser necesita una clave AES de longitud válida;
    probamos primero ``MODEL[-16:]`` (la corrección que ya habíamos identificado
    en v39) y después variantes conservadoras. Si esta ruta no valida JSON útil,
    conservamos IJAI v42/v41 como fallback.
    """

    XIAOMI_DRAWABLES = [
        Drawable.PATH,
        Drawable.CHARGER,
        Drawable.VACUUM_POSITION,
        Drawable.ROOM_NAMES,
        Drawable.NO_GO_AREAS,
        Drawable.VIRTUAL_WALLS,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_xiaomi_diagnostics: dict[str, Any] = {}

    # ---------------------------------------------------------- variantes blob
    @staticmethod
    def _xiaomi_blob_variants(raw: bytes):
        result = []
        seen = set()

        def add(data, label):
            if isinstance(data, str):
                data = data.encode("latin1")
            if not isinstance(data, (bytes, bytearray, memoryview)):
                return
            data = bytes(data).strip()
            if not data or data in seen:
                return
            seen.add(data)
            result.append((data, label))

        add(raw, "raw")
        stripped = bytes(raw or b"").strip()

        # Formato viejo: {"data":"<base64>"}; formato nuevo: ciphertext directo.
        try:
            wrapped = json.loads(stripped)
            if isinstance(wrapped, dict):
                for key in ("data", "content", "map", "payload"):
                    value = wrapped.get(key)
                    if isinstance(value, str) and value:
                        try:
                            add(base64.b64decode(value), f"json.{key}->base64")
                        except Exception:
                            add(value, f"json.{key}")
            elif isinstance(wrapped, str):
                try:
                    add(base64.b64decode(wrapped), "json-string->base64")
                except Exception:
                    add(wrapped, "json-string")
        except Exception:
            pass

        # Algunos backends pueden entregar el ciphertext como texto base64/hex.
        try:
            text = stripped.decode("ascii").strip()
        except Exception:
            text = ""
        compact = re.sub(r"\s+", "", text) if text else ""
        if compact:
            if len(compact) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", compact):
                try:
                    add(bytes.fromhex(compact), "ascii-hex")
                except Exception:
                    pass
            if re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
                try:
                    padded = compact + "=" * ((4 - len(compact) % 4) % 4)
                    add(base64.urlsafe_b64decode(padded), "ascii-base64")
                except Exception:
                    pass
        return result

    # ---------------------------------------------------------- claves modelo
    @staticmethod
    def _model_key_candidates():
        transformed = MODEL.replace("xiaomi", "mi")
        candidates = [
            (MODEL[-16:], "MODEL[-16:]"),
            (transformed, "xiaomi->mi"),
            (transformed.rjust(16, "0"), "xiaomi->mi · pad-left-0"),
            (transformed.ljust(16, "0"), "xiaomi->mi · pad-right-0"),
            (MODEL[:16], "MODEL[:16]"),
        ]
        result = []
        seen = set()
        for value, label in candidates:
            value = str(value)
            # AES sólo admite 16/24/32 bytes. No intentamos entradas imposibles.
            if len(value.encode("latin1", errors="ignore")) not in (16, 24, 32):
                continue
            if value in seen:
                continue
            seen.add(value)
            result.append((value, label))
        return result

    # ------------------------------------------------------------- extracción
    @staticmethod
    def _payload_xy(value):
        if isinstance(value, dict) and "x" in value and "y" in value:
            try:
                return float(value["x"]), float(value["y"])
            except Exception:
                return None
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return float(value[0]), float(value[1])
            except Exception:
                return None
        return None

    @classmethod
    def _payload_path(cls, payload):
        paths = payload.get("paths") if isinstance(payload, dict) else None
        points_src = paths.get("points") if isinstance(paths, dict) else paths
        if not isinstance(points_src, list):
            return []
        result = []
        for item in points_src:
            xy = cls._payload_xy(item)
            if xy is not None:
                result.append(xy)
        return result

    @classmethod
    def _payload_base(cls, payload):
        if not isinstance(payload, dict):
            return None
        if payload.get("have_pile") or ("pile_x" in payload and "pile_y" in payload):
            try:
                return float(payload.get("pile_x", 0)), float(payload.get("pile_y", 0))
            except Exception:
                pass
        for key in ("charger", "charge_station", "charging_station", "base"):
            xy = cls._payload_xy(payload.get(key))
            if xy is not None:
                return xy
        return None

    @staticmethod
    def _image_from_map_data(map_data):
        try:
            image_data = getattr(map_data, "image", None)
            if image_data is None or getattr(image_data, "is_empty", False):
                return None
            image = getattr(image_data, "data", None)
            return image.convert("RGBA") if image is not None and hasattr(image, "convert") else image
        except Exception:
            return None

    @staticmethod
    def _valid_xiaomi_payload(payload):
        if not isinstance(payload, dict):
            return False
        useful = ("position", "paths", "map_data", "width", "height", "pile_x", "map_id")
        return any(key in payload for key in useful)

    def _snapshot_xiaomi(self, raw, blob, slot, endpoint, decrypted, payload, map_data, key_label, blob_label):
        robot = self._payload_xy(payload.get("position"))
        base = self._payload_base(payload)
        path = self._payload_path(payload)
        image = None
        parser_error = None

        if map_data is not None:
            robot = robot or self._xy(getattr(map_data, "vacuum_position", None))
            base = base or self._xy(getattr(map_data, "charger", None))
            if not path:
                path = self._path_points(map_data)
            image = self._image_from_map_data(map_data)

        try:
            map_id = int(payload.get("map_id")) if payload.get("map_id") is not None else None
        except Exception:
            map_id = None
        try:
            resolution = float(payload.get("resolution")) if payload.get("resolution") is not None else None
        except Exception:
            resolution = None

        return ExhaustiveMapSnapshot(
            image=image,
            map_data=map_data,
            transformer=None,
            map_name=str(slot),
            crypto_mode="Xiaomi JSON · AES-CBC · hex-str exacto",
            raw_size=len(raw),
            envelope_version="xiaomi-json-v43",
            map_id=map_id,
            resolution=resolution,
            raw_robot=robot,
            raw_base=base,
            raw_path=path,
            parser_error=parser_error,
            slot=str(slot),
            endpoint=endpoint,
            decrypted_size=len(decrypted.encode("utf-8")) if isinstance(decrypted, str) else 0,
            raw_prefix_hex=bytes(raw[:24]).hex(),
            blob_sha256=hashlib.sha256(raw).hexdigest(),
            blob_kind=blob_label,
            wifi_sn_source="no usado por Xiaomi JSON",
            wifi_sn_length=0,
            mac_source="no usada por Xiaomi JSON",
            mac_available=False,
            owner_source="no usado por Xiaomi JSON",
            did_source="settings.did",
            pose_id=None,
            upload_date=None,
            decode_attempts=0,
            candidate_counts={},
        )

    # -------------------------------------------------------------- descifrado
    def _decode_xiaomi(self, raw, slot, endpoint):
        blob_variants = self._xiaomi_blob_variants(raw)
        key_candidates = self._model_key_candidates()
        attempts = decrypt_ok = json_ok = parse_ok = 0
        last_decrypt_error = None
        last_json_error = None
        last_parse_error = None

        for blob, blob_label in blob_variants:
            # CRÍTICO: unpack_map espera el ciphertext como string hexadecimal.
            encrypted_hex = blob.hex()
            for model_key, key_label in key_candidates:
                attempts += 1
                parser = XiaomiMapDataParser(
                    ColorsPalette(), Sizes(), self.XIAOMI_DRAWABLES, ImageConfig(), []
                )
                try:
                    decrypted = parser.unpack_map(
                        encrypted_hex,
                        model=model_key,
                        device_id=str(self.did),
                    )
                    decrypt_ok += 1
                except Exception as exc:
                    last_decrypt_error = type(exc).__name__ + ": " + (str(exc).strip() or "sin detalle")[:120]
                    continue

                try:
                    payload = json.loads(decrypted) if isinstance(decrypted, str) else decrypted
                    if not self._valid_xiaomi_payload(payload):
                        raise ValueError("JSON sin campos de mapa/posición")
                    json_ok += 1
                except Exception as exc:
                    last_json_error = type(exc).__name__ + ": " + (str(exc).strip() or "sin detalle")[:120]
                    continue

                map_data = None
                try:
                    map_data = parser.parse(payload)
                    parse_ok += 1
                except Exception as exc:
                    # Posición/base/path del JSON siguen siendo utilizables aunque
                    # el renderer falle por una peculiaridad visual del firmware.
                    last_parse_error = type(exc).__name__ + ": " + (str(exc).strip() or "sin detalle")[:160]

                snapshot = self._snapshot_xiaomi(
                    raw, blob, slot, endpoint, decrypted, payload, map_data, key_label, blob_label
                )
                useful = bool(snapshot.raw_robot or snapshot.raw_base or snapshot.raw_path or snapshot.image is not None)
                # Un mapa sin pose puede ser válido al principio; width/height/map_data
                # también sirven como validación estructural fuerte.
                if useful or all(k in payload for k in ("width", "height", "map_data")):
                    diag = {
                        "attempts": attempts,
                        "decrypt_ok": decrypt_ok,
                        "json_ok": json_ok,
                        "parse_ok": parse_ok,
                        "winner": True,
                        "winner_model_key": key_label,
                        "winner_blob_variant": blob_label,
                        "decrypted_sha12": hashlib.sha256(decrypted.encode("utf-8")).hexdigest()[:12],
                        "decrypted_bytes": len(decrypted.encode("utf-8")),
                        "robot": snapshot.raw_robot,
                        "base": snapshot.raw_base,
                        "path_count": len(snapshot.raw_path or []),
                        "image": bool(snapshot.image is not None),
                        "map_id": snapshot.map_id,
                        "resolution": snapshot.resolution,
                        "payload_keys": sorted(str(k) for k in payload.keys())[:32],
                        "last_parse_error": last_parse_error,
                    }
                    snapshot.decode_attempts = attempts
                    return snapshot, diag

        return None, {
            "attempts": attempts,
            "decrypt_ok": decrypt_ok,
            "json_ok": json_ok,
            "parse_ok": parse_ok,
            "winner": False,
            "model_key_candidates": [label for _, label in key_candidates],
            "blob_variants": [label for _, label in blob_variants],
            "last_decrypt_error": last_decrypt_error,
            "last_json_error": last_json_error,
            "last_parse_error": last_parse_error,
        }

    # --------------------------------------------------------------- descarga
    def load(self):
        slot_diag = {}
        errors = {}
        total_attempts = total_decrypt_ok = total_json_ok = total_parse_ok = 0

        for slot in self.CLOUD_SLOTS:
            try:
                url, endpoint = self._map_download_url(slot)
                response = requests.get(url, timeout=30)
                raw = bytes(response.content or b"")
                status = int(response.status_code)
                slot_diag[str(slot)] = {
                    "http": status,
                    "bytes": len(raw),
                    "sha12": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
                    "endpoint": endpoint,
                }
                response.raise_for_status()

                snapshot, diag = self._decode_xiaomi(raw, str(slot), endpoint)
                total_attempts += int(diag.get("attempts", 0) or 0)
                total_decrypt_ok += int(diag.get("decrypt_ok", 0) or 0)
                total_json_ok += int(diag.get("json_ok", 0) or 0)
                total_parse_ok += int(diag.get("parse_ok", 0) or 0)
                slot_diag[str(slot)]["xiaomi"] = {
                    "attempts": diag.get("attempts", 0),
                    "decrypt_ok": diag.get("decrypt_ok", 0),
                    "json_ok": diag.get("json_ok", 0),
                    "parse_ok": diag.get("parse_ok", 0),
                    "winner": diag.get("winner", False),
                    "model_key": diag.get("winner_model_key"),
                    "blob_variant": diag.get("winner_blob_variant"),
                    "last_decrypt_error": diag.get("last_decrypt_error"),
                    "last_json_error": diag.get("last_json_error"),
                    "last_parse_error": diag.get("last_parse_error"),
                }
                if snapshot is not None:
                    snapshot.valid_slots = [str(slot)]
                    snapshot.slot_errors = errors
                    self.last_slot_diagnostics = slot_diag
                    self.last_xiaomi_diagnostics = {
                        **diag,
                        "attempts": total_attempts,
                        "decrypt_ok": total_decrypt_ok,
                        "json_ok": total_json_ok,
                        "parse_ok": total_parse_ok,
                        "slots": slot_diag,
                        "errors": errors,
                        "route": "Xiaomi JSON",
                    }
                    self.decode_attempts = total_attempts
                    return snapshot
            except Exception as exc:
                errors[str(slot)] = self._safe_http_error(exc)

        self.last_xiaomi_diagnostics = {
            "attempts": total_attempts,
            "decrypt_ok": total_decrypt_ok,
            "json_ok": total_json_ok,
            "parse_ok": total_parse_ok,
            "winner": False,
            "slots": slot_diag,
            "errors": errors,
            "route": "Xiaomi JSON falló; probando IJAI",
            "model_key_candidates": [label for _, label in self._model_key_candidates()],
        }

        # No eliminamos ninguna ruta previa: si este firmware concreto fuese IJAI,
        # V42/V41 siguen disponibles como fallback automático.
        try:
            snapshot = super().load()
            self.last_xiaomi_diagnostics["fallback_ijai"] = "OK"
            return snapshot
        except Exception as exc:
            self.last_xiaomi_diagnostics["fallback_ijai"] = self._safe_http_error(exc)
            raise RuntimeError(
                "No pude abrir el mapa ni como Xiaomi JSON ni como IJAI. "
                f"Xiaomi: {total_attempts} intentos, decrypt={total_decrypt_ok}, json={total_json_ok}, parse={total_parse_ok}. "
                f"IJAI: {self.last_xiaomi_diagnostics['fallback_ijai']}"
            ) from exc

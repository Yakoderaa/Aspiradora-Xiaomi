import base64
import hashlib
import json
import re
from typing import Any

import requests
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.drawable import Drawable
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41 import ExhaustiveMapSnapshot, XiaomiE10MapV41


class XiaomiE10MapV42(XiaomiE10MapV41):
    """v42: usa el formato binario IJAI real que consume el parser 0.1.1.

    V41 podía derivar correctamente una clave y aun así descartar el mapa porque
    validaba el resultado como ``RobotMap_pb2``. El paquete
    ``vacuum-map-parser-ijai`` que usamos en producción hace otra cosa: primero
    ``unpack_map()`` (AES-ECB -> hex -> zlib) y después ``parse()`` sobre su
    formato binario propio. Esta clase prueba exactamente esa ruta publicada y
    sólo conserva V41 como último fallback.
    """

    NATIVE_DRAWABLES = [
        Drawable.PATH,
        Drawable.CHARGER,
        Drawable.VACUUM_POSITION,
        Drawable.ROOM_NAMES,
        Drawable.NO_GO_AREAS,
        Drawable.VIRTUAL_WALLS,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_native_diagnostics: dict[str, Any] = {}

    # --------------------------------------------------------- material clave
    @staticmethod
    def _strict_wifi_serial(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        return 16 <= len(text) <= 24 and text.isupper()

    @classmethod
    def _wifi_priority(cls, item):
        value, source = item
        source = str(source)
        exact_order = {
            "LAN 1/5": 0,
            "LAN 1/3": 1,
            "LAN 7/45": 2,
            "Cloud 1/5": 3,
            "Cloud 1/3": 4,
            "Cloud 7/45": 5,
        }
        strict = cls._strict_wifi_serial(str(value))
        return (0 if strict else 1, exact_order.get(source, 50), source)

    @staticmethod
    def _owner_priority(item):
        _, source = item
        order = {
            "session.user_id": 0,
            "UID sufijo 7/45": 1,
            "Cloud UID sufijo 7/45": 2,
            "session.cuser_id": 3,
        }
        return (order.get(str(source), 20), str(source))

    def _ordered_key_material(self):
        wifi, owners, dids, macs = self._key_candidates()
        wifi = sorted(wifi, key=self._wifi_priority)
        owners = sorted(owners, key=self._owner_priority)
        # No descartamos los candidatos laxos: quedan al final como fallback.
        self.last_key_diagnostics["strict_wifi_count"] = sum(
            1 for value, _ in wifi if self._strict_wifi_serial(str(value))
        )
        self.last_key_diagnostics["ordered_wifi_sources"] = [source for _, source in wifi]
        return wifi, owners, dids, macs

    # -------------------------------------------------------- blob codificado
    @staticmethod
    def _encoded_variants(raw: bytes):
        """Devuelve representaciones que ``IjaiMapDataParser.unpack_map`` acepta.

        El decryptor IJAI espera texto Base64. Xiaomi normalmente ya entrega ese
        texto, pero algunos proxies/backend wrappers pueden entregar JSON, hex o
        directamente el ciphertext binario.
        """
        result = []
        seen = set()

        def add(data, label):
            if isinstance(data, str):
                data = data.encode("utf-8")
            if not isinstance(data, (bytes, bytearray, memoryview)):
                return
            data = bytes(data).strip()
            if not data or data in seen:
                return
            seen.add(data)
            result.append((data, label))

        add(raw, "raw")
        stripped = bytes(raw or b"").strip()
        try:
            wrapped = json.loads(stripped)
            if isinstance(wrapped, str):
                add(wrapped, "json-string")
            elif isinstance(wrapped, dict):
                for key in ("data", "content", "map", "payload"):
                    value = wrapped.get(key)
                    if isinstance(value, str) and value:
                        add(value, f"json.{key}")
        except Exception:
            pass

        # Expandimos sólo a formas Base64 válidas para el decryptor del parser.
        for data, label in list(result):
            try:
                text = data.decode("ascii").strip()
            except Exception:
                text = ""
            compact = re.sub(r"\s+", "", text) if text else ""
            if compact and len(compact) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", compact):
                try:
                    add(base64.b64encode(bytes.fromhex(compact)), label + " hex->b64")
                except Exception:
                    pass
            # Si ya parece Base64 lo dejamos tal cual. Si es binario alineado a
            # AES, lo envolvemos en Base64 para respetar el contrato upstream.
            looks_b64 = bool(compact and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact))
            if not looks_b64 and len(data) >= 16 and len(data) % 16 == 0:
                add(base64.b64encode(data), label + " bin->b64")
        return result

    # ------------------------------------------------------------- extracción
    @staticmethod
    def _xy(value):
        if value is None:
            return None
        try:
            return float(value.x), float(value.y)
        except Exception:
            pass
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
    def _path_points(cls, map_data):
        path_obj = getattr(map_data, "path", None)
        if path_obj is None:
            return []
        candidates = getattr(path_obj, "path", None)
        if candidates is None:
            candidates = path_obj if isinstance(path_obj, (list, tuple)) else []
        points = []
        try:
            outer = list(candidates or [])
        except Exception:
            outer = []
        for item in outer:
            xy = cls._xy(item)
            if xy is not None:
                points.append(xy)
                continue
            try:
                nested = list(item or [])
            except Exception:
                nested = []
            for point in nested:
                xy = cls._xy(point)
                if xy is not None:
                    points.append(xy)
        return points

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

    @classmethod
    def _map_data_quality(cls, map_data):
        robot = cls._xy(getattr(map_data, "vacuum_position", None))
        base = cls._xy(getattr(map_data, "charger", None))
        path = cls._path_points(map_data)
        image = cls._image_from_map_data(map_data)
        rooms = getattr(map_data, "rooms", None)
        score = 1
        if robot is not None:
            score += 8
        if base is not None:
            score += 5
        if path:
            score += min(10, 2 + len(path))
        if image is not None:
            score += 5
        try:
            if rooms:
                score += 2
        except Exception:
            pass
        return score, robot, base, path, image

    def _native_snapshot(self, *, raw, slot, endpoint, unpacked, map_data, label, sources):
        score, robot, base, path, image = self._map_data_quality(map_data)
        map_id = None
        resolution = None
        for attr in ("map_id", "map_index", "map_index_id"):
            value = getattr(map_data, attr, None)
            if value is not None:
                try:
                    map_id = int(value)
                    break
                except Exception:
                    pass

        return score, ExhaustiveMapSnapshot(
            image=image,
            map_data=map_data,
            transformer=None,
            map_name=str(slot),
            crypto_mode="IJAI nativo · parser.unpack_map + parser.parse",
            raw_size=len(raw),
            envelope_version="ijai-binary-native",
            map_id=map_id,
            resolution=resolution,
            raw_robot=robot,
            raw_base=base,
            raw_path=path,
            parser_error=None,
            slot=str(slot),
            endpoint=endpoint,
            decrypted_size=len(unpacked),
            raw_prefix_hex=bytes(raw[:24]).hex(),
            blob_sha256=hashlib.sha256(raw).hexdigest(),
            blob_kind=label,
            wifi_sn_source=sources.get("wifi_source", ""),
            wifi_sn_length=int(sources.get("wifi_len", 0) or 0),
            mac_source=sources.get("mac_source", ""),
            mac_available=bool(sources.get("mac_source")),
            owner_source=sources.get("owner_source", ""),
            did_source=sources.get("did_source", ""),
            pose_id=None,
            upload_date=None,
            decode_attempts=int(self.last_native_diagnostics.get("attempts", 0) or 0),
            candidate_counts={k: int(v) for k, v in self.last_key_diagnostics.items() if k.endswith("_count")},
        )

    # ----------------------------------------------------------- parser nativo
    def _decode_native(self, raw, wifi, owners, dids, macs, slot, endpoint):
        variants = self._encoded_variants(raw)
        attempts = 0
        unpack_ok = 0
        parse_ok = 0
        best = None
        last_unpack_error = None
        last_parse_error = None

        for wifi_sn, wifi_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    for mac, mac_source in macs:
                        for encoded, label in variants:
                            attempts += 1
                            parser = IjaiMapDataParser(
                                ColorsPalette(), Sizes(), self.NATIVE_DRAWABLES, ImageConfig(), []
                            )
                            try:
                                unpacked = parser.unpack_map(
                                    encoded,
                                    wifi_sn=str(wifi_sn),
                                    owner_id=str(owner),
                                    device_id=str(did),
                                    model=MODEL,
                                    device_mac=str(mac),
                                )
                                unpack_ok += 1
                            except Exception as exc:
                                last_unpack_error = type(exc).__name__
                                continue

                            unpack_hash = hashlib.sha256(bytes(unpacked)).hexdigest()[:12]
                            try:
                                map_data = parser.parse(unpacked)
                                parse_ok += 1
                            except Exception as exc:
                                last_parse_error = type(exc).__name__
                                continue

                            sources = {
                                "wifi_source": wifi_source,
                                "wifi_len": len(str(wifi_sn)),
                                "owner_source": owner_source,
                                "did_source": did_source,
                                "mac_source": mac_source,
                            }
                            score, snapshot = self._native_snapshot(
                                raw=raw,
                                slot=slot,
                                endpoint=endpoint,
                                unpacked=unpacked,
                                map_data=map_data,
                                label=label,
                                sources=sources,
                            )
                            candidate = (score, snapshot, unpack_hash, sources, label)
                            if best is None or score > best[0]:
                                best = candidate
                            # Robot/base/path es suficiente para el objetivo en
                            # vivo; no tiene sentido seguir probando claves una
                            # vez que el parser validó contenido útil.
                            if score >= 6:
                                break
                        if best is not None and best[0] >= 6:
                            break
                    if best is not None and best[0] >= 6:
                        break
                if best is not None and best[0] >= 6:
                    break
            if best is not None and best[0] >= 6:
                break

        diag = {
            "attempts": attempts,
            "encoded_variants": [label for _, label in variants],
            "unpack_ok": unpack_ok,
            "parse_ok": parse_ok,
            "last_unpack_error": last_unpack_error,
            "last_parse_error": last_parse_error,
        }
        if best is not None:
            diag.update({
                "score": best[0],
                "unpacked_sha12": best[2],
                "winner_sources": best[3],
                "winner_blob_variant": best[4],
                "robot": best[1].raw_robot,
                "base": best[1].raw_base,
                "path_count": len(best[1].raw_path or []),
                "image": bool(best[1].image is not None),
                "decrypted_bytes": int(best[1].decrypted_size or 0),
            })
        return (best[1] if best is not None else None), diag

    @staticmethod
    def _safe_http_error(exc):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if status is not None:
            return f"HTTP {int(status)}"
        text = str(exc).strip() or type(exc).__name__
        # Nunca volcamos URLs firmadas de FDS en Diagnóstico.
        text = re.sub(r"https?://\S+", "<URL omitida>", text)
        return text[:240]

    def load(self):
        wifi, owners, dids, macs = self._ordered_key_material()
        self.last_key_diagnostics["derived_key_count"] = len(self._derive_keys(wifi, owners, dids, macs))

        slot_diag = {}
        errors = {}
        best = None
        total_attempts = total_unpack_ok = total_parse_ok = 0

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

                snapshot, diag = self._decode_native(
                    raw, wifi, owners, dids, macs, str(slot), endpoint
                )
                total_attempts += int(diag.get("attempts", 0) or 0)
                total_unpack_ok += int(diag.get("unpack_ok", 0) or 0)
                total_parse_ok += int(diag.get("parse_ok", 0) or 0)
                slot_diag[str(slot)]["native"] = {
                    "attempts": diag.get("attempts", 0),
                    "unpack_ok": diag.get("unpack_ok", 0),
                    "parse_ok": diag.get("parse_ok", 0),
                    "score": diag.get("score"),
                    "unpacked_sha12": diag.get("unpacked_sha12"),
                    "variant": diag.get("winner_blob_variant"),
                    "last_unpack_error": diag.get("last_unpack_error"),
                    "last_parse_error": diag.get("last_parse_error"),
                }
                if snapshot is not None:
                    score = int(diag.get("score", 0) or 0)
                    if best is None or score > best[0]:
                        best = (score, snapshot, diag)
            except Exception as exc:
                errors[str(slot)] = self._safe_http_error(exc)

        self.last_slot_diagnostics = slot_diag
        self.last_native_diagnostics = {
            "attempts": total_attempts,
            "unpack_ok": total_unpack_ok,
            "parse_ok": total_parse_ok,
            "slots": slot_diag,
            "errors": errors,
            "strict_wifi_count": self.last_key_diagnostics.get("strict_wifi_count", 0),
        }

        if best is not None:
            _, selected, winning_diag = best
            selected.valid_slots = [selected.slot]
            selected.slot_errors = errors
            self.last_native_diagnostics.update({
                "winner": True,
                "winner_sources": winning_diag.get("winner_sources") or {},
                "winner_blob_variant": winning_diag.get("winner_blob_variant"),
                "unpacked_sha12": winning_diag.get("unpacked_sha12"),
                "decrypted_bytes": winning_diag.get("decrypted_bytes", 0),
                "robot": winning_diag.get("robot"),
                "base": winning_diag.get("base"),
                "path_count": winning_diag.get("path_count", 0),
                "image": winning_diag.get("image", False),
            })
            self.decode_attempts = total_attempts
            return selected

        # Último recurso: mantenemos todas las variantes de V41. Si tampoco
        # funcionan, devolvemos un error compacto y sin URL firmada.
        legacy_error = None
        try:
            fallback = super().load()
            self.last_native_diagnostics["legacy_fallback"] = "OK"
            return fallback
        except Exception as exc:
            legacy_error = self._safe_http_error(exc)
            self.last_native_diagnostics["legacy_fallback"] = legacy_error

        self.decode_attempts = total_attempts
        details = ", ".join(f"slot {slot}: {error}" for slot, error in errors.items()) or "sin error HTTP"
        raise RuntimeError(
            "IJAI nativo no produjo un mapa utilizable "
            f"({total_attempts} intentos, unpack correctos={total_unpack_ok}, parse correctos={total_parse_ok}); "
            f"{details}. Fallback V41: {legacy_error or 'sin resultado'}"
        )

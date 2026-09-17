import base64
import hashlib
import json
import re
from typing import Any

import requests
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41 import XiaomiE10MapV41


class XiaomiE10MapV42(XiaomiE10MapV41):
    """v42: descifra el B112 con el propio parser IJAI 0.1.1.

    El hallazgo importante frente a V41 está en la derivación final de clave.
    ``xiaomi.vacuum.b112`` NO pertenece a los modelos que usan el MD5 completo
    interpretado como hexadecimal. El paquete 0.1.1 usa los 16 caracteres
    centrales del MD5, en mayúsculas, como clave AES ASCII. V41 no probaba esa
    variante y por eso podía descargar el blob correcto pero no abrirlo.

    Después de ``unpack_map`` validamos el protobuf directamente para no perder
    una decodificación correcta si el renderer de habitaciones de la librería
    falla. El render visual queda como best-effort; posición/base/historyPose no.
    """

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
        self.last_key_diagnostics["strict_wifi_count"] = sum(
            1 for value, _ in wifi if self._strict_wifi_serial(str(value))
        )
        self.last_key_diagnostics["ordered_wifi_sources"] = [source for _, source in wifi]
        return wifi, owners, dids, macs

    # -------------------------------------------------------- blob codificado
    @staticmethod
    def _encoded_variants(raw: bytes):
        """Genera entradas compatibles con ``IjaiMapDataParser.unpack_map``."""
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
            looks_b64 = bool(compact and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact))
            if not looks_b64 and len(data) >= 16 and len(data) % 16 == 0:
                add(base64.b64encode(data), label + " bin->b64")
        return result

    # ---------------------------------------------------- helpers de diagnóstico
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
        """Extractor tolerante, conservado para tests y formatos MapData."""
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
    def _safe_http_error(exc):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if status is not None:
            return f"HTTP {int(status)}"
        text = str(exc).strip() or type(exc).__name__
        text = re.sub(r"https?://\S+", "<URL omitida>", text)
        return text[:240]

    # ----------------------------------------------------------- parser nativo
    def _decode_native(self, raw, wifi, owners, dids, macs, slot, endpoint):
        variants = self._encoded_variants(raw)
        attempts = 0
        unpack_ok = 0
        protobuf_ok = 0
        render_ok = 0
        last_unpack_error = None
        last_validation_error = None
        last_render_error = None

        for wifi_sn, wifi_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    for mac, mac_source in macs:
                        for encoded, label in variants:
                            attempts += 1
                            parser = IjaiMapDataParser(
                                ColorsPalette(), Sizes(), [], ImageConfig(), []
                            )
                            try:
                                # Ruta exacta del paquete 0.1.1. En B112 aplica
                                # internamente MD5[8:-8].upper() como AES ASCII.
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

                            quality = self._protobuf_quality(unpacked)
                            if not quality:
                                last_validation_error = "protobuf-no-coherente"
                                continue
                            protobuf_ok += 1
                            score, robot_map = quality

                            sources = {
                                "wifi_source": wifi_source,
                                "wifi_len": len(str(wifi_sn)),
                                "owner_source": owner_source,
                                "did_source": did_source,
                                "mac_source": mac_source,
                            }
                            # Extrae pose/base/history antes del renderer; un bug
                            # de rooms/imagen no puede invalidar el movimiento.
                            snapshot = self._snapshot_from_payload(
                                str(slot), endpoint, raw, unpacked, robot_map,
                                "IJAI 0.1.1 · clave B112 ASCII-MD5 central",
                                "parser nativo",
                                sources,
                            )
                            if not snapshot.parser_error:
                                render_ok += 1
                            else:
                                last_render_error = snapshot.parser_error[:180]

                            snapshot.blob_kind = label
                            snapshot.decode_attempts = attempts
                            snapshot.crypto_mode = "IJAI 0.1.1 · unpack_map exacto · B112 ASCII-MD5 central"

                            diag = {
                                "attempts": attempts,
                                "encoded_variants": [name for _, name in variants],
                                "unpack_ok": unpack_ok,
                                "protobuf_ok": protobuf_ok,
                                "parse_ok": render_ok,
                                "last_unpack_error": last_unpack_error,
                                "last_validation_error": last_validation_error,
                                "last_render_error": last_render_error,
                                "score": int(score),
                                "unpacked_sha12": hashlib.sha256(bytes(unpacked)).hexdigest()[:12],
                                "winner_sources": sources,
                                "winner_blob_variant": label,
                                "robot": snapshot.raw_robot,
                                "base": snapshot.raw_base,
                                "path_count": len(snapshot.raw_path or []),
                                "image": bool(snapshot.image is not None),
                                "decrypted_bytes": len(unpacked),
                            }
                            return snapshot, diag

        return None, {
            "attempts": attempts,
            "encoded_variants": [name for _, name in variants],
            "unpack_ok": unpack_ok,
            "protobuf_ok": protobuf_ok,
            "parse_ok": render_ok,
            "last_unpack_error": last_unpack_error,
            "last_validation_error": last_validation_error,
            "last_render_error": last_render_error,
        }

    # --------------------------------------------------------------- descarga
    def load(self):
        wifi, owners, dids, macs = self._ordered_key_material()
        # Métrica comparativa con V41. V42 NO usa estas claves reimplementadas.
        self.last_key_diagnostics["derived_key_count"] = len(self._derive_keys(wifi, owners, dids, macs))

        slot_diag = {}
        errors = {}
        best = None
        total_attempts = total_unpack_ok = total_protobuf_ok = total_parse_ok = 0

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
                total_protobuf_ok += int(diag.get("protobuf_ok", 0) or 0)
                total_parse_ok += int(diag.get("parse_ok", 0) or 0)
                slot_diag[str(slot)]["native"] = {
                    "attempts": diag.get("attempts", 0),
                    "unpack_ok": diag.get("unpack_ok", 0),
                    "protobuf_ok": diag.get("protobuf_ok", 0),
                    "parse_ok": diag.get("parse_ok", 0),
                    "score": diag.get("score"),
                    "unpacked_sha12": diag.get("unpacked_sha12"),
                    "variant": diag.get("winner_blob_variant"),
                    "last_unpack_error": diag.get("last_unpack_error"),
                    "last_validation_error": diag.get("last_validation_error"),
                    "last_render_error": diag.get("last_render_error"),
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
            "protobuf_ok": total_protobuf_ok,
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
                "renderer_error": winning_diag.get("last_render_error"),
            })
            self.decode_attempts = total_attempts
            return selected

        # Último recurso: variantes antiguas de V41, con error saneado.
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
            "IJAI 0.1.1 no produjo un mapa utilizable "
            f"({total_attempts} intentos, unpack={total_unpack_ok}, protobuf={total_protobuf_ok}, render={total_parse_ok}); "
            f"{details}. Fallback V41: {legacy_error or 'sin resultado'}"
        )

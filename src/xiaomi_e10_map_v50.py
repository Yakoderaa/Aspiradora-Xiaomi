import base64
import hashlib
import json
import re
from typing import Any

from xiaomi_e10_map_v44 import XiaomiE10MapV44


class XiaomiE10MapV50(XiaomiE10MapV44):
    """V50: conserva el payload directo de get_interim_file_url_pro.

    Xiaomi Cloud puede responder a ``get_interim_file_url_pro`` con el contenido
    del mapa (o un envelope que lo contiene) en vez de devolver una URL firmada.
    V41-V49 sólo aceptaban ``result.url`` y descartaban cualquier otro resultado,
    por lo que esa ruta quedaba invisible y se terminaba usando el endpoint
    clásico. V50 inspecciona de forma segura la respuesta _pro, extrae candidatos
    binarios/base64/hex y los prueba con los decoders IJAI y Xiaomi ya existentes.

    El diagnóstico nunca publica el payload, URL firmada ni identificadores: sólo
    forma, tamaño, hashes cortos y contadores de los parsers.
    """

    def __init__(self, *args, **kwargs):
        self.last_v50_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    @staticmethod
    def _strip_cloud_prefix(text: str) -> str:
        text = str(text or "").lstrip("\ufeff \t\r\n")
        prefix = "&&&START&&&"
        return text[len(prefix):] if text.startswith(prefix) else text

    @staticmethod
    def _looks_base64(text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or ""))
        if len(compact) < 16 or len(compact) % 4 == 1:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact))

    @staticmethod
    def _looks_hex(text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or ""))
        return bool(len(compact) >= 32 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", compact))

    @staticmethod
    def _magic_label(data: bytes) -> str:
        raw = bytes(data or b"")
        if raw.startswith(b"\x1f\x8b"):
            return "gzip"
        if raw.startswith(b"PK\x03\x04"):
            return "zip"
        if raw.startswith((b"{", b"[")):
            return "json/text"
        if len(raw) >= 2 and raw[0] == 0x78 and raw[1] in (0x01, 0x5E, 0x9C, 0xDA):
            return "zlib"
        if raw:
            printable = sum(1 for b in raw[:128] if 32 <= b < 127)
            if printable >= max(1, int(min(len(raw), 128) * 0.90)):
                return "ascii"
        return "binary"

    @classmethod
    def _candidate_meta(cls, data: bytes, label: str) -> dict[str, Any]:
        raw = bytes(data or b"")
        return {
            "label": str(label),
            "bytes": len(raw),
            "sha12": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
            "prefix_hex": raw[:16].hex(),
            "block16": bool(raw and len(raw) % 16 == 0),
            "magic": cls._magic_label(raw),
        }

    def _pro_payload_candidates(self, response: Any):
        """Devuelve (diagnóstico seguro, candidatos binarios) de una respuesta _pro."""
        diag: dict[str, Any] = {
            "response_kind": type(response).__name__,
            "parsed_kind": None,
            "version": None,
            "url_present": False,
            "candidate_count": 0,
            "candidates": [],
            "error": None,
        }
        candidates: list[tuple[bytes, str]] = []
        seen: set[bytes] = set()

        def add_bytes(data: Any, label: str):
            if isinstance(data, str):
                data = data.encode("utf-8", "replace")
            if not isinstance(data, (bytes, bytearray, memoryview)):
                return
            raw = bytes(data).strip()
            if not raw or raw in seen:
                return
            seen.add(raw)
            candidates.append((raw, label))

        def add_text(text: str, label: str):
            text = self._strip_cloud_prefix(text).strip()
            if not text:
                return
            if text.lower().startswith(("http://", "https://")):
                diag["url_present"] = True
                return

            # Conservamos el texto original porque el parser IJAI acepta base64.
            add_bytes(text.encode("utf-8"), label + ":text")
            compact = re.sub(r"\s+", "", text)

            if self._looks_base64(compact):
                padded = compact + "=" * ((4 - len(compact) % 4) % 4)
                for decoder, suffix in (
                    (base64.b64decode, "base64"),
                    (base64.urlsafe_b64decode, "base64url"),
                ):
                    try:
                        decoded = decoder(padded.encode("ascii"))
                        if decoded:
                            add_bytes(decoded, label + ":" + suffix)
                            break
                    except Exception:
                        pass

            if self._looks_hex(compact):
                try:
                    add_bytes(bytes.fromhex(compact), label + ":hex")
                except Exception:
                    pass

        def walk(value: Any, label: str, depth: int = 0):
            if depth > 3 or value is None:
                return
            if isinstance(value, (bytes, bytearray, memoryview)):
                raw = bytes(value)
                try:
                    text = raw.decode("utf-8-sig")
                except Exception:
                    add_bytes(raw, label + ":bytes")
                    return
                walk(text, label, depth + 1)
                return
            if isinstance(value, str):
                text = self._strip_cloud_prefix(value).strip()
                try:
                    parsed = json.loads(text)
                except Exception:
                    add_text(text, label)
                    return
                diag["parsed_kind"] = type(parsed).__name__
                walk(parsed, label + ":json", depth + 1)
                return
            if isinstance(value, dict):
                if value.get("version") is not None and diag.get("version") is None:
                    diag["version"] = value.get("version")
                for key in ("url", "file_url", "download_url"):
                    if value.get(key):
                        diag["url_present"] = True
                # Xiaomi ha usado result directo y envelopes data/content/map/payload.
                for key in ("result", "data", "content", "map", "payload"):
                    if key in value:
                        walk(value.get(key), label + "." + key, depth + 1)
                return
            if isinstance(value, (list, tuple)):
                for index, item in enumerate(value[:8]):
                    walk(item, f"{label}[{index}]", depth + 1)

        try:
            walk(response, "response")
        except Exception as exc:
            diag["error"] = type(exc).__name__ + ": " + (str(exc).strip() or "sin detalle")[:160]

        diag["candidate_count"] = len(candidates)
        diag["candidates"] = [self._candidate_meta(raw, label) for raw, label in candidates[:12]]
        return diag, candidates

    def _probe_pro_slot(self, slot: str):
        user_id = str(self.session_data.get("user_id") or "")
        obj_name = f"{user_id}/{self.did}/{slot}"
        params = {"data": json.dumps({"obj_name": obj_name}, separators=(",", ":"))}
        try:
            response = self._cloud().request_country(
                "/v2/home/get_interim_file_url_pro",
                self.region,
                params,
            )
            diag, candidates = self._pro_payload_candidates(response)
            diag["ok"] = True
            return diag, candidates
        except Exception as exc:
            return {
                "ok": False,
                "response_kind": None,
                "parsed_kind": None,
                "version": None,
                "url_present": False,
                "candidate_count": 0,
                "candidates": [],
                "error": self._safe_http_error(exc),
            }, []

    def load(self):
        # Usa exactamente los candidatos de clave que V44 ya verificó para IJAI.
        wifi, owners, dids, macs = self._ordered_key_material()
        pro_slots: dict[str, Any] = {}
        native_attempts = native_unpack = native_protobuf = 0
        xiaomi_attempts = xiaomi_decrypt = xiaomi_json = 0

        self.last_v50_diagnostics = {
            "route": "probando get_interim_file_url_pro directo",
            "pro_slots": pro_slots,
            "success": False,
            "fallback_classic": False,
        }

        for slot in self.CLOUD_SLOTS:
            slot_name = str(slot)
            slot_diag, candidates = self._probe_pro_slot(slot_name)
            slot_diag["decoder_trials"] = []
            pro_slots[slot_name] = slot_diag

            for raw, label in candidates:
                native_snapshot, native_diag = self._decode_native(
                    raw,
                    wifi,
                    owners,
                    dids,
                    macs,
                    slot_name,
                    "get_interim_file_url_pro/direct",
                )
                native_attempts += int(native_diag.get("attempts", 0) or 0)
                native_unpack += int(native_diag.get("unpack_ok", 0) or 0)
                native_protobuf += int(native_diag.get("protobuf_ok", 0) or 0)
                slot_diag["decoder_trials"].append({
                    "candidate": label,
                    "decoder": "ijai",
                    "attempts": int(native_diag.get("attempts", 0) or 0),
                    "unpack_ok": int(native_diag.get("unpack_ok", 0) or 0),
                    "protobuf_ok": int(native_diag.get("protobuf_ok", 0) or 0),
                })
                if native_snapshot is not None:
                    native_snapshot.blob_kind = label
                    self.last_v50_diagnostics.update({
                        "route": "get_interim_file_url_pro directo -> IJAI",
                        "success": True,
                        "winner_slot": slot_name,
                        "winner_candidate": label,
                        "winner_decoder": "ijai",
                        "native_attempts": native_attempts,
                        "native_unpack_ok": native_unpack,
                        "native_protobuf_ok": native_protobuf,
                        "xiaomi_attempts": xiaomi_attempts,
                        "xiaomi_decrypt_ok": xiaomi_decrypt,
                        "xiaomi_json_ok": xiaomi_json,
                    })
                    return self._mark_success(native_snapshot, "V50 _pro directo -> IJAI")

                xiaomi_snapshot, xiaomi_diag = self._decode_xiaomi(
                    raw,
                    slot_name,
                    "get_interim_file_url_pro/direct",
                )
                xiaomi_attempts += int(xiaomi_diag.get("attempts", 0) or 0)
                xiaomi_decrypt += int(xiaomi_diag.get("decrypt_ok", 0) or 0)
                xiaomi_json += int(xiaomi_diag.get("json_ok", 0) or 0)
                slot_diag["decoder_trials"].append({
                    "candidate": label,
                    "decoder": "xiaomi-json",
                    "attempts": int(xiaomi_diag.get("attempts", 0) or 0),
                    "decrypt_ok": int(xiaomi_diag.get("decrypt_ok", 0) or 0),
                    "json_ok": int(xiaomi_diag.get("json_ok", 0) or 0),
                })
                if xiaomi_snapshot is not None:
                    xiaomi_snapshot.blob_kind = label
                    self.last_v50_diagnostics.update({
                        "route": "get_interim_file_url_pro directo -> Xiaomi JSON",
                        "success": True,
                        "winner_slot": slot_name,
                        "winner_candidate": label,
                        "winner_decoder": "xiaomi-json",
                        "native_attempts": native_attempts,
                        "native_unpack_ok": native_unpack,
                        "native_protobuf_ok": native_protobuf,
                        "xiaomi_attempts": xiaomi_attempts,
                        "xiaomi_decrypt_ok": xiaomi_decrypt,
                        "xiaomi_json_ok": xiaomi_json,
                    })
                    return self._mark_success(xiaomi_snapshot, "V50 _pro directo -> Xiaomi JSON")

        self.last_v50_diagnostics.update({
            "native_attempts": native_attempts,
            "native_unpack_ok": native_unpack,
            "native_protobuf_ok": native_protobuf,
            "xiaomi_attempts": xiaomi_attempts,
            "xiaomi_decrypt_ok": xiaomi_decrypt,
            "xiaomi_json_ok": xiaomi_json,
            "fallback_classic": True,
            "route": "_pro directo sin mapa válido; fallback V44 clásico",
        })

        try:
            snapshot = super().load()
            self.last_v50_diagnostics["fallback_result"] = "OK"
            return snapshot
        except Exception as exc:
            self.last_v50_diagnostics["fallback_result"] = self._safe_http_error(exc)
            raise

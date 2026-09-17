import base64
import hashlib
import json
import re
from typing import Any

import requests

from xiaomi_e10_map_v47 import XiaomiE10MapV47


class XiaomiE10MapV51(XiaomiE10MapV47):
    """V51: recupera la cadena segura V47/V45 y profundiza la sonda _pro.

    V50 heredaba accidentalmente de V44, por lo que el fallback antiguo podía
    volver a resolver ``request_fresh_upload`` contra V41 y ejecutar 10/18,
    10/15 y 10/6. V51 vuelve a heredar de V47 -> V45 -> V44: con map_id=0 esas
    acciones quedan bloqueadas otra vez.

    Además, la respuesta de ``get_interim_file_url_pro`` se recorre de forma
    genérica. Se registran sólo nombres de claves, tipos, tamaños, códigos y
    mensajes saneados; cualquier URL se conserva sólo en memoria para descargar
    el blob y nunca se imprime en F12.
    """

    CLOUD_SLOTS = ("0", "1")

    def __init__(self, *args, **kwargs):
        self.last_v51_diagnostics: dict[str, Any] = {}
        # app_v50 sigue en la cadena visual; dejamos una marca explícita para
        # que no parezca que su sonda insegura es la que está actuando.
        self.last_v50_diagnostics: dict[str, Any] = {
            "route": "V51 reemplaza V50 con herencia segura V47/V45",
            "success": False,
            "fallback_classic": False,
            "pro_slots": {},
        }
        super().__init__(*args, **kwargs)

    @staticmethod
    def _strip_cloud_prefix(text: str) -> str:
        text = str(text or "").lstrip("\ufeff \t\r\n")
        prefix = "&&&START&&&"
        return text[len(prefix):] if text.startswith(prefix) else text

    @staticmethod
    def _looks_base64(text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or ""))
        if len(compact) < 32 or len(compact) % 4 == 1:
            return False
        if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
            return False
        # Reduce falsos positivos con mensajes ASCII largos.
        return any(ch.isdigit() or ch in "+/_-=" for ch in compact)

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

    def _sanitize_message(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = re.sub(r"https?://\S+", "<URL>", text)
        for secret in (
            str(self.session_data.get("user_id") or ""),
            str(self.session_data.get("cuser_id") or ""),
            str(self.did or ""),
        ):
            if secret:
                text = text.replace(secret, "<id>")
        text = re.sub(r"\b\d{6,}\b", "<id>", text)
        return text[:180]

    @staticmethod
    def _schema_atom(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, (int, float)):
            return type(value).__name__
        if isinstance(value, str):
            return f"str[{len(value)}]"
        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"bytes[{len(value)}]"
        if isinstance(value, dict):
            return f"dict[{len(value)}]"
        if isinstance(value, (list, tuple)):
            return f"{type(value).__name__}[{len(value)}]"
        return type(value).__name__

    def _parse_pro_response(self, response: Any):
        parsed = response
        if isinstance(parsed, (bytes, bytearray, memoryview)):
            raw = bytes(parsed)
            try:
                parsed = raw.decode("utf-8-sig")
            except Exception:
                return raw
        if isinstance(parsed, str):
            text = self._strip_cloud_prefix(parsed).strip()
            try:
                return json.loads(text)
            except Exception:
                return text
        return parsed

    def _analyze_pro_response(self, response: Any):
        parsed = self._parse_pro_response(response)
        diag: dict[str, Any] = {
            "response_kind": type(response).__name__,
            "parsed_kind": type(parsed).__name__,
            "top_keys": [],
            "result_kind": None,
            "result_keys": [],
            "app_code": None,
            "message": None,
            "url_count": 0,
            "url_paths": [],
            "candidate_count": 0,
            "candidates": [],
            "schema": [],
            "error": None,
        }
        candidates: list[tuple[bytes, str]] = []
        urls: list[tuple[str, str]] = []
        seen_candidates: set[bytes] = set()
        seen_urls: set[str] = set()

        if isinstance(parsed, dict):
            diag["top_keys"] = [str(k) for k in list(parsed.keys())[:24]]
            if "result" in parsed:
                result = parsed.get("result")
                diag["result_kind"] = type(result).__name__
                if isinstance(result, dict):
                    diag["result_keys"] = [str(k) for k in list(result.keys())[:24]]
            if isinstance(parsed.get("code"), (int, float, str)):
                diag["app_code"] = parsed.get("code")
            for key in ("message", "msg", "description", "desc", "error", "error_msg"):
                if key in parsed and parsed.get(key) not in (None, ""):
                    diag["message"] = self._sanitize_message(parsed.get(key))
                    break

        def add_candidate(data: Any, label: str):
            if isinstance(data, str):
                data = data.encode("utf-8", "replace")
            if not isinstance(data, (bytes, bytearray, memoryview)):
                return
            raw = bytes(data).strip()
            if not raw or raw in seen_candidates:
                return
            seen_candidates.add(raw)
            candidates.append((raw, label))

        def inspect_text(text: str, path: str, key_hint: str | None = None):
            value = self._strip_cloud_prefix(text).strip()
            if not value:
                return
            if value.lower().startswith(("http://", "https://")):
                if value not in seen_urls:
                    seen_urls.add(value)
                    urls.append((value, path))
                return

            # JSON serializado dentro de una clave arbitraria.
            if value[:1] in ("{", "["):
                try:
                    nested = json.loads(value)
                except Exception:
                    nested = None
                if nested is not None:
                    walk(nested, path + ":json", 1)
                    return

            compact = re.sub(r"\s+", "", value)
            hint = str(key_hint or "").lower()
            payload_hint = any(token in hint for token in ("data", "content", "payload", "map", "blob", "file", "cipher"))

            if self._looks_base64(compact):
                padded = compact + "=" * ((4 - len(compact) % 4) % 4)
                for decoder, suffix in ((base64.b64decode, "base64"), (base64.urlsafe_b64decode, "base64url")):
                    try:
                        decoded = decoder(padded.encode("ascii"))
                        if decoded:
                            add_candidate(decoded, f"{path}:{suffix}")
                            break
                    except Exception:
                        pass
            if self._looks_hex(compact):
                try:
                    add_candidate(bytes.fromhex(compact), f"{path}:hex")
                except Exception:
                    pass
            if payload_hint and len(value) >= 16:
                add_candidate(value.encode("utf-8", "replace"), f"{path}:text")

        def walk(value: Any, path: str, depth: int = 0, key_hint: str | None = None):
            if depth > 5:
                return
            if len(diag["schema"]) < 48:
                diag["schema"].append(f"{path}={self._schema_atom(value)}")

            if isinstance(value, dict):
                for key, item in list(value.items())[:32]:
                    key_s = str(key)
                    if diag.get("message") is None and key_s.lower() in (
                        "message", "msg", "description", "desc", "error", "error_msg"
                    ) and isinstance(item, (str, int, float)):
                        diag["message"] = self._sanitize_message(item)
                    walk(item, f"{path}.{key_s}", depth + 1, key_s)
                return
            if isinstance(value, (list, tuple)):
                for index, item in enumerate(list(value)[:16]):
                    walk(item, f"{path}[{index}]", depth + 1, key_hint)
                return
            if isinstance(value, str):
                inspect_text(value, path, key_hint)
                return
            if isinstance(value, (bytes, bytearray, memoryview)):
                raw = bytes(value)
                try:
                    text = raw.decode("utf-8-sig")
                except Exception:
                    add_candidate(raw, f"{path}:bytes")
                    return
                inspect_text(text, path, key_hint)

        try:
            walk(parsed, "response")
        except Exception as exc:
            diag["error"] = type(exc).__name__ + ": " + self._sanitize_message(str(exc) or "sin detalle")

        diag["url_count"] = len(urls)
        diag["url_paths"] = [path for _, path in urls[:8]]
        diag["candidate_count"] = len(candidates)
        diag["candidates"] = [self._candidate_meta(raw, label) for raw, label in candidates[:12]]
        return diag, candidates, urls

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
            diag, candidates, urls = self._analyze_pro_response(response)
            diag["transport_ok"] = True
            diag["application_ok"] = diag.get("app_code") in (0, "0", None)
            return diag, candidates, urls
        except Exception as exc:
            return {
                "transport_ok": False,
                "application_ok": False,
                "response_kind": None,
                "parsed_kind": None,
                "top_keys": [],
                "result_kind": None,
                "result_keys": [],
                "app_code": None,
                "message": None,
                "url_count": 0,
                "url_paths": [],
                "candidate_count": 0,
                "candidates": [],
                "schema": [],
                "error": self._safe_http_error(exc),
            }, [], []

    def request_fresh_upload(self):
        # Guardia explícita para que una refactorización futura no vuelva a V41.
        return super().request_fresh_upload()

    def load(self):
        wifi, owners, dids, macs = self._ordered_key_material()
        pro_slots: dict[str, Any] = {}
        total_native = total_unpack = total_protobuf = 0
        total_xiaomi = total_decrypt = total_json = 0

        self.last_v51_diagnostics = {
            "route": "sonda _pro profunda sobre base segura V47/V45",
            "pro_slots": pro_slots,
            "success": False,
            "fallback_classic": False,
            "safe_base": "V47->V45->V44",
            "unsafe_actions_blocked": True,
        }
        self.last_v50_diagnostics = {
            "route": "V51 reemplaza V50 con herencia segura V47/V45",
            "success": False,
            "fallback_classic": False,
            "pro_slots": {},
        }

        for slot in self.CLOUD_SLOTS:
            slot_name = str(slot)
            slot_diag, candidates, urls = self._probe_pro_slot(slot_name)
            slot_diag["downloads"] = []
            slot_diag["decoder_trials"] = []
            pro_slots[slot_name] = slot_diag

            # Si la URL está escondida bajo una clave no documentada, la usamos
            # sin exponerla en el diagnóstico.
            for url, path in urls[:4]:
                try:
                    response = requests.get(url, timeout=30)
                    raw = bytes(response.content or b"")
                    status = int(response.status_code)
                    slot_diag["downloads"].append({
                        "path": path,
                        "http": status,
                        "bytes": len(raw),
                        "sha12": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
                        "magic": self._magic_label(raw),
                    })
                    response.raise_for_status()
                    if raw:
                        candidates.append((raw, f"{path}:download"))
                except Exception as exc:
                    slot_diag["downloads"].append({
                        "path": path,
                        "error": self._safe_http_error(exc),
                    })

            seen: set[bytes] = set()
            unique_candidates: list[tuple[bytes, str]] = []
            for raw, label in candidates:
                raw_b = bytes(raw or b"")
                if not raw_b or raw_b in seen:
                    continue
                seen.add(raw_b)
                unique_candidates.append((raw_b, label))

            slot_diag["candidate_count_after_download"] = len(unique_candidates)
            slot_diag["candidate_meta_after_download"] = [
                self._candidate_meta(raw, label) for raw, label in unique_candidates[:12]
            ]

            for raw, label in unique_candidates:
                native_snapshot, native_diag = self._decode_native(
                    raw, wifi, owners, dids, macs, slot_name, "get_interim_file_url_pro/v51"
                )
                total_native += int(native_diag.get("attempts", 0) or 0)
                total_unpack += int(native_diag.get("unpack_ok", 0) or 0)
                total_protobuf += int(native_diag.get("protobuf_ok", 0) or 0)
                slot_diag["decoder_trials"].append({
                    "candidate": label,
                    "decoder": "ijai",
                    "attempts": int(native_diag.get("attempts", 0) or 0),
                    "unpack_ok": int(native_diag.get("unpack_ok", 0) or 0),
                    "protobuf_ok": int(native_diag.get("protobuf_ok", 0) or 0),
                })
                if native_snapshot is not None:
                    native_snapshot.blob_kind = label
                    self.last_v51_diagnostics.update({
                        "route": "_pro profundo -> IJAI",
                        "success": True,
                        "winner_slot": slot_name,
                        "winner_candidate": label,
                        "winner_decoder": "ijai",
                        "native_attempts": total_native,
                        "native_unpack_ok": total_unpack,
                        "native_protobuf_ok": total_protobuf,
                        "xiaomi_attempts": total_xiaomi,
                        "xiaomi_decrypt_ok": total_decrypt,
                        "xiaomi_json_ok": total_json,
                    })
                    return self._mark_success(native_snapshot, "V51 _pro profundo -> IJAI")

                xiaomi_snapshot, xiaomi_diag = self._decode_xiaomi(
                    raw, slot_name, "get_interim_file_url_pro/v51"
                )
                total_xiaomi += int(xiaomi_diag.get("attempts", 0) or 0)
                total_decrypt += int(xiaomi_diag.get("decrypt_ok", 0) or 0)
                total_json += int(xiaomi_diag.get("json_ok", 0) or 0)
                slot_diag["decoder_trials"].append({
                    "candidate": label,
                    "decoder": "xiaomi-json",
                    "attempts": int(xiaomi_diag.get("attempts", 0) or 0),
                    "decrypt_ok": int(xiaomi_diag.get("decrypt_ok", 0) or 0),
                    "json_ok": int(xiaomi_diag.get("json_ok", 0) or 0),
                })
                if xiaomi_snapshot is not None:
                    xiaomi_snapshot.blob_kind = label
                    self.last_v51_diagnostics.update({
                        "route": "_pro profundo -> Xiaomi JSON",
                        "success": True,
                        "winner_slot": slot_name,
                        "winner_candidate": label,
                        "winner_decoder": "xiaomi-json",
                        "native_attempts": total_native,
                        "native_unpack_ok": total_unpack,
                        "native_protobuf_ok": total_protobuf,
                        "xiaomi_attempts": total_xiaomi,
                        "xiaomi_decrypt_ok": total_decrypt,
                        "xiaomi_json_ok": total_json,
                    })
                    return self._mark_success(xiaomi_snapshot, "V51 _pro profundo -> Xiaomi JSON")

        self.last_v51_diagnostics.update({
            "native_attempts": total_native,
            "native_unpack_ok": total_unpack,
            "native_protobuf_ok": total_protobuf,
            "xiaomi_attempts": total_xiaomi,
            "xiaomi_decrypt_ok": total_decrypt,
            "xiaomi_json_ok": total_json,
            "fallback_classic": True,
            "route": "_pro profundo sin mapa válido; fallback clásico con guardas V47/V45",
        })

        try:
            snapshot = super().load()
            self.last_v51_diagnostics["fallback_result"] = "OK"
            return snapshot
        except Exception as exc:
            self.last_v51_diagnostics["fallback_result"] = self._safe_http_error(exc)
            raise

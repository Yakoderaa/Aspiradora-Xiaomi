import base64
import hashlib
import json
import math
import re
import zlib
from collections import Counter
from importlib import metadata
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v51 import XiaomiE10MapV51


class XiaomiE10MapV53(XiaomiE10MapV51):
    """V53: clasifica el blob clásico y prueba sólo derivaciones IJAI conocidas.

    V52 descartó get-cur-path 10/12 incluso con el rango uint32 completo. El
    único artefacto de mapa que permanece disponible para el B112 es el slot 0
    clásico de get_interim_file_url. Esta versión no añade combinaciones de
    claves arbitrarias: reproduce explícitamente las dos familias publicadas por
    vacuum-map-parser-ijai (MD5 central ASCII y MD5 hexadecimal completo) y
    expone métricas intermedias para distinguir clave incorrecta de formato no
    IJAI.
    """

    def __init__(self, *args, **kwargs):
        self.last_v53_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    # ----------------------------------------------------------- fingerprint
    @staticmethod
    def _entropy_bits(data: bytes) -> float:
        raw = bytes(data or b"")
        if not raw:
            return 0.0
        total = float(len(raw))
        counts = Counter(raw)
        return -sum((count / total) * math.log2(count / total) for count in counts.values())

    @classmethod
    def _blob_fingerprint(cls, raw: bytes) -> dict[str, Any]:
        data = bytes(raw or b"")
        blocks = [data[i:i + 16] for i in range(0, len(data) - 15, 16)]
        block_counts = Counter(blocks)
        repeated = sum(count - 1 for count in block_counts.values() if count > 1)
        max_repeat = max(block_counts.values(), default=0)
        printable = sum(1 for value in data if value in (9, 10, 13) or 32 <= value < 127)

        raw_json = False
        try:
            decoded = data.decode("utf-8-sig").strip()
            raw_json = isinstance(json.loads(decoded), (dict, list)) if decoded else False
        except Exception:
            raw_json = False

        zlib_ok = False
        try:
            zlib.decompress(data)
            zlib_ok = True
        except Exception:
            pass

        quality = cls._protobuf_quality(data)
        return {
            "bytes": len(data),
            "sha12": hashlib.sha256(data).hexdigest()[:12] if data else "",
            "prefix_hex": data[:16].hex(),
            "block16": bool(data and len(data) % 16 == 0),
            "entropy": round(cls._entropy_bits(data), 4),
            "ascii_ratio": round(printable / len(data), 4) if data else 0.0,
            "blocks": len(blocks),
            "unique_blocks": len(block_counts),
            "repeated_blocks": repeated,
            "max_block_repeat": max_repeat,
            "magic": cls._magic_label(data),
            "raw_json": raw_json,
            "raw_zlib": zlib_ok,
            "raw_protobuf_score": int(quality[0]) if quality else None,
        }

    @staticmethod
    def _runtime_parser_info() -> dict[str, Any]:
        try:
            version = metadata.version("vacuum-map-parser-ijai")
        except Exception:
            version = "desconocida"
        info = {"version": version, "b112_hex_mode": None}
        try:
            from vacuum_map_parser_ijai.status_mapping import is_EncryptKeyTypeHex_model
            info["b112_hex_mode"] = bool(is_EncryptKeyTypeHex_model(MODEL))
        except Exception:
            pass
        return info

    # ------------------------------------------------------- derivación exacta
    @staticmethod
    def _normalized_model_tail() -> str:
        tail = MODEL.split(".")[-1]
        if len(tail) == 2:
            tail = "00" + tail
        elif len(tail) == 3:
            tail = "0" + tail
        elif len(tail) > 4:
            tail = tail[-4:]
        return tail

    @classmethod
    def _known_final_keys(cls, wifi_sn: str, owner: str, did: str, mac: str):
        mac_compact = re.sub(r"[^0-9A-Fa-f]", "", str(mac or "")).lower()
        if len(mac_compact) != 12:
            return []
        temp_key = (mac_compact + cls._normalized_model_tail()).encode("utf-8")
        if len(temp_key) not in (16, 24, 32):
            return []

        seed = f"{wifi_sn}+{owner}+{did}".encode("utf-8")
        encrypted_seed = AES.new(temp_key, AES.MODE_ECB).encrypt(pad(seed, AES.block_size))
        md5_hex = hashlib.md5(base64.b64encode(encrypted_seed)).hexdigest()
        return [
            (md5_hex[8:-8].upper().encode("utf-8"), "md5-central16-ascii"),
            (bytes.fromhex(md5_hex), "md5-full-hex-bytes"),
        ]

    @classmethod
    def _cipher_variants(cls, raw: bytes):
        result = []
        seen = set()
        for data, label in cls._blob_variants(raw):
            payload = bytes(data or b"")
            if not payload or len(payload) % 16:
                continue
            if payload in seen:
                continue
            seen.add(payload)
            result.append((payload, label))
        return result

    @classmethod
    def _inspect_plain(cls, plain: bytes):
        raw = bytes(plain or b"")
        stripped = raw.strip()
        text = None
        try:
            text = stripped.decode("ascii")
        except Exception:
            pass
        ascii_hex = bool(text and len(text) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", text))

        payload_roots = [(raw, "plain")]
        if ascii_hex:
            try:
                payload_roots.insert(0, (bytes.fromhex(text), "plain->hex"))
            except Exception:
                pass

        seen = set()
        json_ok = False
        best = None
        best_label = None
        best_magic = None
        for root, root_label in payload_roots:
            for payload, post_label in cls._post_decrypt_variants(root):
                if payload in seen:
                    continue
                seen.add(payload)
                try:
                    decoded = payload.decode("utf-8-sig").strip()
                    if decoded and isinstance(json.loads(decoded), (dict, list)):
                        json_ok = True
                except Exception:
                    pass
                quality = cls._protobuf_quality(payload)
                if quality and (best is None or int(quality[0]) > int(best[0])):
                    best = (quality[0], payload, quality[1])
                    best_label = root_label + " | " + post_label
                    best_magic = cls._magic_label(payload)

        return {
            "ascii_hex": ascii_hex,
            "json_ok": json_ok,
            "protobuf_score": int(best[0]) if best else None,
            "payload_label": best_label,
            "payload_magic": best_magic,
        }, best

    def _probe_known_ijai(self, raw, wifi, owners, dids, macs, slot, endpoint):
        modes = {
            "md5-central16-ascii": {"attempts": 0, "padding_ok": 0, "hex_ok": 0, "json_ok": 0, "protobuf_ok": 0},
            "md5-full-hex-bytes": {"attempts": 0, "padding_ok": 0, "hex_ok": 0, "json_ok": 0, "protobuf_ok": 0},
        }
        cipher_variants = self._cipher_variants(raw)
        winner = None
        winner_diag = None

        for wifi_sn, wifi_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    for mac, mac_source in macs:
                        keys = self._known_final_keys(str(wifi_sn), str(owner), str(did), str(mac))
                        for key, mode in keys:
                            for cipher, cipher_label in cipher_variants:
                                diag = modes[mode]
                                diag["attempts"] += 1
                                try:
                                    decrypted = AES.new(key, AES.MODE_ECB).decrypt(cipher)
                                    plain = unpad(decrypted, AES.block_size, "pkcs7")
                                    diag["padding_ok"] += 1
                                except Exception:
                                    continue

                                inspected, best = self._inspect_plain(plain)
                                if inspected.get("ascii_hex"):
                                    diag["hex_ok"] += 1
                                if inspected.get("json_ok"):
                                    diag["json_ok"] += 1
                                if best:
                                    diag["protobuf_ok"] += 1
                                    score, payload, robot_map = best
                                    candidate = {
                                        "score": int(score),
                                        "payload": payload,
                                        "robot_map": robot_map,
                                        "mode": mode,
                                        "cipher_variant": cipher_label,
                                        "payload_label": inspected.get("payload_label"),
                                        "payload_magic": inspected.get("payload_magic"),
                                        "sources": {
                                            "wifi_source": wifi_source,
                                            "wifi_len": len(str(wifi_sn)),
                                            "owner_source": owner_source,
                                            "did_source": did_source,
                                            "mac_source": mac_source,
                                        },
                                    }
                                    if winner is None or candidate["score"] > winner["score"]:
                                        winner = candidate
                                        winner_diag = dict(inspected)

        result = {
            "cipher_variants": [label for _, label in cipher_variants],
            "modes": modes,
            "winner": bool(winner),
            "winner_mode": winner.get("mode") if winner else None,
            "winner_cipher_variant": winner.get("cipher_variant") if winner else None,
            "winner_payload_label": winner.get("payload_label") if winner else None,
            "winner_payload_magic": winner.get("payload_magic") if winner else None,
            "winner_score": winner.get("score") if winner else None,
            "winner_sources": winner.get("sources") if winner else None,
            "winner_inspection": winner_diag,
        }
        if not winner:
            return None, result

        snapshot = self._snapshot_from_payload(
            str(slot), endpoint, raw, winner["payload"], winner["robot_map"],
            "V53 IJAI exacto · " + str(winner["mode"]),
            "V53 derivación conocida",
            winner["sources"],
        )
        snapshot.decode_attempts = sum(int(item.get("attempts", 0) or 0) for item in modes.values())
        return snapshot, result

    # --------------------------------------------------------------- descarga
    def _load_classic_probe(self):
        wifi, owners, dids, macs = self._ordered_key_material()
        url, endpoint = self._map_download_url("0")
        response = requests.get(url, timeout=30)
        status = int(response.status_code)
        raw = bytes(response.content or b"")
        response.raise_for_status()

        fingerprint = self._blob_fingerprint(raw)
        snapshot, trial = self._probe_known_ijai(raw, wifi, owners, dids, macs, "0", endpoint)
        self.last_v53_diagnostics = {
            "success": bool(snapshot),
            "route": "slot 0 clásico + fingerprint + derivaciones IJAI conocidas",
            "http": status,
            "endpoint": endpoint,
            "fingerprint": fingerprint,
            "parser_runtime": self._runtime_parser_info(),
            "key_material": {
                "wifi_count": len(wifi),
                "owner_count": len(owners),
                "did_count": len(dids),
                "mac_count": len(macs),
                "wifi_sources": [source for _, source in wifi],
                "owner_sources": [source for _, source in owners],
                "did_sources": [source for _, source in dids],
                "mac_sources": [source for _, source in macs],
            },
            "trial": trial,
            "fallback_v51": False,
            "error": None,
        }
        if snapshot is not None:
            snapshot.valid_slots = ["0"]
            snapshot.slot_errors = {}
        return snapshot

    def load(self):
        try:
            snapshot = self._load_classic_probe()
            if snapshot is not None:
                return self._mark_success(snapshot, "V53 clásico -> IJAI exacto")
        except Exception as exc:
            self.last_v53_diagnostics = {
                **dict(getattr(self, "last_v53_diagnostics", {}) or {}),
                "success": False,
                "route": "sonda clásica V53 falló antes de validar mapa",
                "parser_runtime": self._runtime_parser_info(),
                "error": self._safe_http_error(exc),
            }

        self.last_v53_diagnostics["fallback_v51"] = True
        try:
            return super().load()
        except Exception as exc:
            self.last_v53_diagnostics["fallback_error"] = self._safe_http_error(exc)
            raise

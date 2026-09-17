import gzip
import hashlib
import json
import re
import zlib
from collections import Counter
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from xiaomi_e10_map_v53 import XiaomiE10MapV53


class XiaomiE10MapV54(XiaomiE10MapV53):
    """V54: identifica el contenido real que aparece después de AES + unpad + hex.

    V53 encontró una señal muy fuerte en el slot clásico del B112: una combinación
    con la derivación MD5 completa produjo padding PKCS7 válido y un plaintext
    completamente hexadecimal. V54 no añade claves ni acciones. Aísla sólo esas
    combinaciones parciales y clasifica el payload post-hex para saber si es zlib,
    protobuf genérico, una matriz cruda u otro formato.

    También conserva, por instancia, la evolución del hash del blob clásico para
    separar "puedo descifrarlo" de "es realmente un mapa vivo".
    """

    def __init__(self, *args, **kwargs):
        self.last_v54_diagnostics: dict[str, Any] = {}
        self._v54_reads = 0
        self._v54_last_hash: str | None = None
        self._v54_hash_changes = 0
        self._v54_seen_hashes: list[str] = []
        super().__init__(*args, **kwargs)

    # -------------------------------------------------------- protobuf genérico
    @staticmethod
    def _read_varint(data: bytes, pos: int):
        value = 0
        shift = 0
        start = pos
        while pos < len(data) and shift <= 63:
            byte = data[pos]
            pos += 1
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value, pos
            shift += 7
        raise ValueError(f"varint inválido en {start}")

    @classmethod
    def _protobuf_wire_scan(cls, data: bytes) -> dict[str, Any]:
        raw = bytes(data or b"")
        pos = 0
        fields = 0
        numbers = Counter()
        wire_types = Counter()
        error = None
        max_fields = 20000

        try:
            while pos < len(raw):
                if fields >= max_fields:
                    raise ValueError("demasiados campos")
                key, pos = cls._read_varint(raw, pos)
                field_no = key >> 3
                wire = key & 0x07
                if field_no <= 0:
                    raise ValueError("field number 0")
                numbers[field_no] += 1
                wire_types[wire] += 1
                fields += 1

                if wire == 0:
                    _, pos = cls._read_varint(raw, pos)
                elif wire == 1:
                    if pos + 8 > len(raw):
                        raise ValueError("fixed64 truncado")
                    pos += 8
                elif wire == 2:
                    length, pos = cls._read_varint(raw, pos)
                    if length < 0 or pos + length > len(raw):
                        raise ValueError("length-delimited truncado")
                    pos += length
                elif wire == 5:
                    if pos + 4 > len(raw):
                        raise ValueError("fixed32 truncado")
                    pos += 4
                else:
                    raise ValueError(f"wire type {wire} no soportado")
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)[:100]

        consumed = min(pos, len(raw))
        ratio = (consumed / len(raw)) if raw else 0.0
        valid = bool(raw and error is None and pos == len(raw) and fields > 0)
        return {
            "valid": valid,
            "fields": fields,
            "consumed": consumed,
            "consumed_ratio": round(ratio, 4),
            "field_numbers": [f"{num}:{count}" for num, count in numbers.most_common(12)],
            "wire_types": [f"{wire}:{count}" for wire, count in wire_types.most_common()],
            "error": error,
        }

    # ------------------------------------------------------------- fingerprint
    @classmethod
    def _posthex_fingerprint(cls, data: bytes) -> dict[str, Any]:
        raw = bytes(data or b"")
        counts = Counter(raw)
        printable = sum(1 for value in raw if value in (9, 10, 13) or 32 <= value < 127)
        blocks = [raw[i:i + 16] for i in range(0, len(raw) - 15, 16)]
        block_counts = Counter(blocks)
        repeated = sum(count - 1 for count in block_counts.values() if count > 1)

        raw_json = False
        try:
            text = raw.decode("utf-8-sig").strip()
            raw_json = bool(text and isinstance(json.loads(text), (dict, list)))
        except Exception:
            pass

        quality = cls._protobuf_quality(raw)
        return {
            "bytes": len(raw),
            "sha12": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
            "prefix_hex": raw[:24].hex(),
            "suffix_hex": raw[-16:].hex() if raw else "",
            "magic": cls._magic_label(raw),
            "entropy": round(cls._entropy_bits(raw), 4),
            "ascii_ratio": round(printable / len(raw), 4) if raw else 0.0,
            "zero_ratio": round(counts.get(0, 0) / len(raw), 4) if raw else 0.0,
            "ff_ratio": round(counts.get(255, 0) / len(raw), 4) if raw else 0.0,
            "byte80_ratio": round(counts.get(128, 0) / len(raw), 4) if raw else 0.0,
            "top_bytes": [f"{value:02x}:{count}" for value, count in counts.most_common(8)],
            "blocks": len(blocks),
            "unique_blocks": len(block_counts),
            "repeated_blocks": repeated,
            "max_block_repeat": max(block_counts.values(), default=0),
            "json": raw_json,
            "robotmap_score": int(quality[0]) if quality else None,
            "wire": cls._protobuf_wire_scan(raw),
        }

    @classmethod
    def _compression_trials(cls, data: bytes) -> list[dict[str, Any]]:
        raw = bytes(data or b"")
        trials = []
        methods = (
            ("zlib", lambda payload: zlib.decompress(payload, zlib.MAX_WBITS)),
            ("deflate", lambda payload: zlib.decompress(payload, -zlib.MAX_WBITS)),
            ("gzip", gzip.decompress),
        )
        for name, decoder in methods:
            item: dict[str, Any] = {"name": name, "ok": False}
            try:
                out = bytes(decoder(raw))
                item.update({
                    "ok": True,
                    "bytes": len(out),
                    "sha12": hashlib.sha256(out).hexdigest()[:12],
                    "magic": cls._magic_label(out),
                    "entropy": round(cls._entropy_bits(out), 4),
                    "robotmap_score": (
                        int(cls._protobuf_quality(out)[0])
                        if cls._protobuf_quality(out)
                        else None
                    ),
                    "wire": cls._protobuf_wire_scan(out),
                })
            except Exception as exc:
                item["error"] = type(exc).__name__
            trials.append(item)
        return trials

    # ------------------------------------------------------ candidato parcial
    def _probe_posthex_candidates(self, raw, wifi, owners, dids, macs):
        cipher_variants = self._cipher_variants(raw)
        candidates = []
        attempts_by_mode = Counter()

        for wifi_sn, wifi_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    for mac, mac_source in macs:
                        for key, mode in self._known_final_keys(
                            str(wifi_sn), str(owner), str(did), str(mac)
                        ):
                            for cipher, cipher_label in cipher_variants:
                                attempts_by_mode[mode] += 1
                                try:
                                    decrypted = AES.new(key, AES.MODE_ECB).decrypt(cipher)
                                    plain = unpad(decrypted, AES.block_size, "pkcs7")
                                except Exception:
                                    continue

                                try:
                                    text = plain.strip().decode("ascii")
                                except Exception:
                                    continue
                                if not text or len(text) % 2 or not re.fullmatch(r"[0-9A-Fa-f]+", text):
                                    continue

                                try:
                                    posthex = bytes.fromhex(text)
                                except Exception:
                                    continue

                                fingerprint = self._posthex_fingerprint(posthex)
                                compression = self._compression_trials(posthex)
                                candidate = {
                                    "mode": mode,
                                    "cipher_variant": cipher_label,
                                    "plain_bytes": len(plain),
                                    "plain_sha12": hashlib.sha256(plain).hexdigest()[:12],
                                    "posthex": fingerprint,
                                    "compression": compression,
                                    "sources": {
                                        "wifi_source": str(wifi_source),
                                        "wifi_len": len(str(wifi_sn)),
                                        "owner_source": str(owner_source),
                                        "did_source": str(did_source),
                                        "mac_source": str(mac_source),
                                    },
                                }
                                candidates.append(candidate)

        # Orden estable: primero los que revelan estructura fuerte.
        def rank(item):
            post = item.get("posthex") or {}
            comp = item.get("compression") or []
            comp_robot = max(
                [int(x.get("robotmap_score") or 0) for x in comp if x.get("ok")]
                or [0]
            )
            comp_wire = any(
                bool((x.get("wire") or {}).get("valid"))
                for x in comp
                if x.get("ok")
            )
            return (
                int(post.get("robotmap_score") or 0),
                int(comp_robot),
                bool((post.get("wire") or {}).get("valid")),
                bool(comp_wire),
                -int(post.get("bytes") or 0),
            )

        candidates.sort(key=rank, reverse=True)
        return {
            "attempts": dict(attempts_by_mode),
            "candidate_count": len(candidates),
            "candidates": candidates[:8],
            "cipher_variants": [label for _, label in cipher_variants],
        }

    # --------------------------------------------------------------- descarga
    def _record_blob_hash(self, full_hash: str):
        self._v54_reads += 1
        if full_hash:
            if self._v54_last_hash is not None and full_hash != self._v54_last_hash:
                self._v54_hash_changes += 1
            self._v54_last_hash = full_hash
            if full_hash not in self._v54_seen_hashes:
                self._v54_seen_hashes.append(full_hash)
                self._v54_seen_hashes = self._v54_seen_hashes[-8:]

    def _load_v54_probe(self):
        wifi, owners, dids, macs = self._ordered_key_material()
        url, endpoint = self._map_download_url("0")
        import requests
        response = requests.get(url, timeout=30)
        status = int(response.status_code)
        raw = bytes(response.content or b"")
        response.raise_for_status()

        full_hash = hashlib.sha256(raw).hexdigest() if raw else ""
        self._record_blob_hash(full_hash)
        probe = self._probe_posthex_candidates(raw, wifi, owners, dids, macs)

        self.last_v54_diagnostics = {
            "route": "slot 0 clásico -> AES/PKCS7 -> hex -> análisis post-hex",
            "http": status,
            "endpoint": endpoint,
            "blob_bytes": len(raw),
            "blob_sha12": full_hash[:12] if full_hash else "",
            "reads": self._v54_reads,
            "hash_changes": self._v54_hash_changes,
            "unique_hashes": len(self._v54_seen_hashes),
            "probe": probe,
            "key_material": {
                "wifi_count": len(wifi),
                "owner_count": len(owners),
                "did_count": len(dids),
                "mac_count": len(macs),
            },
            "error": None,
            "fallback_v53": False,
        }
        return None

    def load(self):
        try:
            self._load_v54_probe()
        except Exception as exc:
            self.last_v54_diagnostics = {
                **dict(getattr(self, "last_v54_diagnostics", {}) or {}),
                "route": "sonda post-hex V54 falló",
                "error": self._safe_http_error(exc),
                "fallback_v53": True,
            }

        self.last_v54_diagnostics["fallback_v53"] = True
        try:
            return super().load()
        except Exception as exc:
            self.last_v54_diagnostics["fallback_error"] = self._safe_http_error(exc)
            raise

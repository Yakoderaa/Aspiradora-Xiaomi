import base64
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v49
import app_v50
from xiaomi_e10_map_v41 import ExhaustiveMapSnapshot
from xiaomi_e10_map_v50 import XiaomiE10MapV50


# 1) Una respuesta _pro que sea base64 directo debe conservar texto y binario.
probe = XiaomiE10MapV50.__new__(XiaomiE10MapV50)
raw_payload = bytes(range(32))
encoded = base64.b64encode(raw_payload).decode("ascii")
diag, candidates = probe._pro_payload_candidates(encoded)
assert diag["candidate_count"] >= 2
assert any(raw == raw_payload for raw, _ in candidates)
assert any(item["bytes"] == len(raw_payload) and item["block16"] for item in diag["candidates"])


# 2) También debe abrir el envelope {version:2,data:<base64>} visto en Xiaomi.
envelope = json.dumps({"result": {"version": 2, "data": encoded}})
diag2, candidates2 = probe._pro_payload_candidates(envelope)
assert diag2["version"] == 2
assert any(raw == raw_payload for raw, _ in candidates2)


# 3) Si _pro devuelve una URL tradicional, se marca como URL y no como ciphertext.
diag3, candidates3 = probe._pro_payload_candidates({"result": {"url": "https://example.invalid/signed"}})
assert diag3["url_present"] is True
assert candidates3 == []


# 4) load() debe preferir un payload _pro válido antes de tocar el fallback clásico.
direct = XiaomiE10MapV50.__new__(XiaomiE10MapV50)
direct.last_v50_diagnostics = {}
direct.last_v44_diagnostics = {}
direct.last_key_diagnostics = {}
direct.CLOUD_SLOTS = ("0", "1")
direct._ordered_key_material = types.MethodType(
    lambda self: ([('WIFI', 'wifi-test')], [('OWNER', 'owner-test')], [('DID', 'did-test')], [('MAC', 'mac-test')]),
    direct,
)


def fake_probe(self, slot):
    if str(slot) == "0":
        return {
            "ok": True,
            "response_kind": "str",
            "parsed_kind": None,
            "version": None,
            "url_present": False,
            "candidate_count": 1,
            "candidates": [self._candidate_meta(b"ciphertext-00000", "response:base64")],
            "error": None,
        }, [(b"ciphertext-00000", "response:base64")]
    return {
        "ok": True,
        "response_kind": "dict",
        "parsed_kind": "dict",
        "version": None,
        "url_present": True,
        "candidate_count": 0,
        "candidates": [],
        "error": None,
    }, []


def fake_native(self, raw, wifi, owners, dids, macs, slot, endpoint):
    snap = ExhaustiveMapSnapshot(
        raw_size=len(raw),
        decrypted_size=123,
        raw_prefix_hex=raw[:16].hex(),
        blob_sha256="a" * 64,
        raw_robot=(1.0, 2.0),
        raw_base=(0.0, 0.0),
        raw_path=[(0.0, 0.0), (1.0, 2.0)],
        slot=str(slot),
        endpoint=endpoint,
        wifi_sn_source="wifi-test",
        wifi_sn_length=4,
        owner_source="owner-test",
        did_source="did-test",
        mac_source="mac-test",
        mac_available=True,
    )
    return snap, {"attempts": 1, "unpack_ok": 1, "protobuf_ok": 1, "parse_ok": 1}


direct._probe_pro_slot = types.MethodType(fake_probe, direct)
direct._decode_native = types.MethodType(fake_native, direct)
direct._decode_xiaomi = types.MethodType(lambda self, *args, **kwargs: (_ for _ in ()).throw(AssertionError("No debe llegar a Xiaomi si IJAI ya ganó")), direct)
selected = direct.load()
assert selected.endpoint == "get_interim_file_url_pro/direct"
assert direct.last_v50_diagnostics["success"] is True
assert direct.last_v50_diagnostics["winner_decoder"] == "ijai"
assert direct.last_v50_diagnostics["fallback_classic"] is False

assert issubclass(app_v50.App, app_v49.App)
print("SMOKE TEST V50 OK: payload _pro directo + envelope v2 + fallback seguro")

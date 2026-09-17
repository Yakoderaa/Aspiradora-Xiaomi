import inspect
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v53
from xiaomi_e10_map_v53 import XiaomiE10MapV53


wifi = "ABCDEFGHIJ12345678"
owner = "1234567890"
did = "987654321"
mac = "AA:BB:CC:DD:EE:FF"
sentinel = b"V53-valid-protobuf-sentinel"
compressed = zlib.compress(sentinel)
plain_hex = compressed.hex().encode("ascii")

original_quality = XiaomiE10MapV53._protobuf_quality
try:
    XiaomiE10MapV53._protobuf_quality = staticmethod(
        lambda payload: (9, SimpleNamespace()) if bytes(payload) == sentinel else None
    )

    probe = XiaomiE10MapV53.__new__(XiaomiE10MapV53)
    probe._snapshot_from_payload = lambda *args, **kwargs: SimpleNamespace(
        decode_attempts=0,
        valid_slots=[],
        slot_errors={},
        crypto_mode=args[5] if len(args) > 5 else "",
    )

    keys = dict((label, key) for key, label in XiaomiE10MapV53._known_final_keys(wifi, owner, did, mac))
    assert set(keys) == {"md5-central16-ascii", "md5-full-hex-bytes"}
    assert all(len(key) == 16 for key in keys.values())

    for expected_mode in ("md5-central16-ascii", "md5-full-hex-bytes"):
        cipher = AES.new(keys[expected_mode], AES.MODE_ECB).encrypt(pad(plain_hex, AES.block_size))
        snapshot, diag = probe._probe_known_ijai(
            cipher,
            [(wifi, "wifi-test")],
            [(owner, "owner-test")],
            [(did, "did-test")],
            [(mac, "mac-test")],
            "0",
            "test-endpoint",
        )
        assert snapshot is not None
        assert diag["winner"] is True
        assert diag["winner_mode"] == expected_mode
        assert diag["modes"][expected_mode]["padding_ok"] >= 1
        assert diag["modes"][expected_mode]["hex_ok"] >= 1
        assert diag["modes"][expected_mode]["protobuf_ok"] >= 1

finally:
    XiaomiE10MapV53._protobuf_quality = original_quality

fingerprint = XiaomiE10MapV53._blob_fingerprint(b"A" * 16 + b"B" * 16 + b"A" * 16 + b"C" * 16)
assert fingerprint["block16"] is True
assert fingerprint["blocks"] == 4
assert fingerprint["unique_blocks"] == 3
assert fingerprint["repeated_blocks"] == 1
assert fingerprint["max_block_repeat"] == 2
assert fingerprint["prefix_hex"] == (b"A" * 16).hex()
assert 0.0 <= fingerprint["entropy"] <= 8.0

runtime = XiaomiE10MapV53._runtime_parser_info()
assert runtime.get("version")

source = inspect.getsource(sys.modules["xiaomi_e10_map_v53"])
for forbidden in ("call_action_by", "set_property_by", "10/23", "10/18", "10/15", "10/6"):
    assert forbidden not in source, f"V53 no debe ejecutar ni referenciar acción insegura: {forbidden}"

assert issubclass(app_v53.App, app_v53.app_v52.App)
print("SMOKE TEST V53 OK: fingerprint + 2 derivaciones IJAI conocidas + cero acciones al robot")

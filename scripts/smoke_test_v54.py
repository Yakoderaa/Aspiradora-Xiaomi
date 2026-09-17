import inspect
import sys
import zlib
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v54
from xiaomi_e10_map_v54 import XiaomiE10MapV54


wifi = "ABCDEFGHIJ12345678"
owner = "1234567890"
did = "987654321"
mac = "AA:BB:CC:DD:EE:FF"

keys = dict((label, key) for key, label in XiaomiE10MapV54._known_final_keys(wifi, owner, did, mac))
assert set(keys) == {"md5-central16-ascii", "md5-full-hex-bytes"}

# Protobuf wire genérico válido, a propósito NO RobotMap.
wire_payload = b"\x08\x96\x01\x12\x03abc"
assert XiaomiE10MapV54._protobuf_wire_scan(wire_payload)["valid"] is True

plain_hex = wire_payload.hex().encode("ascii")
cipher = AES.new(keys["md5-full-hex-bytes"], AES.MODE_ECB).encrypt(
    pad(plain_hex, AES.block_size)
)

probe = XiaomiE10MapV54.__new__(XiaomiE10MapV54)
result = probe._probe_posthex_candidates(
    cipher,
    [(wifi, "LAN 1/5")],
    [(owner, "UID sufijo 7/45")],
    [(did, "settings.did")],
    [(mac, "miIO info")],
)
assert result["candidate_count"] >= 1
candidate = next(
    item for item in result["candidates"]
    if item["mode"] == "md5-full-hex-bytes"
)
assert candidate["posthex"]["bytes"] == len(wire_payload)
assert candidate["posthex"]["sha12"]
assert candidate["posthex"]["wire"]["valid"] is True
assert candidate["sources"]["wifi_source"] == "LAN 1/5"
assert candidate["sources"]["owner_source"] == "UID sufijo 7/45"

# La capa de compresión debe decirnos qué aparece DESPUÉS del hex.
compressed = zlib.compress(wire_payload)
trials = XiaomiE10MapV54._compression_trials(compressed)
ztrial = next(item for item in trials if item["name"] == "zlib")
assert ztrial["ok"] is True
assert ztrial["bytes"] == len(wire_payload)
assert ztrial["wire"]["valid"] is True

# Fingerprint útil para matrices/artefactos repetidos.
matrix_like = b"\x00" * 256 + b"\x80" * 64 + b"\xff" * 32
fingerprint = XiaomiE10MapV54._posthex_fingerprint(matrix_like)
assert fingerprint["bytes"] == len(matrix_like)
assert fingerprint["zero_ratio"] > 0.70
assert fingerprint["byte80_ratio"] > 0.10
assert fingerprint["top_bytes"]
assert fingerprint["prefix_hex"]

# Seguimiento de frescura sin almacenar payloads.
tracker = XiaomiE10MapV54.__new__(XiaomiE10MapV54)
tracker._v54_reads = 0
tracker._v54_last_hash = None
tracker._v54_hash_changes = 0
tracker._v54_seen_hashes = []
tracker._record_blob_hash("a" * 64)
tracker._record_blob_hash("a" * 64)
tracker._record_blob_hash("b" * 64)
assert tracker._v54_reads == 3
assert tracker._v54_hash_changes == 1
assert len(tracker._v54_seen_hashes) == 2

source = inspect.getsource(sys.modules["xiaomi_e10_map_v54"])
for forbidden in ("call_action_by", "set_property_by", "10/23", "10/18", "10/15", "10/6"):
    assert forbidden not in source, f"V54 no debe ejecutar ni referenciar acción insegura: {forbidden}"

assert issubclass(app_v54.App, app_v54.app_v53.App)
print("SMOKE TEST V54 OK: candidato post-hex + protobuf genérico + compresión + frescura + cero acciones")

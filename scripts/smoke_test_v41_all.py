import base64
import hashlib
import json
import sys
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41_all import XiaomiE10MapV41All

# JSON plano válido debe convertirse a RobotMap sintético.
obj = {
    "map_id": 77,
    "resolution": 0.05,
    "position": {"x": 1250, "y": 500},
    "charger": {"x": 1000, "y": 500},
    "paths": [{"x": 1000, "y": 500}, {"x": 1100, "y": 500}, {"x": 1250, "y": 500}],
}
raw_json = json.dumps(obj).encode()
client = XiaomiE10MapV41All.__new__(XiaomiE10MapV41All)
client.did = "987654321"
client.decode_attempts = 0
score, payload, rm, mode, label = client._decode_exhaustive(raw_json, [])
assert rm.currentPose.x == 1250
assert rm.chargeStation.x == 1000
assert len(rm.historyPose.points) == 3
assert "JSON" in mode

# Cadena Xiaomi Home AES-CBC compatible con el fallback v39/v41.
model_key = MODEL[-16:].encode("latin1")
assert len(model_key) == 16
iv = XiaomiE10MapV41All.XIAOMI_IV
original = model_key + client.did.encode("latin1")
material = AES.new(model_key, AES.MODE_CBC, iv).encrypt(pad(original, 16))
key = hashlib.md5(material).digest()
cipher = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(raw_json, 16))
blob = base64.b64encode(cipher)
client.decode_attempts = 0
score, payload, rm, mode, label = client._decode_exhaustive(blob, [])
assert rm.currentPose.x == 1250
assert len(rm.historyPose.points) == 3
assert "AES-CBC" in mode

print("SMOKE TEST V41 ALL OK: JSON plano + Xiaomi AES-CBC validados")

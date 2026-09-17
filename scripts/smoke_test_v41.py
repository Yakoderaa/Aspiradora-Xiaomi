import base64
import hashlib
import json
import sys
import zlib
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v41
from vacuum_map_parser_ijai import RobotMap_pb2 as RobotMap
from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41 import XiaomiE10MapV41


def build_robot_map():
    rm = RobotMap.RobotMap()
    rm.mapHead.mapHeadId = 42
    rm.mapHead.sizeX = 4
    rm.mapHead.sizeY = 4
    rm.mapHead.minX = -2.0
    rm.mapHead.minY = -2.0
    rm.mapHead.maxX = 2.0
    rm.mapHead.maxY = 2.0
    rm.mapHead.resolution = 0.05
    rm.mapData.mapData = bytes([0, 0, 0, 0, 0, 10, 10, 0, 0, 10, 10, 0, 0, 0, 0, 0])
    rm.currentPose.x = 1.25
    rm.currentPose.y = -0.50
    rm.currentPose.poseId = 123
    rm.chargeStation.x = 0.25
    rm.chargeStation.y = -0.50
    p1 = rm.historyPose.points.add()
    p1.x, p1.y = 0.25, -0.50
    p2 = rm.historyPose.points.add()
    p2.x, p2.y = 1.25, -0.50
    return rm.SerializeToString()


def standard_ijai_blob(payload, wifi_sn, owner_id, did, mac):
    temp_model = MODEL.split(".")[-1]
    temp_key = mac.replace(":", "").lower() + temp_model
    source = f"{wifi_sn}+{owner_id}+{did}"
    first = AES.new(temp_key.encode("utf-8"), AES.MODE_ECB).encrypt(
        pad(source.encode("utf-8"), AES.block_size)
    )
    decrypt_key = hashlib.md5(base64.b64encode(first)).digest()
    compressed_hex = zlib.compress(payload).hex().encode("ascii")
    encrypted = AES.new(decrypt_key, AES.MODE_ECB).encrypt(
        pad(compressed_hex, AES.block_size)
    )
    return base64.b64encode(encrypted)


# 1) Validación protobuf directa y sin cifrado.
payload = build_robot_map()
quality = XiaomiE10MapV41._protobuf_quality(payload)
assert quality and quality[0] >= 10
client = XiaomiE10MapV41.__new__(XiaomiE10MapV41)
client.decode_attempts = 0
score, decoded, rm, mode, label = client._decode_exhaustive(zlib.compress(payload), [])
assert decoded == payload
assert rm.currentPose.poseId == 123
assert mode.startswith("sin AES")

# 2) Cadena IJAI exacta usada por vacuum-map-parser-ijai.
wifi_sn = "ABCDEFGHIJ12345678"
owner_id = "1234567890"
did = "987654321"
mac = "AA:BB:CC:DD:EE:FF"
blob = standard_ijai_blob(payload, wifi_sn, owner_id, did, mac)
keys = XiaomiE10MapV41._derive_keys(
    [(wifi_sn, "test-wifi")], [(owner_id, "test-owner")], [(did, "test-did")], [(mac, "test-mac")]
)
assert keys
client.decode_attempts = 0
score, decoded, rm, mode, key_label = client._decode_exhaustive(blob, keys)
assert decoded == payload
assert rm.currentPose.poseId == 123
assert "AES-ECB" in mode
assert "test-wifi" in key_label

# 3) La misma carga envuelta en JSON también debe sobrevivir.
wrapped = json.dumps({"data": blob.decode("ascii")}).encode("utf-8")
client.decode_attempts = 0
score, decoded, rm, mode, key_label = client._decode_exhaustive(wrapped, keys)
assert decoded == payload


class FakeDevice:
    def __init__(self, map_id=0, privacy=0):
        self.map_id = map_id
        self.privacy = privacy
        self.calls = []
        self.sets = []

    def get_property_by(self, siid, piid):
        if (siid, piid) == (10, 2):
            return [{"code": 0, "value": self.map_id}]
        if (siid, piid) == (10, 23):
            return [{"code": 0, "value": self.privacy}]
        return [{"code": 0, "value": None}]

    def set_property_by(self, siid, piid, value):
        self.sets.append((siid, piid, value))
        if (siid, piid) == (10, 23):
            self.privacy = value
        return True

    def call_action_by(self, siid, aiid, params):
        self.calls.append((siid, aiid, tuple(params)))
        if (siid, aiid) == (10, 1):
            maps = [] if not self.map_id else [{"id": self.map_id, "cur": True, "name": "Casa"}]
            return {"out": [{"piid": 4, "value": json.dumps(maps)}]}
        return {"out": [{"piid": 21, "value": 1}]}


class FakeVacuum:
    def __init__(self, device):
        self.device = device


# 4) map_id=0 NO debe disparar acciones by-map-id. Sí realtime.
client = XiaomiE10MapV41.__new__(XiaomiE10MapV41)
client.vacuum = FakeVacuum(FakeDevice(map_id=0, privacy=0))
client.privacy_original = None
client.privacy_temporarily_enabled = False
client.last_upload_diagnostics = {}
result = client.request_fresh_upload()
actions = [aiid for _, aiid, _ in client.vacuum.device.calls]
assert 18 in actions and 15 in actions and 6 in actions
assert 14 not in actions and 2 not in actions
assert result["map_id"] == 0

# 5) map_id real agrega los fallbacks by-id.
client = XiaomiE10MapV41.__new__(XiaomiE10MapV41)
client.vacuum = FakeVacuum(FakeDevice(map_id=42, privacy=0))
client.privacy_original = None
client.privacy_temporarily_enabled = False
client.last_upload_diagnostics = {}
result = client.request_fresh_upload()
actions = [aiid for _, aiid, _ in client.vacuum.device.calls]
assert 14 in actions and 2 in actions
assert result["map_id"] == 42

# 6) map-privacy=1 se habilita temporalmente y se restaura.
client = XiaomiE10MapV41.__new__(XiaomiE10MapV41)
client.vacuum = FakeVacuum(FakeDevice(map_id=0, privacy=1))
client.privacy_original = None
client.privacy_temporarily_enabled = False
client.last_upload_diagnostics = {}
client.request_fresh_upload()
assert client.vacuum.device.privacy == 0
assert client.privacy_temporarily_enabled
assert client.restore_map_privacy()
assert client.vacuum.device.privacy == 1

# 7) Pipeline de escala existente sigue recibiendo metros.
class Snapshot:
    raw_robot = (12.0, 8.0)
    raw_base = (10.0, 8.0)
    raw_path = [(10.0, 8.0), (11.0, 8.0), (12.0, 8.0)]

assert app_v41.App._v40_detect_scale(Snapshot()) == 1.0
relative = app_v41.App._v39_relative_mm((12.0, 8.0), (10.0, 8.0))
assert relative and abs(relative["x"] - 2.0) < 1e-9

print("SMOKE TEST V41 OK: protobuf + IJAI AES + wrappers + uploads realtime/by-id + privacidad + escala")

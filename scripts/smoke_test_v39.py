import base64
import hashlib
import json
import os
import sys
import zlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from app_v39 import App
from xiaomi_e10 import MODEL
from xiaomi_map import XiaomiE10MapClient


IV = b"ABCDEF1234123412"


def encrypt_like_xiaomi_home(payload: dict, model: str, device_id: str) -> bytes:
    """Inverso independiente del decoder de producción."""
    model_key = model[-16:].encode("latin1")
    first = AES.new(model_key, AES.MODE_CBC, IV).encrypt(
        pad(model_key + device_id.encode("latin1"), AES.block_size)
    )
    key = hashlib.md5(first).digest()
    compressed = zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    encrypted = AES.new(key, AES.MODE_CBC, IV).encrypt(pad(compressed, AES.block_size))
    envelope = {"version": 2, "data": base64.b64encode(encrypted).decode("ascii")}
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


# Regresión exacta del fallo físico reportado: esta transformación vieja daba
# una clave AES de 14 bytes. Xiaomi Home usa los últimos 16 del modelo completo.
assert len(MODEL.replace("xiaomi", "mi").encode("latin1")) == 14
assert len(MODEL[-16:].encode("latin1")) == 16
assert MODEL[-16:] == "aomi.vacuum.b112"

pixels = bytes([
    0, 0, 0, 0,
    0, 1, 1, 0,
    0, 1, 1, 0,
    0, 0, 0, 0,
])
payload = {
    "map_id": 7,
    "width": 4,
    "height": 4,
    "resolution": 50,
    "origin_x": 0,
    "origin_y": 0,
    "map_data": base64.b64encode(zlib.compress(pixels)).decode("ascii"),
    "have_pile": True,
    "pile_x": 1000,
    "pile_y": 2000,
    "pile_yaw": 0,
    "position": {"x": 1450, "y": 2250, "yaw": 0},
    "paths": {
        "points": [
            {"x": 1000, "y": 2000},
            {"x": 1120, "y": 2000},
            {"x": 1300, "y": 2100},
            {"x": 1450, "y": 2250},
        ]
    },
}

did = "1234567890"
blob = encrypt_like_xiaomi_home(payload, MODEL, did)
plaintext = XiaomiE10MapClient.decrypt_xiaomi_v2(blob, MODEL, did)
decoded = json.loads(plaintext)
assert decoded == payload

robot, base, path = XiaomiE10MapClient._payload_telemetry(decoded)
assert robot == (1450.0, 2250.0)
assert base == (1000.0, 2000.0)
assert len(path) == 4

# Verifica además la librería de parsing con el JSON ya descifrado.
parser = XiaomiE10MapClient._parser()
map_data = parser.parse(plaintext)
assert map_data.vacuum_position is not None
assert float(map_data.vacuum_position.x) == 1450.0
assert map_data.charger is not None
assert float(map_data.charger.x) == 1000.0
assert map_data.path is not None

local = App._v39_local_path(path, base)
assert len(local) == 4
assert abs(local[-1]["x"] - 0.45) < 1e-9
assert abs(local[-1]["y"] - 0.25) < 1e-9
assert App._v39_path_has_motion(local) is True

print("smoke_test_v39 OK · AES suffix16 + JSON position/base/paths + parser")

import base64
import hashlib
import json
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

import app_v43
from xiaomi_e10 import MODEL
from xiaomi_e10_map_v43 import XiaomiE10MapV43


IV = b"ABCDEF1234123412"


def encrypt_xiaomi_json(payload: dict, model_key: str, did: str) -> bytes:
    # Inversa exacta de vacuum_map_parser_xiaomi.aes_decryptor.decrypt().
    seed = (model_key + did).encode("latin1")
    enc_seed = AES.new(model_key.encode("latin1"), AES.MODE_CBC, IV).encrypt(
        pad(seed, AES.block_size)
    )
    final_key = hashlib.md5(enc_seed).digest()
    compressed = zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return AES.new(final_key, AES.MODE_CBC, IV).encrypt(
        pad(compressed, AES.block_size)
    )


model_key = MODEL[-16:]
did = "987654321"
assert len(model_key.encode("latin1")) == 16
assert XiaomiE10MapV43._model_key_candidates()[0] == (model_key, "MODEL[-16:]")

pixels = bytes([0, 1, 2, 0])
payload = {
    "map_id": 77,
    "width": 2,
    "height": 2,
    "resolution": 50,
    "origin_x": 0,
    "origin_y": 0,
    "map_data": base64.b64encode(zlib.compress(pixels)).decode("ascii"),
    "have_pile": 1,
    "pile_x": 1000,
    "pile_y": 2000,
    "pile_yaw": 0,
    "position": {"x": 1250, "y": 2250, "yaw": 0},
    "paths": {"points": [
        {"x": 1000, "y": 2000},
        {"x": 1250, "y": 2250},
    ]},
}

ciphertext = encrypt_xiaomi_json(payload, model_key, did)
client = object.__new__(XiaomiE10MapV43)
client.did = did
client.last_xiaomi_diagnostics = {}

snapshot, diag = client._decode_xiaomi(ciphertext, "0", "test-endpoint")
assert snapshot is not None
assert diag["winner"] is True
assert diag["decrypt_ok"] >= 1
assert diag["json_ok"] >= 1
assert diag["winner_model_key"] == "MODEL[-16:]"
assert snapshot.map_id == 77
assert snapshot.resolution == 50.0
assert snapshot.raw_robot == (1250.0, 2250.0)
assert snapshot.raw_base == (1000.0, 2000.0)
assert snapshot.raw_path == [(1000.0, 2000.0), (1250.0, 2250.0)]

# Formato viejo del extractor: wrapper JSON con data base64.
wrapped = json.dumps({"data": base64.b64encode(ciphertext).decode("ascii")}).encode()
variants = XiaomiE10MapV43._xiaomi_blob_variants(wrapped)
assert any(data == ciphertext and label == "json.data->base64" for data, label in variants)

# La UI debe convertir las coordenadas JSON (mm) a metros.
fake_snapshot = SimpleNamespace(crypto_mode="Xiaomi JSON · AES-CBC · hex-str exacto")
assert app_v43.App._v40_detect_scale(fake_snapshot) == 0.001

print("SMOKE TEST V43 OK: Xiaomi JSON CBC + hex str + payload + wrapper + escala mm->m")

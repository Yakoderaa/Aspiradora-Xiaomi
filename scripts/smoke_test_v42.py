import base64
import hashlib
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

import app_v42
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser
from vacuum_map_parser_ijai.status_mapping import is_EncryptKeyTypeHex_model
from xiaomi_e10 import MODEL
from xiaomi_e10_map_v42 import XiaomiE10MapV42


def encode_like_ijai_parser(payload: bytes, wifi_sn: str, owner: str, did: str, mac: str) -> bytes:
    """Inversa exacta de aes_decryptor.py + unpack_map() del paquete IJAI 0.1.1."""
    normalized_mac = "".join(mac.lower().split(":"))
    model_tail = MODEL.split(".")[-1]
    if len(model_tail) == 2:
        model_tail = "00" + model_tail
    elif len(model_tail) == 3:
        model_tail = "0" + model_tail
    elif len(model_tail) > 4:
        model_tail = model_tail[-4:]
    temp_key = (normalized_mac + model_tail).encode("utf-8")
    seed = f"{wifi_sn}+{owner}+{did}"
    encrypted_seed = AES.new(temp_key, AES.MODE_ECB).encrypt(
        pad(seed.encode("utf-8"), AES.block_size)
    )
    encrypted_seed_b64 = base64.b64encode(encrypted_seed)
    md5_hex = hashlib.md5(encrypted_seed_b64).hexdigest()

    # Importante para xiaomi.vacuum.b112: NO está en la lista de modelos que
    # interpretan el MD5 como hex. El parser usa los 16 caracteres centrales,
    # en mayúsculas, directamente como clave AES ASCII.
    if is_EncryptKeyTypeHex_model(MODEL):
        final_key = bytes.fromhex(md5_hex)
    else:
        final_key = md5_hex[8:-8].upper().encode("utf-8")

    compressed_hex = zlib.compress(payload).hex().encode("ascii")
    encrypted_map = AES.new(final_key, AES.MODE_ECB).encrypt(
        pad(compressed_hex, AES.block_size)
    )
    return base64.b64encode(encrypted_map)


wifi_sn = "ABCDEFGHIJ12345678"
owner = "1234567890"
did = "987654321"
mac = "AA:BB:CC:DD:EE:FF"
payload = b"IJAI-native-v42-roundtrip\x00\x01\x02"
assert not is_EncryptKeyTypeHex_model(MODEL), "b112 debe usar clave ASCII central según IJAI 0.1.1"
encoded = encode_like_ijai_parser(payload, wifi_sn, owner, did, mac)
parser = IjaiMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])
unpacked = parser.unpack_map(
    encoded,
    wifi_sn=wifi_sn,
    owner_id=owner,
    device_id=did,
    model=MODEL,
    device_mac=mac,
)
assert unpacked == payload

# El blob binario puro también se convierte a Base64 como fallback.
cipher_binary = base64.b64decode(encoded)
variants = XiaomiE10MapV42._encoded_variants(cipher_binary)
assert any(data == encoded and "bin->b64" in label for data, label in variants)

# Priorizamos seriales con la forma que usa el extractor IJAI publicado.
assert XiaomiE10MapV42._strict_wifi_serial(wifi_sn)
assert not XiaomiE10MapV42._strict_wifi_serial("hello")
items = [
    ("OTHERDEVICEVALUE123", "LAN 1/2"),
    (wifi_sn, "LAN 1/5"),
    ("ZYXWVUTSRQ12345678", "LAN 1/3"),
]
ordered = sorted(items, key=XiaomiE10MapV42._wifi_priority)
assert ordered[0][1] == "LAN 1/5"
assert ordered[1][1] == "LAN 1/3"

# El extractor genérico de path acepta la estructura MapData.path.path.
p1 = SimpleNamespace(x=1.0, y=2.0)
p2 = SimpleNamespace(x=3.0, y=4.0)
fake_map = SimpleNamespace(path=SimpleNamespace(path=[[p1, p2]]))
assert XiaomiE10MapV42._path_points(fake_map) == [(1.0, 2.0), (3.0, 4.0)]

# Nunca deben quedar URLs FDS firmadas dentro del diagnóstico.
clean = XiaomiE10MapV42._safe_http_error(RuntimeError("falló https://example.com/x?Signature=secret"))
assert "example.com" not in clean and "Signature" not in clean

assert issubclass(app_v42.App, app_v42.app_v41.App)
print("SMOKE TEST V42 OK: clave b112 ASCII-MD5 + unpack_map real + Base64 + path + sanitización")

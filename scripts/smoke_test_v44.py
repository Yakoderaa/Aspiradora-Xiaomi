import base64
import hashlib
import sys
import zlib
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v44
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_ijai import RobotMap_pb2 as RobotMap
from vacuum_map_parser_ijai.map_data_parser import IjaiMapDataParser
from vacuum_map_parser_ijai.status_mapping import is_EncryptKeyTypeHex_model
from xiaomi_e10 import MODEL
from xiaomi_e10_map_v44 import XiaomiE10MapV44


def encode_like_ijai_parser(payload: bytes, wifi_sn: str, owner: str, did: str, mac: str) -> bytes:
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
    b64_seed = base64.b64encode(encrypted_seed)
    md5_hex = hashlib.md5(b64_seed).hexdigest()
    if is_EncryptKeyTypeHex_model(MODEL):
        final_key = bytes.fromhex(md5_hex)
    else:
        final_key = md5_hex[8:-8].upper().encode("utf-8")
    compressed_hex = zlib.compress(payload).hex().encode("ascii")
    encrypted_map = AES.new(final_key, AES.MODE_ECB).encrypt(
        pad(compressed_hex, AES.block_size)
    )
    return base64.b64encode(encrypted_map)


# Caso real documentado por Xiaomi Cloud Map Extractor: la barra forma parte
# del wifi_sn y NO debe eliminarse para la derivación principal.
wifi_sn = "57054/B2AE7F5NE03300"
owner = "1664180447"
did = "709919863"
mac = "AC:8C:46:9F:B5:B8"
assert XiaomiE10MapV44._strict_wifi_serial(wifi_sn)
assert not XiaomiE10MapV44._strict_wifi_serial("1152339753")
serials, owners = XiaomiE10MapV44._serial_and_owner_from_multi(
    f'[0,3,1,1,2,0,-28800,5,9.1,0,"zh_CN","{wifi_sn};{owner}","es_ES"]'
)
assert wifi_sn in serials
assert owner in owners
assert wifi_sn.replace("/", "") in serials  # fallback adicional, nunca prioridad principal

# La prioridad debe seleccionar 1/5 con serial flexible antes de un valor
# genérico del servicio device-information.
ordered = sorted(
    [("OTHERDEVICEVALUE123", "LAN 1/2"), (wifi_sn, "LAN 1/5")],
    key=XiaomiE10MapV44._wifi_priority,
)
assert ordered[0] == (wifi_sn, "LAN 1/5")

# Roundtrip criptográfico completo con un RobotMap protobuf real.
rm = RobotMap.RobotMap()
rm.mapHead.mapHeadId = 77
rm.mapHead.sizeX = 20
rm.mapHead.sizeY = 30
rm.mapHead.resolution = 50
rm.currentPose.x = 1250
rm.currentPose.y = 2250
rm.currentPose.poseId = 9
rm.chargeStation.x = 1000
rm.chargeStation.y = 2000
p1 = rm.historyPose.points.add()
p1.x = 1000
p1.y = 2000
p2 = rm.historyPose.points.add()
p2.x = 1250
p2.y = 2250
payload = rm.SerializeToString()
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
quality = XiaomiE10MapV44._protobuf_quality(unpacked)
assert quality is not None and quality[0] >= 2
parsed_rm = quality[1]
assert parsed_rm.currentPose.x == 1250
assert parsed_rm.chargeStation.x == 1000
assert len(parsed_rm.historyPose.points) == 2

shape = XiaomiE10MapV44._shape(wifi_sn, "LAN 1/5")
assert shape["length"] == len(wifi_sn)
assert shape["slash"] is True
assert wifi_sn not in str(shape)

assert issubclass(app_v44.App, app_v44.app_v43.App)
print("SMOKE TEST V44 OK: wifi_sn con '/' + UID 7/45 + IJAI roundtrip + RobotMap")

import sys
from pathlib import Path
from types import SimpleNamespace

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v56
from xiaomi_e10_map_v56 import XiaomiE10MapV56


wifi = "ABCDEFGHIJ12345678"
owner = "1234567890"
did = "987654321"
mac = "AA:BB:CC:DD:EE:FF"

keys = dict(
    (label, key)
    for key, label in XiaomiE10MapV56._known_final_keys(wifi, owner, did, mac)
)
full_key = keys["md5-full-hex-bytes"]


def pack_2bpp(cells):
    out = bytearray()
    for i in range(0, len(cells), 4):
        chunk = list(cells[i:i + 4])
        while len(chunk) < 4:
            chunk.append(0)
        out.append(
            ((chunk[0] & 3) << 6)
            | ((chunk[1] & 3) << 4)
            | ((chunk[2] & 3) << 2)
            | (chunk[3] & 3)
        )
    return bytes(out)


# Rejilla 120x120 con una habitación rectangular y un corredor.
side = 120
cells = [0] * (side * side)
for y in range(52, 69):
    for x in range(48, 73):
        cells[y * side + x] = 1
for y in range(58, 62):
    for x in range(73, 91):
        cells[y * side + x] = 2

grid_raw = pack_2bpp(cells)
assert len(grid_raw) == 3600

field1 = b"1763778469"
field2 = b"0000000000"
body = len(field1).to_bytes(2, "big") + field1 + len(field2).to_bytes(2, "big") + field2
assert len(body) == 24
payload = bytes([0x06]) + (24).to_bytes(3, "big") + body + grid_raw
assert len(payload) == 3628

plain_hex = payload.hex().encode("ascii")
cipher = AES.new(full_key, AES.MODE_ECB).encrypt(pad(plain_hex, AES.block_size))
assert len(cipher) % 16 == 0

probe = XiaomiE10MapV56.__new__(XiaomiE10MapV56)
probe._ordered_key_material = lambda: (
    [(wifi, "LAN 1/5")],
    [(owner, "UID sufijo 7/45")],
    [(did, "settings.did")],
    [(mac, "miIO info")],
)

decoded = probe._decode_b112_payload(cipher)
assert decoded is not None
assert decoded["exact_b112_grid"] is True
assert decoded["payload"] == payload

header = XiaomiE10MapV56._parse_header(payload)
assert header["type"] == 0x06
assert header["length"] == 24
assert header["timestamp"] == 1763778469
assert header["grid_offset"] == 28

selected, alternatives = XiaomiE10MapV56._decode_grid(grid_raw)
assert len(selected["cells"]) == 14400
assert sum(v for k, v in selected["counts"].items() if int(k) != 0) > 0
assert len(alternatives) == 2

walls = XiaomiE10MapV56._grid_walls(selected["cells"], base_cell=(60.0, 60.0))
assert walls
assert all(len(w["points"]) >= 2 for w in walls)

# Diferencias temporales: primer grid sólo baseline; los siguientes dos cambios
# locales generan dos poses y permiten una trayectoria real por evolución de mapa.
tracker = XiaomiE10MapV56.__new__(XiaomiE10MapV56)
tracker._v56_prev_cells = None
tracker._v56_grid_track = []
tracker._v56_last_grid_pose = None
first = list(selected["cells"])
assert tracker._update_grid_track(first)["changed_cells"] == 0

second = list(first)
for y in range(61, 64):
    for x in range(88, 92):
        second[y * side + x] = 3
r2 = tracker._update_grid_track(second)
assert r2["accepted"] is True
assert len(tracker._v56_grid_track) == 1

third = list(second)
for y in range(63, 66):
    for x in range(91, 95):
        third[y * side + x] = 3
r3 = tracker._update_grid_track(third)
assert r3["accepted"] is True
assert len(tracker._v56_grid_track) == 2

# Refresco oficial: 10/18 no cambia el blob, 10/15(0) sí; 10/6 no debe ejecutarse.
class FakeDevice:
    def __init__(self):
        self.calls = []

    def call_action_by(self, siid, aiid, params):
        self.calls.append((siid, aiid, list(params)))
        return {"code": 0, "out": [{"piid": 18, "value": 1780000000}]}


refresh = XiaomiE10MapV56.__new__(XiaomiE10MapV56)
refresh.vacuum = SimpleNamespace(device=FakeDevice())
refresh.REFRESH_SETTLE_SECONDS = 0
refresh.map_privacy_state = lambda: 0
refresh.enable_map_upload_temporarily = lambda: True
refresh.last_v56_upload_diagnostics = {}
refresh.last_upload_diagnostics = {}

raw_a = b"A" * 32
raw_b = b"B" * 32
downloads = iter([
    (raw_a, "get_interim_file_url", 200),  # baseline
    (raw_a, "get_interim_file_url", 200),  # after 10/18
    (raw_b, "get_interim_file_url", 200),  # after 10/15
])
refresh._download_slot = lambda slot="0": next(downloads)

info = refresh.request_fresh_upload()
assert info["changed"] is True
assert info["winner"] == "10/15"
assert refresh.vacuum.device.calls == [
    (10, 18, []),
    (10, 15, [0]),
]

assert issubclass(app_v56.App, app_v56.app_v55.App)
print("SMOKE TEST V56 OK: upload oficial + AES full-MD5 + grid 120x120/2bpp + contornos + tracking temporal")

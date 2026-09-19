import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v91
from xiaomi_e10_map_v91 import XiaomiE10MapV91

for path in (
    SRC / "app_v91.py",
    SRC / "main_v91.py",
    SRC / "xiaomi_e10_map_v91.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v91.App, app_v91.app_v90.App)
assert app_v91.App.ROUTE_VISIBLE is False
assert XiaomiE10MapV91.GRID_RESOLUTION_M == 0.20

# Cabecera observada: type8 + version8 + length16be + 24 B + 3600 B.
body = (
    (10).to_bytes(2, "big") + b"1789785989"
    + (10).to_bytes(2, "big") + b"0000000000"
)
assert len(body) == 24
payload = bytes([0x0D, 0x01, 0x00, 0x18]) + body + bytes(3600)
assert len(payload) == 3628
header = XiaomiE10MapV91._parse_header(payload)
assert header is not None
assert header["type"] == 0x0D
assert header["version"] == 1
assert header["length"] == 24
assert header["grid_offset"] == 28
assert header["timestamp"] == 1789785989

# El fallback debe expandir una trayectoria y conservar continuidad.
snapshot = {
    "points": [
        {"x": 0.0, "y": 0.0},
        {"x": 0.5, "y": 0.0},
        {"x": 0.5, "y": 0.5},
        {"x": 0.0, "y": 0.5},
        {"x": 0.0, "y": 0.0},
    ]
}
legacy = app_v91.app_v90.App._v87_floor_cells(snapshot)
new = app_v91.App._v87_floor_cells(snapshot)
assert len(new) > len(legacy)
assert app_v91.App._v91_floor_bounds(snapshot) is not None

source = (SRC / "app_v91.py").read_text(encoding="utf-8")
decoder_source = (SRC / "xiaomi_e10_map_v91.py").read_text(encoding="utf-8")
for required in (
    "DIAGNÓSTICO V91 ACTIVO",
    "fallback reconstruido",
    "radio físico 0.18 m",
    "no cambia todavía RAW_TO_METERS",
):
    assert required in source, required
for required in (
    "type8-version8-len16be",
    "GRID_RESOLUTION_M = 0.20",
    "v12",
    "v23",
):
    assert required in decoder_source, required

print("SMOKE TEST V91 OK: cabecera 3628 decodificable + grid multicapa + fallback reconstruido")

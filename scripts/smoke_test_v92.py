import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v92
from xiaomi_e10_map_v92 import XiaomiE10MapV92

for path in (
    SRC / "app_v92.py",
    SRC / "main_v92.py",
    SRC / "xiaomi_e10_map_v92.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v92.App, app_v92.app_v91.App)
assert app_v92.App.ROUTE_VISIBLE is False

# Construye una habitación rectangular 30x24 codificada como bloques 2x2.
side = 120
cells = [0] * (side * side)
for y in range(45, 69):
    for x in range(43, 73):
        cells[y * side + x] = 2

raw = bytearray()
for by in range(60):
    for bx in range(60):
        coords = (
            (bx * 2, by * 2),
            (bx * 2 + 1, by * 2),
            (bx * 2, by * 2 + 1),
            (bx * 2 + 1, by * 2 + 1),
        )
        values = [cells[y * side + x] for x, y in coords]
        raw.append(
            (values[0] << 6)
            | (values[1] << 4)
            | (values[2] << 2)
            | values[3]
        )

selected, options = XiaomiE10MapV92._decode_grid(bytes(raw))
assert len(options) == 28 * 7
assert selected["metrics"]["valid"] is True
assert any(
    str(item["label"]).startswith("tile2-")
    and str(item["label"]).endswith("|v2")
    and item["metrics"]["valid"] is True
    for item in options
)

# La unión temporal debe convertir dos mitades contiguas en un conjunto mayor.
left = [0] * (side * side)
right = [0] * (side * side)
for y in range(50, 60):
    for x in range(50, 59):
        left[y * side + x] = 1
    for x in range(59, 68):
        right[y * side + x] = 1
merged = XiaomiE10MapV92._merge_binary_cells(left, right)
assert sum(left) == 90
assert sum(right) == 90
assert sum(merged) == 180
assert XiaomiE10MapV92._grid_metrics(merged)["nonzero"] == 180

# 255_255 nunca puede ser base geométrica.
base, fallback = XiaomiE10MapV92._valid_device_base_cell({"x": 255, "y": 255})
assert fallback is True
assert base == (60.0, 60.0)
base, fallback = XiaomiE10MapV92._valid_device_base_cell({"x": 61, "y": 58})
assert fallback is False
assert base == (61.0, 58.0)

source = (SRC / "xiaomi_e10_map_v92.py").read_text(encoding="utf-8")
app_source = (SRC / "app_v92.py").read_text(encoding="utf-8")
for required in (
    "_layout_horizontal4",
    "_layout_vertical4",
    "_layout_tile2",
    "itertools.permutations(range(4))",
    "_v92_accumulate",
    "255_255",
):
    assert required in source, required
for required in (
    "DIAGNÓSTICO V92 ACTIVO",
    "28 layouts físicos",
    "V57 sigue siendo el gate final",
):
    assert required in app_source, required

print("SMOKE TEST V92 OK: h4/v4/tile2 + 24 permutaciones + acumulación + base 255 protegida")

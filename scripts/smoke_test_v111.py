import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v111
import xiaomi_e10_map_v111

for path in (
    SRC / "app_v111.py",
    SRC / "main_v111.py",
    SRC / "xiaomi_e10_map_v111.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v111.App, app_v111.app_v110.App)

# El contrato classmethod debe soportar ambas llamadas sin convertir el dict en self.
assert isinstance(app_v111.App._v87_floor_cells({}), set)
assert isinstance(app_v111.App._v87_floor_cells(), set)

dummy = xiaomi_e10_map_v111.XiaomiE10MapV111.__new__(
    xiaomi_e10_map_v111.XiaomiE10MapV111
)
dummy._v111_area_raw = 69
dummy._v111_preferred_area_m2 = 6.9
dummy._v111_inferred_area_m2 = None
dummy._v111_inferred_scale = None
dummy._v111_reference_area_m2 = None
dummy._v110_target_area_m2 = None

# Trayectoria tipo raster de ~6-8 m²: el factor 0,1 debe ser mucho más
# plausible que 1 o 0,01 para raw=69.
path = []
for row in range(7):
    y = row * 0.42
    xs = [i * 0.25 for i in range(12)]
    if row % 2:
        xs.reverse()
    for x in xs:
        path.append((x, y))
dummy._v109_reference_path = path
target = dummy._v111_choose_target_area()
assert target is not None
assert abs(target - 6.9) < 0.001
assert abs(dummy._v111_inferred_scale - 0.1) < 1e-9

source = (SRC / "app_v111.py").read_text(encoding="utf-8")
for required in (
    "@classmethod\n    def _v87_floor_cells",
    "_v111_area_raw_max",
    "área retenida + F12 completo",
    "no se publica una planta",
):
    assert required in source, required

driver = (SRC / "xiaomi_e10.py").read_text(encoding="utf-8")
for required in (
    "_last_cleaning_area_raw",
    "self._value(7, 23)",
    "* 0.1",
):
    assert required in driver, required

print(
    "SMOKE TEST V111 OK: classmethod diagnostic contract + "
    "session area retention + raw scale inference + final area gate"
)

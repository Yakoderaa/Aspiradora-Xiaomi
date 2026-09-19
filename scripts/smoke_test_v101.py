import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v101

for path in (
    SRC / "app_v101.py",
    SRC / "main_v101.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v101.App, app_v101.app_v100.App)

dummy = app_v101.App.__new__(app_v101.App)
dummy._v101_transform_adapter_hits = 0

transform = {
    "scale": 100.0,
    "min_x": -2.0,
    "max_y": 2.0,
    "pad": 28.0,
    "pan_x": 10.0,
    "pan_y": -5.0,
}
xy = dummy._v87_xy(object(), transform)
assert callable(xy)
assert xy(0.0, 0.0) == (238.0, 223.0)
assert dummy._v101_transform_adapter_hits == 1

# El modo antiguo sigue funcionando como parser de puntos.
point = dummy._v87_xy({"x": 1.25, "y": -0.5})
assert point == (1.25, -0.5)

source = (SRC / "app_v101.py").read_text(encoding="utf-8")
for required in (
    'canvas.find_withtag(tag)',
    '"v88_xiaomi_floor"',
    "self._v88_draw_native_floor(",
    "self._v70_refresh_map_overview(force=True)",
    "0 objetos v88_xiaomi_floor",
    "corrigiendo el contrato roto heredado V88",
):
    assert required in source, required

# Regresión exacta: V88 llamaba _v87_xy(canvas, transform), mientras V87
# definía sólo _v87_xy(point). V101 debe conservar el adaptador dual.
v88 = (SRC / "app_v88.py").read_text(encoding="utf-8")
v87 = (SRC / "app_v87.py").read_text(encoding="utf-8")
assert "self._v87_xy(canvas, transform)" in v88
assert "def _v87_xy(point)" in v87
assert "def _v87_xy(self, point_or_canvas, transform=None)" in source

print(
    "SMOKE TEST V101 OK: fixed V88 transform contract + "
    "native-grid render guard + live thumbnail refresh"
)

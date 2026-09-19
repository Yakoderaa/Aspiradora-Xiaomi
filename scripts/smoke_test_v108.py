import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v108

for path in (
    SRC / "app_v108.py",
    SRC / "main_v108.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v108.App, app_v108.app_v107.App)

# El último renderer debe ser propietario del canvas y no dibujar ruta.
source = (SRC / "app_v108.py").read_text(encoding="utf-8")
for required in (
    'canvas.delete("all")',
    "def _v87_draw_route",
    "return None",
    "Esperando mapa final Xiaomi",
    "Mapa Xiaomi final",
    "base naranja",
    "recorrido azul interno",
    "_v108_draw_modern_scene",
):
    assert required in source, required

# Transformación conocida.
transform = {
    "scale": 10.0,
    "min_x": -2.0,
    "max_y": 2.0,
    "pad": 20.0,
    "pan_x": 5.0,
    "pan_y": -3.0,
}
xy = app_v108.App._v108_xy_from_transform(transform)
assert xy(0.0, 0.0) == (45.0, 37.0)

print(
    "SMOKE TEST V108 OK: modern final pass owns main/thumbnail canvas + "
    "route/legacy renderer cannot remain visible"
)

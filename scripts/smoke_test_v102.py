import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v102

for path in (
    SRC / "app_v102.py",
    SRC / "main_v102.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v102.App, app_v102.app_v101.App)

sig = inspect.signature(app_v102.App._v87_draw_rooms_and_plan)
assert list(sig.parameters) == [
    "self", "canvas", "snapshot", "xy", "transform"
]

dummy = app_v102.App.__new__(app_v102.App)
dummy._v102_rooms_contract_hits = 0
dummy.plan_store = None

# Regresión exacta V101: V88 entrega transform como cuarto argumento.
dummy._v87_draw_rooms_and_plan(
    object(),
    {},
    lambda x, y: (x, y),
    {"scale": 1.0},
)
assert dummy._v102_rooms_contract_hits == 1

source = (SRC / "app_v102.py").read_text(encoding="utf-8")
for required in (
    "def _v87_draw_rooms_and_plan(self, canvas, snapshot, xy, transform=None):",
    "super()._v87_draw_rooms_and_plan(canvas, snapshot, xy)",
    'canvas.tag_raise("v87_base")',
    'canvas.tag_raise("v87_robot")',
    'canvas.delete("v99_waiting")',
    "mapa Xiaomi en vivo",
    "la planta sigue saliendo del grid Xiaomi 120x120",
):
    assert required in source, required

print(
    "SMOKE TEST V102 OK: rooms contract fixed + "
    "base/robot overlays + Xiaomi live status"
)

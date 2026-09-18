import ast
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v76

source = (SRC / "app_v76.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v76.App, app_v76.app_v75.App)

# Regresión: V34 ya no puede insertar una segunda trayectoria.
app = app_v76.App.__new__(app_v76.App)
app._v34_last_relative = None
app._v34_motion_confirmed = False
app._v34_position_changes = 0
app._v76_duplicate_points_blocked = 0
app.MOTION_EPSILON = 0.015

assert app._record_relative_motion({"x": 0.0, "y": 0.0, "angle": 0.0}) == 0
assert app._record_relative_motion({"x": 1.0, "y": 0.0, "angle": 0.0}) == 0
assert app._v34_position_changes == 1
assert app._v76_duplicate_points_blocked == 1

# Detección de reversión: una dirección continua no es atasco oscilante.
one_way = [
    (0.0, 0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0, 0.3),
    (2.0, 0.0, 0.0, 0.6),
    (3.0, 0.0, 0.0, 0.9),
]
assert app._v76_turn_reversals(one_way, 0.08) == 0

oscillating = [
    (0.0, 0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0, 0.4),
    (2.0, 0.0, 0.0, -0.4),
    (3.0, 0.0, 0.0, 0.4),
    (4.0, 0.0, 0.0, -0.4),
]
assert app._v76_turn_reversals(oscillating, 0.08) >= 3

# Los umbrales V75 que dieron falso positivo (span=1.00, giro=5.3)
# quedan explícitamente por debajo de los nuevos requisitos V76.
assert app_v76.App.STALL_POSITION_SPAN < 1.0
assert app_v76.App.STALL_MIN_ANGLE_TRAVEL > 5.3
assert app_v76.App.STALL_MIN_SECONDS >= 24.0
assert app_v76.App.STALL_GRACE_AFTER_START_SECONDS >= 45.0
assert app_v76.App.STALL_MIN_DIRECTION_REVERSALS >= 3

for required in (
    "LocalMapStore recibe trayectoria sólo desde V73/V55",
    "STALL_GRACE_AFTER_START_SECONDS = 45.0",
    "STALL_POSITION_SPAN = 0.45",
    "STALL_MIN_DIRECTION_REVERSALS = 3",
    "_v76_reset_legacy_motion_state",
):
    assert required in source, required

print(
    "SMOKE TEST V76 OK: trayectoria única + reset legado + "
    "antiatasco con gracia/reversiones/tolerancia"
)

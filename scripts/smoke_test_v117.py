import ast
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v117

for path in (
    SRC / "app_v117.py",
    SRC / "main_v117.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v117.App, app_v117.app_v116.App)

pose = app_v117.App._v117_pose_from_state(
    {
        "charging_base": {"x": 60.0, "y": 60.0},
        "robot": {"x": 57.0, "y": 59.0, "angle": -3.048098},
    },
    5,
)
assert pose is not None
assert math.isclose(pose["x"], -0.3, abs_tol=1e-9), pose
assert math.isclose(pose["y"], 0.1, abs_tol=1e-9), pose
assert math.isclose(pose["angle"], 3.048098, abs_tol=1e-9), pose

dock_pose = app_v117.App._v117_pose_from_state(
    {
        "charging_base": {"x": 60.0, "y": 60.0},
        "robot": {"x": 57.0, "y": 59.0, "angle": 1.0},
    },
    4,
)
assert dock_pose == {"x": 0.0, "y": 0.0, "angle": 0.0}, dock_pose

source=(SRC / "app_v117.py").read_text(encoding="utf-8")
for required in (
    "Capturamos ANTES de V73",
    "_v117_snapshot_with_live_pose",
    "10/24 - 10/22",
    "Y reflejado como grid V107",
    "Hacer sonar/locate emitidos por ESTA app",
):
    assert required in source, required

assert "set_native_grid(" not in source
assert "arm_new_map(" not in source

print(
    "SMOKE TEST V117 OK: 10/24 vivo -> metros -> espejo Y -> "
    "overlay de robot sin mutar native_grid"
)

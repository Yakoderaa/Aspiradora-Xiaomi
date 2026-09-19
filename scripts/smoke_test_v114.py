import ast
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v114
import robot_plans
import xiaomi_e10


for path in (
    SRC / "app_v114.py",
    SRC / "main_v114.py",
    SRC / "robot_plans.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v114.App, app_v114.app_v113.App)

# Grid Xiaomi final simple: 4x4 celdas ocupadas alrededor del dock, 0.20 m.
side = 6
cells = [0] * (side * side)
for gy in range(1, 5):
    for gx in range(1, 5):
        cells[gy * side + gx] = 1

grid = {
    "side": side,
    "resolution": 0.20,
    "base_cell": [3.0, 3.0],
    "cells": cells,
}
target = {"x0": -0.40, "y0": -0.40, "x1": 0.40, "y1": 0.40}
block = {"x0": 0.00, "y0": -0.40, "x1": 0.40, "y1": 0.00}

safe = robot_plans.constrain_rect_to_native_grid(
    target,
    grid,
    no_go=[block],
    max_rectangles=24,
)
assert safe["selected_cells"] == 12, safe
assert safe["blocked_cells"] == 4, safe
assert math.isclose(safe["requested_area"], 0.64, abs_tol=1e-8)
assert math.isclose(safe["allowed_area"], 0.48, abs_tol=1e-8)
assert math.isclose(safe["coverage_ratio"], 0.75, abs_tol=1e-8)
assert len(safe["rectangles"]) >= 1

# Ningún rectángulo seguro puede invadir el bloqueo.
for rect in safe["rectangles"]:
    overlap = robot_plans._rect_intersection(rect, block)
    assert overlap is None, (rect, overlap)
    assert rect["x0"] >= target["x0"] - 1e-9
    assert rect["x1"] <= target["x1"] + 1e-9
    assert rect["y0"] >= target["y0"] - 1e-9
    assert rect["y1"] <= target["y1"] + 1e-9

plan = {"device_origin": {"x": 60.0, "y": 60.0}}
raw = robot_plans.local_rect_to_device(
    {"x0": -0.4, "y0": -0.2, "x1": 0.2, "y1": 0.4},
    plan,
)
assert math.isclose(raw["x0"], 56.0)
assert math.isclose(raw["y0"], 58.0)
assert math.isclose(raw["x1"], 62.0)
assert math.isclose(raw["y1"], 64.0)

assert robot_plans.native_grid_contains_point(
    {"x": -0.3, "y": 0.3},
    grid,
    no_go=[block],
)
assert not robot_plans.native_grid_contains_point(
    {"x": 0.2, "y": -0.2},
    grid,
    no_go=[block],
)

try:
    robot_plans.constrain_rect_to_native_grid(
        {"x0": 4.0, "y0": 4.0, "x1": 5.0, "y1": 5.0},
        grid,
    )
except RuntimeError:
    pass
else:
    raise AssertionError("Una zona fuera del mapa Xiaomi debe rechazarse")

# Guard duro: una limpieza dirigida activa bloquea cualquier build-map antes
# de que el método intente hablar con el dispositivo.
vacuum = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum._targeted_clean_guard = 1
vacuum._targeted_clean_blocked_mapping_calls = 0
vacuum._targeted_clean_last_blocked = None
try:
    vacuum.arm_new_map(1)
except RuntimeError as exc:
    assert "Seguridad V114" in str(exc)
else:
    raise AssertionError("arm_new_map debe bloquearse durante targeted clean")
assert vacuum._targeted_clean_blocked_mapping_calls == 1
assert vacuum._targeted_clean_last_blocked == "arm_new_map"

source = (SRC / "app_v114.py").read_text(encoding="utf-8")
for required in (
    "constrain_rect_to_native_grid",
    "_v114_restore_grid_if_needed",
    "_v114_target_clean_active",
    "_v114_map_switch_restores",
    "current_fp != original_fp",
    "self._zone_job_running = True",
    "mapa Xiaomi guardado queda congelado",
):
    assert required in source, required

# Una habitación local nunca debe salir por clean_rooms(room_id): esos IDs son
# nuestros, no IDs internos de Xiaomi.
assert "clean_rooms(" not in source

print(
    "SMOKE TEST V114 OK: native-grid clipping + blockers + raw coordinates + "
    "mapping guard + immutable saved map"
)

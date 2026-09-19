import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v93
from xiaomi_e10_map_v93 import XiaomiE10MapV93

for path in (
    SRC / "app_v93.py",
    SRC / "main_v93.py",
    SRC / "xiaomi_e10_map_v93.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v93.App, app_v93.app_v92.App)
assert app_v93.App.ROUTE_VISIBLE is False

side = XiaomiE10MapV93.GRID_SIDE

# 10/24 usa 0,10 m por unidad; el grid nativo usa 0,20 m por celda.
# Robot raw 66_53 respecto de dock 60_60 => +0,6/-0,7 m =>
# +3/-3,5 celdas sobre la base geométrica 60_60.
projected = XiaomiE10MapV93._physical_robot_grid_cell(
    {"x": 60, "y": 60},
    {"x": 66, "y": 53},
    (60.0, 60.0),
)
assert projected == (63.0, 56.5)
projected_sentinel = XiaomiE10MapV93._physical_robot_grid_cell(
    {"x": 255, "y": 255},
    {"x": 66, "y": 53},
    (60.0, 60.0),
)
assert projected_sentinel == (63.0, 56.5)

# Dos plantas igualmente válidas: el tie-break físico debe preferir la que
# contiene la base y la posición 10/24 actual.
near = [0] * (side * side)
far = [0] * (side * side)
for y in range(55, 65):
    for x in range(50, 70):
        near[y * side + x] = 1
    for x in range(80, 100):
        far[y * side + x] = 1

assert XiaomiE10MapV93._grid_metrics(near)["valid"] is True
assert XiaomiE10MapV93._grid_metrics(far)["valid"] is True

probe = object.__new__(XiaomiE10MapV93)
probe._v93_temporal_stats = {
    "near|nonzero": {
        "samples": 4,
        "robot_sum": 1.0,
        "robot_n": 4,
        "robot_hits": 4,
        "delta_sum": 2.0,
        "delta_n": 4,
        "delta_hits": 4,
        "changed_cells": 40,
    },
    "far|nonzero": {
        "samples": 4,
        "robot_sum": 40.0,
        "robot_n": 4,
        "robot_hits": 0,
        "delta_sum": 40.0,
        "delta_n": 4,
        "delta_hits": 0,
        "changed_cells": 40,
    },
}
near_item = {
    "layout": "near",
    "mask": "nonzero",
    "cells": near,
    "metrics": XiaomiE10MapV93._grid_metrics(near),
}
far_item = {
    "layout": "far",
    "mask": "nonzero",
    "cells": far,
    "metrics": XiaomiE10MapV93._grid_metrics(far),
}
near_score, near_diag = XiaomiE10MapV93._v93_score(
    probe, near_item, (60.0, 60.0), (61.0, 60.0)
)
far_score, far_diag = XiaomiE10MapV93._v93_score(
    probe, far_item, (60.0, 60.0), (61.0, 60.0)
)
assert near_score > far_score
assert near_diag["robot_distance"] <= 1.0
assert far_diag["robot_distance"] > 10.0

# Un apéndice 1-celda de ancho no debe deformar la planta si existe un núcleo
# grueso suficiente. La limpieza no puede romper la validez V57.
with_spur = list(near)
for x in range(70, 78):
    with_spur[60 * side + x] = 1
cleaned, clean_diag = XiaomiE10MapV93._clean_cells(
    with_spur,
    base_cell=(60.0, 60.0),
    robot_cell=(61.0, 60.0),
)
assert sum(cleaned) < sum(with_spur)
assert clean_diag["spurs_removed"] > 0
assert XiaomiE10MapV93._grid_metrics(cleaned)["valid"] is True

# Huecos completamente encerrados se rellenan.
with_hole = list(near)
with_hole[60 * side + 60] = 0
filled, filled_count = XiaomiE10MapV93._fill_enclosed_holes(with_hole)
assert filled[60 * side + 60] == 1
assert filled_count >= 1

source = (SRC / "xiaomi_e10_map_v93.py").read_text(encoding="utf-8")
app_source = (SRC / "app_v93.py").read_text(encoding="utf-8")
for required in (
    "_physical_robot_grid_cell",
    "_v93_note_frame",
    "_v93_score",
    "_clean_cells",
    "robot_hit_rate",
    "delta_hit_rate",
):
    assert required in source, required
for required in (
    "FINAL_DOCK_READS = 3",
    "_v81_completion_state",
    "_v84_close_mapping_on_dock",
    "v93_final_grid_done",
    "Mapa Xiaomi guardado",
):
    assert required in app_source, required

print(
    "SMOKE TEST V93 OK: ranking físico/temporal + limpieza conservadora "
    "+ grid válido como completitud + lecturas finales en dock"
)

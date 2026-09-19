import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v107
import xiaomi_e10_map_v107

for path in (
    SRC / "app_v107.py",
    SRC / "main_v107.py",
    SRC / "xiaomi_e10_map_v107.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v107.App, app_v107.app_v106.App)
assert issubclass(
    xiaomi_e10_map_v107.XiaomiE10MapV107,
    xiaomi_e10_map_v107.XiaomiE10MapV100,
)

assert app_v107.App.RENDER_MIN_INTERVAL_SECONDS == 1.50
assert app_v107.App.MAP_OVERVIEW_REFRESH_SECONDS == 12.0
assert app_v107.App.FINAL_DOCK_READS == 3

# Reflexión Y alrededor del dock: la base queda fija y filas opuestas se
# intercambian sin cambiar la cantidad de celdas.
side = 6
base = [3.0, 3.0]
cells = [0] * (side * side)
cells[1 * side + 2] = 1
cells[2 * side + 3] = 1
mirrored = xiaomi_e10_map_v107.XiaomiE10MapV107._v107_mirror_y(
    cells, side, base
)
assert sum(mirrored) == 2
assert mirrored[(2 * 3 - 1 - 1) * side + 2] == 1
assert mirrored[(2 * 3 - 2 - 1) * side + 3] == 1

dummy = app_v107.App.__new__(app_v107.App)
dummy._v107_final_candidates = 0
dummy._v107_final_unique = 0

g1 = {
    "side": 2, "resolution": 0.2, "base_cell": [1.0, 1.0],
    "cells": [1, 0, 0, 0],
}
g2 = {
    "side": 2, "resolution": 0.2, "base_cell": [1.0, 1.0],
    "cells": [1, 0, 0, 0],
}
g3 = {
    "side": 2, "resolution": 0.2, "base_cell": [1.0, 1.0],
    "cells": [1, 1, 0, 0],
}
chosen, reason = dummy._v107_choose_final_grid([g1, g2, g3])
assert chosen["cells"] == g2["cells"]
assert "repetido" in reason
assert dummy._v107_final_candidates == 3
assert dummy._v107_final_unique == 2

source = (SRC / "app_v107.py").read_text(encoding="utf-8")
for required in (
    "la planta se generará al finalizar",
    "surface live bloqueada",
    "cloud live bloqueado",
    "frame Xiaomi actual",
    "eje Y final se refleja",
    "MAP_OVERVIEW_REFRESH_SECONDS = 12.0",
):
    assert required in source, required

print(
    "SMOKE TEST V107 OK: final-current Xiaomi map + Y orientation + "
    "live-surface suppression + UI throttling"
)

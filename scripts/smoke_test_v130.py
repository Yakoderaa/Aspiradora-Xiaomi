from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v130.py")
local_mapping = text("src/local_mapping.py")
robot_plans = text("src/robot_plans.py")
map_client = text("src/xiaomi_e10_map_v130.py")
main = text("src/main_v130.py")
build = text("build.ps1")

assert "class App(app_v129.App)" in app
assert "10/24 antes de fase 1 perímetro V121" in app
assert "10/22 chargingbase al iniciar mapa · V130" in app
assert "_v130_capture_return_candidate_async" in app
assert "V130_DOCK_COLLAPSE_RATIO = 0.62" in app
assert "_v130_persist_late_return_candidate" in app
assert "Habitación rectangular" in app
assert "Habitación por puntos" in app
assert "Editar vértices" in app
assert "def clean_selected_point(self):" in app
assert "return None" in app[app.index("def clean_selected_point"):app.index("def _map_double_click")]
assert "constrain_polygon_to_native_grid" in app
assert "wait_for_cleaning_cycle(vacuum)" in app
assert "self._zone_job_running = False" in text("src/app_v114.py")
assert "def add_polygon_room" in local_mapping
assert "def update_polygon_room" in local_mapping
assert "def constrain_polygon_to_native_grid" in robot_plans
assert "class XiaomiE10MapV130(XiaomiE10MapV128)" in map_client
assert "import app_v130" in main
assert "app_v130.App().mainloop()" in main
assert "scripts\\smoke_test_v130.py" in build
assert any(f"src\\main_v{v}.py" in build for v in (130, 131, 132, 133, 134, 135))

# V130 no reintroduce comandos automáticos para antiatasco de Fase 2.
phase_watch = text("src/app_v129.py")
method = phase_watch[
    phase_watch.index("def _v127_try_phase2_recovery"):
    phase_watch.index("def _render_status")
]
for forbidden in (
    ".stop(",
    ".manual(",
    "_send_motor_start(",
    "start_mapping_whole_home(",
    ".dock(",
):
    assert forbidden not in method, forbidden

from local_mapping import LocalMapStore
from robot_plans import constrain_polygon_to_native_grid

with tempfile.TemporaryDirectory() as folder:
    store = LocalMapStore(Path(folder))
    room = store.add_polygon_room(
        "L",
        [(0.0, 0.0), (1.2, 0.0), (1.2, 0.4), (0.4, 0.4), (0.4, 1.2), (0.0, 1.2)],
    )
    assert room["shape"] == "polygon"
    assert len(room["polygon"]) == 6
    edited = store.update_polygon_room(
        room["id"],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],
    )
    assert len(edited["polygon"]) == 4
    assert store.snapshot()["rooms"][0]["shape"] == "polygon"

side = 20
cells = [0] * (side * side)
for gy in range(7, 14):
    for gx in range(7, 14):
        cells[gy * side + gx] = 1
grid = {
    "side": side,
    "resolution": 0.2,
    "base_cell": [10.0, 10.0],
    "cells": cells,
}
poly = [
    {"x": -0.5, "y": -0.5},
    {"x": 0.7, "y": -0.5},
    {"x": 0.7, "y": 0.1},
    {"x": 0.1, "y": 0.1},
    {"x": 0.1, "y": 0.7},
    {"x": -0.5, "y": 0.7},
]
constrained = constrain_polygon_to_native_grid(poly, grid)
assert constrained["selected_cells"] > 0
assert constrained["rectangles"]
assert constrained["requested_area"] > 0

print("V130 smoke OK")

import ast
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v110
import xiaomi_e10_map_v110
from cleaning_plan import CleaningPlanStore

for path in (
    SRC / "app_v110.py",
    SRC / "main_v110.py",
    SRC / "cleaning_plan.py",
    SRC / "xiaomi_e10_map_v110.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v110.App, app_v110.app_v109.App)
assert CleaningPlanStore.VERSION == 3

with tempfile.TemporaryDirectory() as folder:
    store = CleaningPlanStore(Path(folder))
    store.set_active_map("map-a")
    z1 = store.add_zone("Mesa", 0, 0, 1, 1, room_id="7")
    z2 = store.add_zone("Sillón", 1, 1, 2, 2, room_id="8")
    b1 = store.add_no_go("Cables", 0.2, 0.2, 0.4, 0.4, room_id="7")

    room7 = store.room_items("7", "map-a")
    assert [x["id"] for x in room7["zones"]] == [z1["id"]]
    assert [x["id"] for x in room7["no_go"]] == [b1["id"]]

    removed = store.delete_room_items("7", "map-a")
    assert removed == {"zones": 1, "no_go": 1}

    snap = store.snapshot("map-a")
    assert [x["id"] for x in snap["zones"]] == [z2["id"]]
    assert snap["no_go"] == []

# Escala física y selección por área.
assert app_v110.App.AUTO_PHYSICAL_SCALE_PX_PER_M == 72.0

dummy_map = xiaomi_e10_map_v110.XiaomiE10MapV110.__new__(
    xiaomi_e10_map_v110.XiaomiE10MapV110
)
dummy_map._v110_target_area_m2 = 9.6
dummy_map.GRID_RESOLUTION_M = 0.20

score_good, diag_good = dummy_map._v110_area_score(240)
score_bad, diag_bad = dummy_map._v110_area_score(85)
assert round(diag_good["grid_m2"], 2) == 9.60
assert round(diag_bad["grid_m2"], 2) == 3.40
assert score_good > score_bad

simple = [0] * 100
for y in range(3, 7):
    for x in range(3, 7):
        simple[y * 10 + x] = 1
topology = dummy_map._v110_topology(simple, 10)
assert topology["nonzero"] == 16
assert topology["holes"] == 0
assert topology["perimeter"] == 16

# Una zona debe estar completamente dentro de su habitación.
room = {"x0": 0, "y0": 0, "x1": 3, "y1": 3}
assert app_v110.App._v110_zone_inside_room(
    {"x0": 0.2, "y0": 0.2, "x1": 2.8, "y1": 2.8},
    room,
)
assert not app_v110.App._v110_zone_inside_room(
    {"x0": -0.5, "y0": 0.2, "x1": 1, "y1": 1},
    room,
)

source = (SRC / "app_v110.py").read_text(encoding="utf-8")
for required in (
    "Cada zona pertenece a una habitación",
    "Sin habitación no se pueden crear zonas",
    "delete_room_items",
    "Habitación activa",
    "Administrar mapas",
    "_v87_floor_cells(self, snapshot=None)",
    "AUTO_PHYSICAL_SCALE_PX_PER_M = 72.0",
    "Mi Home=",
):
    assert required in source, required

print(
    "SMOKE TEST V110 OK: room-owned zones + cascade delete + "
    "room switching + modern side panel + diagnostic compatibility + "
    "physical Mi Home scale"
)

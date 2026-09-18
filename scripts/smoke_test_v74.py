import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v74

source = (SRC / "app_v74.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v74.App, app_v74.app_v73.App)
assert "start_mapping_perimeter" not in source
assert "vacuum.arm_new_map(1)" in source
assert "vacuum.start_mapping_interior()" in source
assert 'step2.pack_forget()' in source
assert 'text="Recorrido"' in source
assert "NO_NEW_AREA_SECONDS = 240.0" in source
assert "MIN_MAPPING_SECONDS = 300.0" in source
assert "MIN_COVERAGE_CELLS = 35" in source
assert "_v74_request_finish_for_coverage" in source
assert "vacuum.dock()" in source

controller = (SRC / "xiaomi_e10.py").read_text(encoding="utf-8")
assert "self.set_water(0)" in controller
assert "self.set_suction(1)" in controller
assert "return self._start_mapping_sweep(0)" in controller

assert hasattr(app_v74.App, "_v73_schedule_recovery")
assert hasattr(app_v74.App, "_v73_start_dock_guard")

app = app_v74.App.__new__(app_v74.App)
app._v71_session_origin_raw = (10.0, 20.0)
app.vacuum = type(
    "FakeVacuum",
    (),
    {"parse_position": staticmethod(lambda value: {
        "x": float(str(value).split("_")[0]),
        "y": float(str(value).split("_")[1]),
        "angle": 0.0,
    })},
)()
parsed = app._v73_parse_pose("13_26_0")
assert parsed[:2] == (13.0, 26.0)
cell = (
    int(round((parsed[0] - 10.0) / app.MAP_CELL_SIZE)),
    int(round((parsed[1] - 20.0) / app.MAP_CELL_SIZE)),
)
assert cell == (1, 2)

print("SMOKE TEST V74 OK: sweep normal ECO + una sola capa + fin por cobertura + antiatasco/acople")

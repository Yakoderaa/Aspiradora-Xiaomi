import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v120
import xiaomi_e10


for path in (
    SRC / "app_v120.py",
    SRC / "main_v120.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v120.App, app_v120.app_v119.App)


class FakeDevice:
    def __init__(self):
        self.actions = []
        self.sets = []

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, params))
        return {"code": 0}

    def set_property_by(self, siid, piid, value):
        self.sets.append((siid, piid, value))
        return [{"code": 0}]


vacuum = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum.device = FakeDevice()
vacuum._last_mapping_exploration_diag = {}
vacuum._reject_mapping_during_targeted_clean = lambda operation: None
vacuum._prepare_mapping_vacuum = lambda: None
vacuum.set_sweep_type = lambda value: vacuum.device.set_property_by(2, 8, value)
vacuum._get_many = lambda defs: {"status": 5, "sweep_type": 2}

response = vacuum.start_mapping_exploration(confirm_timeout=0.5)
assert response == {"code": 0}
assert vacuum.device.actions == [(7, 3, ["", 2, 1])]
assert (2, 8, 2) in vacuum.device.sets
assert vacuum._last_mapping_exploration_diag["success"] is True
assert vacuum._last_mapping_exploration_diag["status_after"] == 5

source = (SRC / "app_v120.py").read_text(encoding="utf-8")
start_block = source.split("    def start_new_mapping(self):", 1)[1].split(
    "    def _handle_ui_event", 1
)[0]
assert "start_mapping_exploration" in start_block
assert "start_mapping_interior" not in start_block
assert "start_mapping_perimeter" not in start_block
assert "arm_new_map(1)" in start_block

print(
    "SMOKE TEST V120 OK: build-map -> única exploración Edge 7/3; "
    "sin sweep global normal ni segunda fase"
)

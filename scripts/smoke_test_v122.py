import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v122
import xiaomi_e10


for path in (
    SRC / "app_v122.py",
    SRC / "main_v122.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v122.App, app_v122.app_v121.App)


class FakeDevice:
    def __init__(self):
        self.actions = []
        self.sets = []

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, params))
        return {"code": 0, "out": []}

    def set_property_by(self, siid, piid, value):
        self.sets.append((siid, piid, value))
        return [{"code": 0}]


vacuum = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum.device = FakeDevice()
vacuum._targeted_clean_guard = 0
vacuum._global_clean_guard = 0
vacuum._motor_start_audit = []
vacuum._blocked_duplicate_starts = 0
vacuum._last_blocked_duplicate_start = None
vacuum._last_mapping_whole_home_diag = {}
vacuum._prepare_mapping_vacuum = lambda: None
vacuum.set_sweep_type = lambda value: vacuum.device.set_property_by(2, 8, value)
vacuum._get_many = lambda defs: {"status": 5, "sweep_type": 0}

response = vacuum.start_mapping_whole_home(confirm_timeout=0.5)
assert response == {"code": 0, "out": []}
assert vacuum.device.actions == [(7, 3, ["", 0, 1])]
assert (2, 8, 0) in vacuum.device.sets
assert vacuum._last_mapping_whole_home_diag["success"] is True
assert vacuum._last_mapping_whole_home_diag["status_after"] == 5

source = (SRC / "app_v122.py").read_text(encoding="utf-8")
phase2 = source.split(
    "    def _v121_request_phase2", 1
)[1].split(
    "    def _handle_ui_event", 1
)[0]
assert "start_mapping_whole_home" in phase2
assert "start_mapping_interior" not in phase2
assert "arm_new_map(" not in phase2
assert "7/3 ['', 0, 1]" in source

print(
    "SMOKE TEST V122 OK: Fase 2 usa whole-home 7/3 ['',0,1], "
    "sin start-sweep 2/1 y sin segundo build-map"
)

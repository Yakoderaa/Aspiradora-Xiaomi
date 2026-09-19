import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v123
import xiaomi_e10


for path in (
    SRC / "app_v123.py",
    SRC / "main_v123.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v123.App, app_v123.app_v122.App)


class FakeDevice:
    def __init__(self):
        self.actions = []
        self.sets = []

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, params))
        return {"id": len(self.actions), "exe_time": 0}

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

reads = {"n": 0}
def fake_get_many(defs):
    reads["n"] += 1
    # Primeras lecturas: 7/3 aceptado, pero sigue docked.
    # Después del trigger 2/3: confirma movimiento.
    if len(vacuum.device.actions) < 2:
        return {"status": 4, "sweep_type": 0}
    return {"status": 5, "sweep_type": 0}

vacuum._get_many = fake_get_many
response = vacuum.start_mapping_whole_home(confirm_timeout=1.0)

assert response["id"] == 2
assert vacuum.device.actions == [
    (7, 3, ["", 0, 1]),
    (2, 3, None),
]
assert not any(a[0] == 2 and a[1] == 1 for a in vacuum.device.actions)
assert vacuum._last_mapping_whole_home_diag["success"] is True
assert vacuum._last_mapping_whole_home_diag["trigger_sent"] is True
assert vacuum._last_mapping_whole_home_diag["started_by"] == (
    "7/3 whole-home + 2/3 trigger"
)
assert vacuum._last_mapping_whole_home_diag["status_after"] == 5

# Si 7/3 sí logra arrancar por sí solo, jamás se debe emitir 2/3.
vacuum2 = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum2.device = FakeDevice()
vacuum2._targeted_clean_guard = 0
vacuum2._global_clean_guard = 0
vacuum2._motor_start_audit = []
vacuum2._blocked_duplicate_starts = 0
vacuum2._last_blocked_duplicate_start = None
vacuum2._last_mapping_whole_home_diag = {}
vacuum2._prepare_mapping_vacuum = lambda: None
vacuum2.set_sweep_type = lambda value: vacuum2.device.set_property_by(2, 8, value)
vacuum2._get_many = lambda defs: {"status": 5, "sweep_type": 0}
vacuum2.start_mapping_whole_home(confirm_timeout=0.8)
assert vacuum2.device.actions == [(7, 3, ["", 0, 1])]
assert vacuum2._last_mapping_whole_home_diag["trigger_sent"] is False
assert vacuum2._last_mapping_whole_home_diag["started_by"] == "7/3 set-room-clean"

print(
    "SMOKE TEST V123 OK: whole-home se prepara por 7/3 y sólo si sigue "
    "docked se activa con 2/3; 2/1 queda prohibido"
)

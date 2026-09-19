import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v115
import xiaomi_e10


for path in (
    SRC / "app_v115.py",
    SRC / "main_v115.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v115.App, app_v115.app_v114.App)


class FakeDevice:
    def __init__(self, owner):
        self.owner = owner
        self.calls = []

    def call_action_by(self, siid, aiid, params=None):
        self.calls.append((siid, aiid, params))
        # El primer start por modo queda en charging; el fallback genérico
        # sí mueve físicamente el robot.
        if (siid, aiid) == (2, 1):
            self.owner.fake_status = 5
        return {"code": 0}

    def set_property_by(self, siid, piid, value):
        return [{"code": 0}]


class FakeStatus:
    def __init__(self, status):
        self.status = status


vacuum = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum.fake_status = 4
vacuum._last_global_start_diag = {}
vacuum.device = FakeDevice(vacuum)
vacuum.set_mode = lambda mode: None
vacuum.set_sweep_type = lambda sweep_type: None
vacuum._value = lambda siid, piid: vacuum.fake_status
vacuum.status = lambda: FakeStatus(vacuum.fake_status)

diag = vacuum.start_global_verified(0, confirm_timeout=0.15)
assert diag["success"] is True, diag
assert diag["method"] == "generic_start", diag
assert diag["status_after"] == 5, diag
assert vacuum.device.calls[0][:2] == (2, 3), vacuum.device.calls
assert vacuum.device.calls[1][:2] == (2, 1), vacuum.device.calls
assert all(call[:2] != (10, 17) for call in vacuum.device.calls)

source = (SRC / "app_v115.py").read_text(encoding="utf-8")
for required in (
    "start_global_verified",
    "_v115_global_clean_active",
    "_v115_live_grid_updates_blocked",
    "_v114_restore_grid_if_needed",
    "Limpiando…",
    "native_grid guardado queda congelado",
):
    assert required in source, required

print(
    "SMOKE TEST V115 OK: botón global verificado + fallback B112 + "
    "mapa Xiaomi inmutable durante limpieza"
)

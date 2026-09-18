import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v63
from xiaomi_e10_edge import XiaomiE10Edge
from xiaomi_e10_live import XiaomiE10Live


# XiaomiE10Live sigue usando la implementación EDGE real.
assert XiaomiE10Live.start_mapping_perimeter is XiaomiE10Edge.start_mapping_perimeter

vac = XiaomiE10Live.__new__(XiaomiE10Live)
events = []

class Device:
    def set_property_by(self, siid, piid, value, **kwargs):
        events.append(("set", siid, piid, value))
        return [{"code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        events.append(("action", siid, aiid, params))
        return {"code": 0}

vac.device = Device()
vac.arm_new_map = lambda mode=1: events.append(("arm", mode)) or {"success": True}
vac._prepare_mapping_vacuum = lambda: events.append(("prepare",))
vac.set_sweep_type = lambda value: events.append(("sweep", value))

result = vac.start_mapping_perimeter()
assert result == {"code": 0}
assert events[0] == ("arm", 1)
assert events[1] == ("prepare",)
assert ("action", 7, 3, ["", 2, 1]) in events
assert not any(e[0] == "set" and e[1:3] == (10, 1) for e in events)

assert issubclass(app_v63.App, app_v63.app_v62.App)

print("SMOKE TEST V63/V64 OK: ruta EDGE queda detrás del arm-new-map, no de 10/1")

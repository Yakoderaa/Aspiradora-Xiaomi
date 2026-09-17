import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v51
import app_v52
from xiaomi_e10_probe_v45 import XiaomiE10ProbeV45
from xiaomi_e10_probe_v52 import XiaomiE10ProbeV52


class FakeDevice:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call_action_by(self, siid, aiid, params=None):
        self.calls.append((int(siid), int(aiid), list(params or [])))
        if self.responses:
            return self.responses.pop(0)
        return {"code": 0, "out": []}


# 1) Una trayectoria real en el rango uint32 completo debe ganar inmediatamente.
probe = XiaomiE10ProbeV52.__new__(XiaomiE10ProbeV52)
probe.reset_live_path_session()
probe.device = FakeDevice([
    {
        "code": 0,
        "out": [{"piid": 5, "value": "[100,0,0,0,1,1,0,0,1]"}],
    }
])
raw, path, error, used_range = probe._get_path_by_action([], None)
assert error is None
assert used_range == (0, 4294967295)
assert len(path) == 2
assert probe._v52_full_distinct_xy == 2
assert probe._v52_full_accepted is True
assert probe._v52_fallback_used is False
assert probe.device.calls == [(10, 12, [0, 4294967295])]


# 2) Si el rango completo está vacío, debe volver al sondeo heredado y no inventar movimiento.
probe2 = XiaomiE10ProbeV52.__new__(XiaomiE10ProbeV52)
probe2.reset_live_path_session()
probe2.device = FakeDevice([
    {"code": 0, "out": [{"piid": 5, "value": "hello"}]},
    {"code": 0, "out": []},
])
probe2._read_documented_path_bounds = types.MethodType(lambda self: None, probe2)
raw2, path2, error2, used_range2 = probe2._get_path_by_action([], None)
assert path2 == []
assert probe2._v52_full_accepted is False
assert probe2._v52_fallback_used is True
assert used_range2 == (0, 256)
assert probe2.device.calls[0] == (10, 12, [0, 4294967295])
assert probe2.device.calls[1] == (10, 12, [0, 256])
assert all((siid, aiid) == (10, 12) for siid, aiid, _ in probe2.device.calls)


# 3) La consulta completa ocurre una sola vez por sesión; las siguientes usan fallback.
probe2._get_path_by_action([], None)
full_calls = [call for call in probe2.device.calls if call[2] == [0, 4294967295]]
assert len(full_calls) == 1

assert issubclass(XiaomiE10ProbeV52, XiaomiE10ProbeV45)
assert issubclass(app_v52.App, app_v51.App)
print("SMOKE TEST V52 OK: 10/12 uint32 completo una vez + fallback seguro + sin uploads")

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v62
from xiaomi_e10 import XiaomiE10
from xiaomi_e10_map_v62 import XiaomiE10MapV62


# 1) El normalizador V62 sigue aceptando todas las formas de respuesta.
row = {"siid": 10, "piid": 14, "code": 0, "value": 1}
assert XiaomiE10MapV62._result_rows([row]) == [row]
assert XiaomiE10MapV62._result_rows({"result": [row]}) == [row]
assert XiaomiE10MapV62._result_rows({"data": {"out": [row]}}) == [row]
assert XiaomiE10MapV62._result_rows(
    '{"result":[{"siid":10,"piid":14,"code":0,"value":1}]}'
)[0]["value"] == 1

# 2) La lectura LAN conserva seis campos y usa map_privacy.
p = XiaomiE10MapV62.__new__(XiaomiE10MapV62)
p._v60_lan_lock = threading.RLock()
p.last_v61_diagnostics = {}
p.last_v62_diagnostics = {}
p._v61_state = {}
p._v61_last_state_monotonic = 0.0
p.session_data = {}
p.did = "DID"
p.region = "sg"

class StateDevice:
    def send(self, method, payload):
        assert method == "get_properties"
        values = {
            (10, 1): 0,
            (10, 2): 0,
            (10, 3): 0,
            (10, 14): 1,
            (10, 19): 0,
            (10, 23): 0,
        }
        return [
            {"siid": siid, "piid": piid, "code": 0, "value": value}
            for (siid, piid), value in values.items()
        ]

p.vacuum = SimpleNamespace(device=StateDevice())
values, meta = p._read_state_lan()
assert meta["ok"] is True and meta["count"] == 6
assert values["remember_state"] == 0
assert values["build_map"] == 1
assert values["map_privacy"] == 0

# 3) El helper histórico remember-state sigue diagnosticable, pero ya no es
# parte de _prepare_mapping_vacuum.
class RejectRememberDevice:
    def set_property_by(self, *args, **kwargs):
        raise AssertionError("_prepare_mapping_vacuum no debe llamar set_property_by directamente")

vac = XiaomiE10.__new__(XiaomiE10)
vac.device = RejectRememberDevice()
side_effects = []
vac.set_map_remembering = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("remember-state no debe ser gate en V64")
)
vac.set_water = lambda value: side_effects.append(("water", value))
vac.set_suction = lambda value: side_effects.append(("suction", value))
vac.set_mode = lambda value: side_effects.append(("mode", value))
vac._prepare_mapping_vacuum()
assert side_effects == [("water", 0), ("suction", 1), ("mode", 0)]

assert issubclass(app_v62.App, app_v62.app_v61.App)

print("SMOKE TEST V62/V64 OK: parser de estado + remember-state ya no bloquea")

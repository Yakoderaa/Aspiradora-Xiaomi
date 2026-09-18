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


# 1) Regresión V61: el normalizador existe y acepta todas las formas usadas.
row = {"siid": 10, "piid": 1, "code": 0, "value": 1}
assert XiaomiE10MapV62._result_rows([row]) == [row]
assert XiaomiE10MapV62._result_rows({"result": [row]}) == [row]
assert XiaomiE10MapV62._result_rows({"data": {"out": [row]}}) == [row]
assert XiaomiE10MapV62._result_rows('{"result":[{"siid":10,"piid":1,"code":0,"value":1}]}')[0]["value"] == 1


# 2) La lectura LAN de V61 ya funciona sobre V62 y devuelve los seis campos.
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
            (10, 1): 1,
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
assert meta["ok"] is True
assert meta["count"] == 6
assert values["remember_state"] == 1
assert values["build_map"] == 1
assert values["map_uploads"] == 0


# 3) Setter verificado: sólo se considera éxito cuando la lectura devuelve 1.
class GoodDevice:
    def __init__(self):
        self.remember = 0
        self.set_calls = []

    def set_property_by(self, siid, piid, value, **kwargs):
        assert (siid, piid) == (10, 1)
        self.set_calls.append(("set_property_by", value, kwargs.get("name")))
        self.remember = int(value)
        return [{"code": 0}]

    def send(self, method, payload):
        assert method == "set_properties"
        self.set_calls.append(("send", payload[0]["value"], payload[0]["did"]))
        self.remember = int(payload[0]["value"])
        return [{"code": 0}]

    def get_property_by(self, siid, piid):
        assert (siid, piid) == (10, 1)
        return [{"code": 0, "value": self.remember}]

vac = XiaomiE10.__new__(XiaomiE10)
vac.device = GoodDevice()
result = vac.set_map_remembering(True, verify=True, retries=3)
assert result == 1
diag = vac.last_map_persistence_diag
assert diag["success"] is True
assert diag["before"] == 0
assert diag["after"] == 1
assert diag["attempts"][0]["verified"] is True


# 4) Si el firmware rechaza 10/1 o la lectura sigue en 0, se aborta.
class RejectDevice:
    def __init__(self):
        self.remember = 0

    def set_property_by(self, siid, piid, value, **kwargs):
        return [{"code": -4001}]

    def send(self, method, payload):
        return [{"code": -4001}]

    def get_property_by(self, siid, piid):
        return [{"code": 0, "value": self.remember}]

vac = XiaomiE10.__new__(XiaomiE10)
vac.device = RejectDevice()
failed = False
try:
    vac.set_map_remembering(True, verify=True, retries=3)
except RuntimeError as exc:
    failed = True
    assert "Cancelé el mapeo antes de mover el robot" in str(exc)
assert failed is True
assert vac.last_map_persistence_diag["success"] is False
assert vac.last_map_persistence_diag["after"] == 0


# 5) La preparación no toca agua/succión/modo si remember-state no se confirmó.
vac = XiaomiE10.__new__(XiaomiE10)
vac.device = RejectDevice()
side_effects = []
vac.set_water = lambda value: side_effects.append(("water", value))
vac.set_suction = lambda value: side_effects.append(("suction", value))
vac.set_mode = lambda value: side_effects.append(("mode", value))
failed = False
try:
    vac._prepare_mapping_vacuum()
except RuntimeError:
    failed = True
assert failed is True
assert side_effects == []


# 6) Con remember-state confirmado, la preparación continúa normalmente.
vac = XiaomiE10.__new__(XiaomiE10)
vac.device = GoodDevice()
side_effects = []
vac.set_water = lambda value: side_effects.append(("water", value))
vac.set_suction = lambda value: side_effects.append(("suction", value))
vac.set_mode = lambda value: side_effects.append(("mode", value))
vac._prepare_mapping_vacuum()
assert side_effects == [("water", 0), ("suction", 1), ("mode", 0)]


# 7) La UI V62 conserva la cadena y usa el cliente nuevo.
assert issubclass(app_v62.App, app_v62.app_v61.App)

print("SMOKE TEST V62 OK: _result_rows + remember-state set/readback + abort-before-motion")

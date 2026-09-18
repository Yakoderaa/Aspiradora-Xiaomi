import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v64
from xiaomi_e10_live import XiaomiE10Live
from xiaomi_e10_map_v64 import XiaomiE10MapV64


class GoodDevice:
    def __init__(self, reject_17=False, reject_11=False):
        self.events = []
        self.build_map = 0
        self.reject_17 = reject_17
        self.reject_11 = reject_11

    def send(self, method, payload):
        assert method == "get_properties"
        self.events.append(("get_properties",))
        values = {
            (10, 14): self.build_map,
            (10, 19): 0,
            (10, 23): 0,
        }
        result = []
        for item in payload:
            pair = (int(item["siid"]), int(item["piid"]))
            result.append({
                "did": item.get("did"),
                "siid": pair[0],
                "piid": pair[1],
                "code": 0,
                "value": values.get(pair, 0),
            })
        return result

    def set_property_by(self, siid, piid, value, **kwargs):
        if (siid, piid) == (10, 1):
            raise AssertionError("V64 jamás debe escribir remember-state 10/1")
        self.events.append(("set", siid, piid, value))
        return [{"code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        self.events.append(("action", siid, aiid, params))
        if (siid, aiid) == (10, 17):
            if self.reject_17:
                return {"code": -4001}
            self.build_map = 1
            return {"code": 0, "out": [{"piid": 18, "value": 1780000000}]}
        if (siid, aiid) == (10, 11):
            if self.reject_11:
                return {"code": -4001}
            self.build_map = 1
            return {"code": 0}
        if (siid, aiid) == (7, 3):
            return {"code": 0}
        raise AssertionError(f"acción inesperada {(siid, aiid, params)}")


def new_live(device):
    vac = XiaomiE10Live.__new__(XiaomiE10Live)
    vac.device = device
    return vac


# 1) Ruta feliz real: 10/17 aceptado, luego preparación ECO y recién después EDGE.
dev = GoodDevice()
vac = new_live(dev)
result = vac.start_mapping_perimeter()
assert result == {"code": 0}
assert vac.last_map_build_diag["success"] is True
assert vac.last_map_build_diag["winner"] == "build-map-ii"
assert vac.last_map_build_diag["attempts"][0]["code"] == 0
assert vac.last_map_build_diag["attempts"][0]["timestamp"] == 1780000000
assert vac.last_map_build_diag["attempts"][0]["build_map_readback"] == 1
assert not any(e[0] == "set" and e[1:3] == (10, 1) for e in dev.events)

build_i = dev.events.index(("action", 10, 17, [1]))
water_i = dev.events.index(("set", 7, 6, 0))
edge_i = dev.events.index(("action", 7, 3, ["", 2, 1]))
assert build_i < water_i < edge_i

# 2) Si 10/17 falla, usa exclusivamente el fallback documentado 10/11.
dev = GoodDevice(reject_17=True)
vac = new_live(dev)
vac.start_mapping_perimeter()
assert vac.last_map_build_diag["success"] is True
assert vac.last_map_build_diag["winner"] == "build-new-map"
assert ("action", 10, 17, [1]) in dev.events
assert ("action", 10, 11, [1]) in dev.events
assert dev.events.index(("action", 10, 11, [1])) < dev.events.index(("set", 7, 6, 0))

# 3) Si ambas acciones de creación son rechazadas, no se toca la preparación
# física ni se ejecuta EDGE.
dev = GoodDevice(reject_17=True, reject_11=True)
vac = new_live(dev)
failed = False
try:
    vac.start_mapping_perimeter()
except RuntimeError as exc:
    failed = True
    assert "Cancelé el recorrido antes de mover el robot" in str(exc)
assert failed is True
assert vac.last_map_build_diag["success"] is False
assert not any(e[0] == "set" for e in dev.events)
assert ("action", 7, 3, ["", 2, 1]) not in dev.events

# 4) El cliente V64 habilita realtime cuando la acción build fue aceptada aunque
# el readback 10/14 todavía llegue en 0.
class StateDevice:
    def send(self, method, payload):
        assert method == "get_properties"
        values = {
            (10, 1): 0,
            (10, 2): 0,
            (10, 3): 0,
            (10, 14): 0,
            (10, 19): 0,
            (10, 23): 0,
        }
        return [
            {
                "siid": int(item["siid"]),
                "piid": int(item["piid"]),
                "code": 0,
                "value": values[(int(item["siid"]), int(item["piid"]))],
            }
            for item in payload
        ]

p = XiaomiE10MapV64.__new__(XiaomiE10MapV64)
p._v60_lan_lock = threading.RLock()
p._v61_state = {}
p._v61_last_state_monotonic = 0.0
p.last_v61_diagnostics = {}
p.last_v62_diagnostics = {}
p.last_v64_diagnostics = {}
p.session_data = {}
p.did = "DID"
p.region = "sg"
p.vacuum = SimpleNamespace(
    device=StateDevice(),
    last_map_build_diag={
        "requested_mode": 1,
        "success": True,
        "winner": "build-map-ii",
        "attempts": [{"aiid": 17, "code": 0, "accepted": True}],
    },
)
state = p._probe_state(force=True)
assert state["status"] == "new_map_armed"
assert state["build_armed"] is True
assert state["privacy_enabled"] is True
assert state["allow_realtime_upload"] is True
assert p.last_v64_diagnostics["skip_realtime_upload"] is False

# 5) map-privacy=1 sigue bloqueando realtime incluso si build está armado.
class PrivateStateDevice(StateDevice):
    def send(self, method, payload):
        rows = super().send(method, payload)
        for row in rows:
            if (row["siid"], row["piid"]) == (10, 23):
                row["value"] = 1
        return rows

p._v61_state = {}
p._v61_last_state_monotonic = 0.0
p.vacuum = SimpleNamespace(
    device=PrivateStateDevice(),
    last_map_build_diag={"requested_mode": 1, "success": True, "winner": "build-map-ii"},
)
state = p._probe_state(force=True)
assert state["privacy_enabled"] is False
assert state["allow_realtime_upload"] is False

assert issubclass(app_v64.App, app_v64.app_v63.App)

print("SMOKE TEST V64 OK: build-map-ii/fallback + no remember-state + gate EDGE + realtime armado")

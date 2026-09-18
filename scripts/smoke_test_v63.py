import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v63
from xiaomi_e10_edge import XiaomiE10Edge
from xiaomi_e10_live import XiaomiE10Live


# 1) Regresión exacta: XiaomiE10Live hereda la ruta EDGE que V62 había dejado
# por fuera del gate de persistencia.
assert XiaomiE10Live.start_mapping_perimeter is XiaomiE10Edge.start_mapping_perimeter


class RejectDevice:
    def __init__(self):
        self.events = []
        self.remember = 0

    def get_property_by(self, siid, piid):
        self.events.append(("get", siid, piid, self.remember))
        return [{"code": 0, "value": self.remember}]

    def set_property_by(self, siid, piid, value, **kwargs):
        self.events.append(("set", siid, piid, value))
        if (siid, piid) == (10, 1):
            return [{"code": -4001}]
        raise AssertionError(f"V63 no debe tocar {siid}/{piid} si remember-state falla")

    def send(self, method, payload):
        self.events.append(("send", method, payload))
        if method == "set_properties":
            return [{"code": -4001}]
        raise AssertionError(f"método inesperado: {method}")

    def call_action_by(self, *args, **kwargs):
        self.events.append(("action", args, kwargs))
        raise AssertionError("EDGE 7/3 jamás debe ejecutarse sin 10/1=1")


# 2) Si 10/1 no se confirma, la ruta REAL de XiaomiE10Live aborta antes de
# agua/succión/modo/sweep-type y antes de cualquier acción.
vac = XiaomiE10Live.__new__(XiaomiE10Live)
vac.device = RejectDevice()
failed = False
try:
    vac.start_mapping_perimeter()
except RuntimeError as exc:
    failed = True
    assert "Cancelé el mapeo antes de mover el robot" in str(exc)
assert failed is True
assert vac.last_map_persistence_diag["success"] is False
assert not any(e[0] == "action" for e in vac.device.events)
assert not any(
    e[0] == "set" and (e[1], e[2]) in {(7, 6), (7, 5), (2, 4), (2, 8), (7, 1)}
    for e in vac.device.events
)


class GoodDevice:
    def __init__(self):
        self.events = []
        self.remember = 0

    def get_property_by(self, siid, piid):
        assert (siid, piid) == (10, 1)
        self.events.append(("get", siid, piid, self.remember))
        return [{"code": 0, "value": self.remember}]

    def set_property_by(self, siid, piid, value, **kwargs):
        self.events.append(("set", siid, piid, value))
        if (siid, piid) == (10, 1):
            self.remember = int(value)
        return [{"code": 0}]

    def send(self, method, payload):
        self.events.append(("send", method, payload))
        if method == "set_properties":
            self.remember = int(payload[0]["value"])
            return [{"code": 0}]
        raise AssertionError(f"método inesperado: {method}")

    def call_action_by(self, siid, aiid, params=None):
        self.events.append(("action", siid, aiid, params))
        return {"code": 0}


# 3) Con confirmación real, primero aparece write/readback 10/1=1 y recién
# después preparación ECO + acción EDGE 7/3.
vac = XiaomiE10Live.__new__(XiaomiE10Live)
vac.device = GoodDevice()
result = vac.start_mapping_perimeter()
assert result == {"code": 0}
assert vac.last_map_persistence_diag["success"] is True
assert vac.last_map_persistence_diag["after"] == 1
assert any(e[:4] == ("set", 10, 1, 1) for e in vac.device.events)
assert any(e[:4] == ("get", 10, 1, 1) for e in vac.device.events)
assert ("set", 7, 6, 0) in vac.device.events
assert ("set", 7, 5, 1) in vac.device.events
assert ("set", 2, 4, 0) in vac.device.events
assert ("action", 7, 3, ["", 2, 1]) in vac.device.events
write_i = next(i for i,e in enumerate(vac.device.events) if e[:4] == ("set", 10, 1, 1))
verify_i = next(i for i,e in enumerate(vac.device.events) if e[:4] == ("get", 10, 1, 1))
action_i = next(i for i,e in enumerate(vac.device.events) if e == ("action", 7, 3, ["", 2, 1]))
assert write_i < verify_i < action_i


# 4) La UI V63 conserva toda la cadena V62.
assert issubclass(app_v63.App, app_v63.app_v62.App)

print("SMOKE TEST V63 OK: XiaomiE10Live/Edge no alcanza 7/3 sin remember-state verificado")

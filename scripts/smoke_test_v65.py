import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v65
from xiaomi_e10_live import XiaomiE10Live


# 1) ACK simples: python-miio puede devolver directamente result=["ok"].
assert XiaomiE10Live._miot_action_ack(["ok"]) is True
assert XiaomiE10Live._miot_action_ack("OK") is True
assert XiaomiE10Live._miot_action_ack({"result": ["ok"]}) is True
assert XiaomiE10Live._miot_action_ack(None) is False
assert XiaomiE10Live._miot_action_ack([]) is False


class AckDevice:
    def __init__(self, first_response=["ok"], second_response=["ok"]):
        self.events = []
        self.first_response = first_response
        self.second_response = second_response

    def send(self, method, payload):
        assert method == "get_properties"
        values = {(10, 14): 0, (10, 19): 0, (10, 23): 0}
        return [
            {
                "did": item.get("did"),
                "siid": int(item["siid"]),
                "piid": int(item["piid"]),
                "code": 0,
                "value": values.get((int(item["siid"]), int(item["piid"])), 0),
            }
            for item in payload
        ]

    def set_property_by(self, siid, piid, value, **kwargs):
        if (siid, piid) == (10, 1):
            raise AssertionError("V65 no debe escribir remember-state 10/1")
        self.events.append(("set", siid, piid, value))
        return [{"code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        self.events.append(("action", siid, aiid, params))
        if (siid, aiid) == (10, 17):
            return self.first_response
        if (siid, aiid) == (10, 11):
            return self.second_response
        if (siid, aiid) == (7, 3):
            return ["ok"]
        raise AssertionError(f"acción inesperada {(siid, aiid, params)}")


def make_live(device):
    vac = XiaomiE10Live.__new__(XiaomiE10Live)
    vac.device = device
    return vac


# 2) Caso observado: 10/17 devuelve ["ok"] sin code/timestamp/readback.
# Debe considerarse ACK y NO debe disparar 10/11.
dev = AckDevice(first_response=["ok"])
vac = make_live(dev)
result = vac.start_mapping_perimeter()
assert result == ["ok"]
diag = vac.last_map_build_diag
assert diag["success"] is True
assert diag["winner"] == "build-map-ii"
first = diag["attempts"][0]
assert first["code"] is None
assert first["ack"] is True
assert first["accepted"] is True
assert first["response_type"] == "list"
assert "ok" in first["response_summary"].lower()
assert ("action", 10, 17, [1]) in dev.events
assert ("action", 10, 11, [1]) not in dev.events
assert ("action", 7, 3, ["", 2, 1]) in dev.events

# 3) Un rechazo explícito sí habilita fallback. El fallback ["ok"] se acepta.
dev = AckDevice(first_response={"code": -4001}, second_response=["ok"])
vac = make_live(dev)
vac.start_mapping_perimeter()
diag = vac.last_map_build_diag
assert diag["success"] is True
assert diag["winner"] == "build-new-map"
assert diag["attempts"][0]["accepted"] is False
assert diag["attempts"][1]["ack"] is True
assert diag["attempts"][1]["accepted"] is True
assert ("action", 10, 11, [1]) in dev.events

# 4) Un code negativo manda incluso si hubiera un "ok" anidado.
dev = AckDevice(first_response={"code": -4001, "result": ["ok"]}, second_response=["ok"])
vac = make_live(dev)
vac.start_mapping_perimeter()
assert vac.last_map_build_diag["winner"] == "build-new-map"
assert vac.last_map_build_diag["attempts"][0]["ack"] is True
assert vac.last_map_build_diag["attempts"][0]["accepted"] is False

# 5) None/vacío sin timestamp/readback nunca autoriza movimiento.
dev = AckDevice(first_response=None, second_response=[])
vac = make_live(dev)
failed = False
try:
    vac.start_mapping_perimeter()
except RuntimeError as exc:
    failed = True
    text = str(exc)
    assert "ack=False" in text
    assert "resp=None" in text
assert failed is True
assert ("action", 7, 3, ["", 2, 1]) not in dev.events

assert issubclass(app_v65.App, app_v65.app_v64.App)

print("SMOKE TEST V65 OK: ACK ['ok'] aceptado, rechazo explícito manda, None sigue bloqueado")

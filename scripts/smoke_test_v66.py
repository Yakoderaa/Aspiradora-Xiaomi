import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v66
from xiaomi_e10_live import XiaomiE10Live


# 1) Quirk exacto documentado para xiaomi.vacuum.b112:
# result vacío reparado por python-miio como dict con id + exe_time.
quirk = {"id": 2, "exe_time": 0}
assert XiaomiE10Live._miot_b112_empty_result_ack(quirk) is True
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": "12", "exe_time": 4.5}) is True

# Formas ambiguas o explícitamente erróneas no cuentan.
assert XiaomiE10Live._miot_b112_empty_result_ack(None) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": 2}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"exe_time": 0}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": 2, "exe_time": -1}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": 2, "exe_time": 0, "error": {"code": -1}}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": 2, "exe_time": 0, "code": -4001}) is False
assert XiaomiE10Live._miot_b112_empty_result_ack({"id": 2, "exe_time": 0, "result": ["unexpected"]}) is False


class B112QuirkDevice:
    def __init__(self, first_response=None, second_response=None):
        self.events = []
        self.first_response = {"id": 101, "exe_time": 0} if first_response is None else first_response
        self.second_response = {"id": 102, "exe_time": 0} if second_response is None else second_response

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
            raise AssertionError("V66 no debe escribir remember-state 10/1")
        self.events.append(("set", siid, piid, value))
        return [{"code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        self.events.append(("action", siid, aiid, params))
        if (siid, aiid) == (10, 17):
            return self.first_response
        if (siid, aiid) == (10, 11):
            return self.second_response
        if (siid, aiid) == (7, 3):
            return {"id": 103, "exe_time": 0}
        raise AssertionError(f"acción inesperada {(siid, aiid, params)}")


def make_live(device):
    vac = XiaomiE10Live.__new__(XiaomiE10Live)
    vac.device = device
    return vac


# 2) Caso exacto de la captura real: 10/17 devuelve sólo id + exe_time.
# Debe aceptarse y NO debe ejecutarse 10/11.
dev = B112QuirkDevice()
vac = make_live(dev)
result = vac.start_mapping_perimeter()
assert result == {"id": 103, "exe_time": 0}
diag = vac.last_map_build_diag
assert diag["success"] is True
assert diag["winner"] == "build-map-ii"
first = diag["attempts"][0]
assert first["code"] is None
assert first["ack"] is False
assert first["b112_empty_ack"] is True
assert first["accepted"] is True
assert first["response_type"] == "dict"
assert "exe_time" in first["response_summary"]
assert "id" in first["response_summary"]
assert ("action", 10, 17, [1]) in dev.events
assert ("action", 10, 11, [1]) not in dev.events
assert ("action", 7, 3, ["", 2, 1]) in dev.events

# 3) Un código negativo no puede quedar legitimado por id+exe_time.
dev = B112QuirkDevice(
    first_response={"id": 201, "exe_time": 0, "code": -4001},
    second_response={"id": 202, "exe_time": 0},
)
vac = make_live(dev)
vac.start_mapping_perimeter()
diag = vac.last_map_build_diag
assert diag["success"] is True
assert diag["winner"] == "build-new-map"
assert diag["attempts"][0]["b112_empty_ack"] is False
assert diag["attempts"][0]["accepted"] is False
assert diag["attempts"][1]["b112_empty_ack"] is True
assert diag["attempts"][1]["accepted"] is True
assert ("action", 10, 11, [1]) in dev.events

# 4) Si ambas respuestas son ambiguas, EDGE sigue bloqueado.
dev = B112QuirkDevice(first_response={"id": 301}, second_response={"exe_time": 0})
vac = make_live(dev)
failed = False
try:
    vac.start_mapping_perimeter()
except RuntimeError as exc:
    failed = True
    msg = str(exc)
    assert "b112-empty=False" in msg
assert failed is True
assert ("action", 7, 3, ["", 2, 1]) not in dev.events

assert issubclass(app_v66.App, app_v66.app_v65.App)

print("SMOKE TEST V66 OK: id+exe_time del B112 = ACK fuerte; fallback y bloqueo siguen seguros")

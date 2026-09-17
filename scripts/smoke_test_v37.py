import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from app_v37 import App
from xiaomi_cloud_telemetry import XiaomiCloudTelemetry


response = {
    "code": 0,
    "message": "",
    "result": [
        {"did": "123", "siid": 10, "piid": 2, "value": 0, "code": 0, "updateTime": 10},
        {"did": "123", "siid": 10, "piid": 5, "value": "hello", "code": 0, "updateTime": 11},
        {"did": "123", "siid": 10, "piid": 22, "value": "60_60", "code": 0, "updateTime": 12},
        {"did": "123", "siid": 10, "piid": 24, "value": "59_60_3.0", "code": 0, "updateTime": 13},
    ],
}

for wire_response in (
    response,
    json.dumps(response, separators=(",", ":")),
    json.dumps(response, separators=(",", ":")).encode("utf-8"),
    ("\ufeff" + json.dumps(response, separators=(",", ":"))).encode("utf-8"),
):
    decoded = XiaomiCloudTelemetry.decode_response(wire_response)
    assert decoded["values"]["robot_location"] == "59_60_3.0"
    assert decoded["values"]["charging_base"] == "60_60"
    assert decoded["meta"]["robot_location"]["updateTime"] == 13

assert App._xy_from_miot("59_60_3.0") == (59.0, 60.0)
assert App._xy_from_miot("60_60") == (60.0, 60.0)

print("smoke_test_v37 OK · dict/str/bytes")

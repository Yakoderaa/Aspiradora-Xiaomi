import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v47
import app_v48
from xiaomi_cloud_history_v48 import XiaomiCloudHistoryV48
from xiaomi_e10_map_v48 import XiaomiE10MapV48


class FakeDevice:
    def __init__(self, state):
        self.state = state
        self.set_calls = []

    def get_property_by(self, siid, piid):
        assert (siid, piid) == (10, 23)
        return [{"code": 0, "value": self.state}]

    def set_property_by(self, siid, piid, value):
        assert (siid, piid) == (10, 23)
        self.set_calls.append((siid, piid, value))
        self.state = value
        return [{"code": 0}]


class FakeVacuum:
    def __init__(self, state):
        self.device = FakeDevice(state)


def make_map_client(state):
    client = XiaomiE10MapV48.__new__(XiaomiE10MapV48)
    client.vacuum = FakeVacuum(state)
    client.privacy_original = None
    client.privacy_temporarily_enabled = False
    client.last_upload_diagnostics = {}
    client.last_v45_upload_diagnostics = {}
    client.active_map_id = lambda: (0, [])
    return client


# Reproduce el bug observado en V47: V45 limpiaba la bandera temporal durante
# request_fresh_upload aunque 10/23 ya hubiera cambiado 1 -> 0.
client = make_map_client(1)
assert client.enable_map_upload_temporarily() is True
assert client.vacuum.device.state == 0
assert client.privacy_original == 1
assert client.privacy_temporarily_enabled is True
result = client.request_fresh_upload()
assert result["skipped"] is True
assert result["privacy_temp"] is True
assert client.privacy_temporarily_enabled is True

# Incluso si una capa heredada pierde la bandera, V48 restaura por estado real.
client.privacy_temporarily_enabled = False
assert client.restore_map_privacy() is True
assert client.vacuum.device.state == 1
assert client.vacuum.device.set_calls[-1] == (10, 23, 1)

# Si el valor original era 0, nunca fuerza una restauración a 1.
already_enabled = make_map_client(0)
assert already_enabled.enable_map_upload_temporarily() is True
assert already_enabled.privacy_original == 0
assert already_enabled.restore_map_privacy() is False
assert already_enabled.vacuum.device.state == 0


class FakeCloud:
    def __init__(self):
        self.payloads = []

    def request_country(self, path, region, params):
        assert path == "/user/get_user_device_data"
        assert region == "sg"
        payload = json.loads(params["data"])
        self.payloads.append(payload)
        return {"code": 0, "message": "ok", "result": []}


probe = XiaomiCloudHistoryV48.__new__(XiaomiCloudHistoryV48)
probe.did = "fake-did"
probe.region = "sg"
probe.session_data = {"user_id": "12345"}
fake_cloud = FakeCloud()
probe._cloud = lambda: fake_cloud
summary = probe.read_probe(time.time() - 30)

assert summary["plans"] == 20
assert len(summary["queries"]) == 20
assert len(fake_cloud.payloads) == 20
assert summary["any_history"] is False
assert summary["total_records"] == 0
assert "phase|uid|prop:10.5" in summary["queries"]
assert "phase|no-uid|event:10.5" in summary["queries"]
assert "all|uid|event:cleaning-path" in summary["queries"]
assert "all|no-uid|prop:cur-cleaning-path" in summary["queries"]
assert any("uid" not in payload for payload in fake_cloud.payloads)
assert any(payload.get("uid") == "12345" for payload in fake_cloud.payloads)
assert all(payload["did"] == "fake-did" for payload in fake_cloud.payloads)

assert issubclass(app_v48.App, app_v47.App)

print("SMOKE TEST V48 OK: restore 10/23 robusto + sonda Cloud 20 variantes sólo lectura")

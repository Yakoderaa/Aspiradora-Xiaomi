import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v45
from xiaomi_e10_map_v45 import XiaomiE10MapV45
from xiaomi_e10_probe_v45 import XiaomiE10ProbeV45


class FakeLocalDevice:
    def __init__(self):
        self.action_calls = []

    def send(self, method, payload):
        assert method == "get_properties"
        result = []
        for item in payload:
            piid = item["piid"]
            value = {15: 100, 16: 101}.get(piid)
            result.append({"did": item["did"], "siid": 10, "piid": piid, "code": 0, "value": value})
        return result

    def call_action_by(self, siid, aiid, params):
        self.action_calls.append((siid, aiid, list(params)))
        assert (siid, aiid, list(params)) == (10, 12, [100, 101])
        return {
            "code": 0,
            "out": [{"piid": 5, "value": "[100,1,2,0,1,2,3,0,1]"}],
        }


probe = object.__new__(XiaomiE10ProbeV45)
probe.device = FakeLocalDevice()
probe._v45_bound_start_raw = None
probe._v45_bound_end_raw = None
probe._v45_bound_range = None
probe._v45_bound_source = ""
probe._v45_bound_action_code = None
probe._v45_bound_action_raw = None
probe._v45_bound_action_points = 0
probe._last_action_probe_range = None
probe._last_action_raw = None
probe._v45_base_anchor = {"x": 60.0, "y": 60.0, "angle": 0.0}
probe._v45_base_sentinels_ignored = 0
probe._v45_base_changes_ignored = 0

raw, path, error, used_range = probe._get_path_by_action([], None)
assert error is None
assert used_range == (100, 101)
assert probe.device.action_calls == [(10, 12, [100, 101])]
assert len(path) == 2
assert path[0]["id"] == 100 and path[1]["id"] == 101
assert probe._v45_bound_action_code == 0
assert probe._v45_bound_action_points == 2

state = {
    "charging_base": {"x": 255.0, "y": 255.0, "angle": 0.0},
}
probe._sanitize_base(state)
assert state["base_sentinel_ignored"] is True
assert state["charging_base"]["x"] == 60.0
assert state["charging_base"]["y"] == 60.0
assert probe._v45_base_sentinels_ignored == 1

assert app_v45.App._base_xy_valid((60, 60))
assert not app_v45.App._base_xy_valid((255, 255))
assert not app_v45.App._base_xy_valid({"x": 65535, "y": 65535})

app = object.__new__(app_v45.App)
app._v45_local_base_anchor = None
relative = app._relative_robot_from_state({
    "robot": {"x": 59.0, "y": 60.0, "angle": 3.0},
    "charging_base": {"x": 60.0, "y": 60.0, "angle": 0.0},
})
assert relative == {"x": -1.0, "y": 0.0, "angle": 3.0}
# La misma posición del robot con una base sentinela NO puede producir -196/-195.
assert app._relative_robot_from_state({
    "robot": {"x": 59.0, "y": 60.0, "angle": 3.0},
    "charging_base": {"x": 255.0, "y": 255.0, "angle": 0.0},
}) is None


class FakeMapClient(XiaomiE10MapV45):
    def __init__(self):
        self.vacuum = SimpleNamespace(device=SimpleNamespace(call_action_by=self._bad_call))
        self.last_upload_diagnostics = {}
        self.last_v45_upload_diagnostics = {}
        self.privacy_original = None
        self.privacy_temporarily_enabled = False
        self.calls = 0

    def _bad_call(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("No se debe llamar una acción de upload con map_id=0")

    def active_map_id(self):
        return 0, []

    def map_privacy_state(self):
        return 1


client = FakeMapClient()
info = client.request_fresh_upload()
assert info["skipped"] is True
assert info["map_id"] == 0
assert client.calls == 0
assert client.privacy_temporarily_enabled is False

print("SMOKE TEST V45 OK: sentinel 255_255 + base fija + 10/15-10/16 + upload seguro")

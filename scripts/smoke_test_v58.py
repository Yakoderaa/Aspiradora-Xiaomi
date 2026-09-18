import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v58
from xiaomi_e10_map_v58 import XiaomiE10MapV58


# ------------------------------------------------------ historial sin UID gana
probe = XiaomiE10MapV58.__new__(XiaomiE10MapV58)
probe.did = "did-123"
probe.region = "sg"
probe.session_data = {
    "user_id": "uid-456",
    "service_token": "token",
    "ssecurity": "secret",
}
probe.HISTORY_LIMIT = 80

calls = []
def fake_history_variant(endpoint, key, typ, start, end, include_uid):
    calls.append((endpoint, key, typ, include_uid))
    if (
        endpoint.endswith("get_user_device_data")
        and typ == "event"
        and include_uid is False
    ):
        return (
            [{
                "time": 1789700000,
                "value": [
                    {"piid": 30, "value": "/maps/final.bin"},
                ],
            }],
            {
                "endpoint": endpoint.rsplit("/", 1)[-1],
                "uid": False,
                "type": typ,
                "code": 0,
                "records": 1,
            },
        )
    return (
        [],
        {
            "endpoint": endpoint.rsplit("/", 1)[-1],
            "uid": bool(include_uid),
            "type": typ,
            "code": 0,
            "records": 0,
        },
    )

probe._history_request_variant = fake_history_variant
records, diags = probe._query_key("7.1", 0, 9999999999)
assert records, "la variante sin UID debe recuperar el evento"
assert any(item[0].endswith("no-uid") for item in records)
assert any(d.get("uid") is False and d.get("records") == 1 for d in diags)
assert any(d.get("uid") is True and d.get("records") == 0 for d in diags)

# --------------------------------------------------- Cloud action nested result
class FakeCloud:
    def request_country(self, endpoint, region, payload):
        assert endpoint in ("/miotspec/action", "/v2/miotspec/action")
        body = json.loads(payload["data"])
        assert body["params"]["did"] == "did-123"
        assert body["params"]["siid"] == 10
        assert body["params"]["aiid"] == 15
        assert body["params"]["in"] == [0]
        return {
            "code": 0,
            "result": {
                "did": "did-123",
                "siid": 10,
                "aiid": 15,
                "code": 0,
                "out": [
                    {"piid": 6, "value": 31415},
                    {"piid": 7, "value": 0},
                    {"piid": 18, "value": 1789701234},
                    {"piid": 21, "value": 1},
                ],
            },
        }

probe._cloud = lambda: FakeCloud()
action = probe._call_cloud_action(15, [0], "upload-by-maptype-ii")
assert action["ok"] is True
assert action["map_id"] == 31415
assert action["map_type"] == 0
assert action["timestamp"] == 1789701234
assert action["renew_map"] == 1

# ------------------------------------------- FDS candidate distinto y decodifica
snapshot = SimpleNamespace(raw_robot=(1.0, 2.0), raw_base=(0.0, 0.0), raw_path=[])
probe._v58_fresh_snapshot = None
probe._v58_fresh_meta = {}
probe._download_candidate_reference = lambda source, reference: (
    b"fresh-map-payload",
    "get_interim_file_url",
    200,
)
probe._decode_any_map = lambda raw, label, endpoint: (
    snapshot,
    [{"name": "synthetic", "ok": True}],
)
snap, pdiag = probe._probe_action_candidates(
    "0a0ad83e5049",
    action,
)
assert snap is snapshot
assert probe._v58_fresh_snapshot is snapshot
assert probe._v58_fresh_meta["source"] in ("map-id", "timestamp", "map-id_timestamp", "timestamp_map-id")
assert any(p.get("ok") for p in pdiag)

# ---------------------------------------------------------- cached map wins load
probe.last_v57_diagnostics = {}
returned = probe.load()
assert returned is snapshot
assert probe._v58_fresh_snapshot is None
assert probe.last_v57_diagnostics["source"] == "v58-fresh"

# --------------------------------------------------------------- source guard
source = inspect.getsource(XiaomiE10MapV58.request_fresh_upload)
for required in ("(18, []", "(15, [0]", "(6, [0]"):
    assert required in source
assert "10, 14" not in source
assert "10, 2" not in source

assert issubclass(app_v58.App, app_v58.app_v57.App)
print("SMOKE TEST V58 OK: no-uid history + Cloud action + FDS candidate + cached fresh map")

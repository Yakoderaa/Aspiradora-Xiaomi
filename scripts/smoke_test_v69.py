import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v69
from xiaomi_e10_map_v69 import XiaomiE10MapV69


# 1) Spec B112: battery sólo expone 3/1. Nunca se consulta 3/2.
class ProbeVacuum:
    def __init__(self):
        self.defs = None

    def _get_many(self, defs):
        self.defs = list(defs)
        return {
            "status": 3,
            "fault": 0,
            "battery": 32,
            "robot": "19_59_-0.17",
            "charging_base": "60_60",
        }

    @staticmethod
    def parse_position(value):
        parts = str(value).split("_")
        if len(parts) >= 2:
            return {"x": float(parts[0]), "y": float(parts[1]), "angle": 0.0}
        return None


vac = ProbeVacuum()
state = app_v69.App._v69_read_base_state(vac)
assert state["status"] == 3
assert ("battery", 3, 1) in vac.defs
assert all(not (siid == 3 and piid == 2) for _name, siid, piid in vac.defs)

edge_vac = ProbeVacuum()
edge = app_v69.App._v68_read_edge_state(edge_vac)
assert edge["status"] == 3
assert edge["charging_state"] is None
assert all(not (siid == 3 and piid == 2) for _name, siid, piid in edge_vac.defs)


# 2) Status=4 sigue siendo confirmación directa.
mode, reason = app_v69.App._v69_fallback_reason(
    status=4,
    fault=0,
    saw_returning=True,
    return_elapsed=2,
    dock_reasserted=False,
    pose_stable_seconds=0,
    battery_start=32,
    battery_now=32,
)
assert mode == "direct"
assert "status=4" in reason


# 3) No autorizar status=3 demasiado pronto.
mode, reason = app_v69.App._v69_fallback_reason(
    status=3,
    fault=0,
    saw_returning=True,
    return_elapsed=40,
    dock_reasserted=True,
    pose_stable_seconds=30,
    battery_start=32,
    battery_now=32,
)
assert mode is None
assert reason is None


# 4) El fallback real exige retorno prolongado + dock + fault=0 + pose estable.
mode, reason = app_v69.App._v69_fallback_reason(
    status=3,
    fault=0,
    saw_returning=True,
    return_elapsed=80,
    dock_reasserted=True,
    pose_stable_seconds=25,
    battery_start=32,
    battery_now=32,
)
assert mode == "stale-return"
assert "status=3" in reason

# Con fault activo, jamás autoriza.
mode, _ = app_v69.App._v69_fallback_reason(
    status=3,
    fault=17,
    saw_returning=True,
    return_elapsed=200,
    dock_reasserted=True,
    pose_stable_seconds=100,
    battery_start=32,
    battery_now=32,
)
assert mode is None


# 5) Subida de batería es evidencia fuerte aun si status queda clavado en 3.
mode, reason = app_v69.App._v69_fallback_reason(
    status=3,
    fault=0,
    saw_returning=True,
    return_elapsed=20,
    dock_reasserted=False,
    pose_stable_seconds=0,
    battery_start=32,
    battery_now=33,
)
assert mode == "battery-rise"
assert "32→33" in reason


# 6) clean-end: placeholders no son candidatos FDS.
assert XiaomiE10MapV69._v69_ref_kind("cloud") == "placeholder"
assert XiaomiE10MapV69._v69_ref_kind("hello") == "placeholder"
assert XiaomiE10MapV69._v69_ref_kind("https://example.invalid/map") == "http"
assert XiaomiE10MapV69._v69_ref_kind("folder/object.record") == "path"
assert XiaomiE10MapV69._v69_ref_kind("1234567890") == "object"
assert XiaomiE10MapV69._v69_ref_usable("cloud") is False
assert XiaomiE10MapV69._v69_ref_usable("folder/object.record") is True


# 7) La consulta quick debe seguir buscando si PIID30 sólo dice "cloud",
# y aceptar una referencia anidada real en una variante posterior.
client = XiaomiE10MapV69.__new__(XiaomiE10MapV69)
client._v57_session_started_at = 0.0
client.last_v60_diagnostics = {}
client.last_v69_clean_end_diagnostics = {}

calls = []
records_by_endpoint = {
    "/v2/user/get_user_device_data": [
        {"time": 100, "out": [{"piid": 30, "value": "cloud"}]},
    ],
    "/user/get_user_device_data": [
        {
            "time": 101,
            "out": [{"piid": 30, "value": "cloud"}],
            "file_url": "folder/real-map.record",
        },
    ],
}

def fake_history(endpoint, key, typ, start, end, include_uid):
    calls.append(endpoint)
    rows = records_by_endpoint.get(endpoint, [])
    return rows, {
        "endpoint": endpoint.rsplit("/", 1)[-1],
        "uid": bool(include_uid),
        "type": typ,
        "code": 0,
        "records": len(rows),
    }

client._history_request_variant = fake_history

refs = client._clean_end_quick()
assert len(calls) >= 2
assert refs
assert all(ref != "cloud" for _source, ref, _priority in refs)
assert any(ref == "folder/real-map.record" for _source, ref, _priority in refs)
assert client.last_v69_clean_end_diagnostics["ref_shapes"]["placeholder"] >= 1
assert client.last_v69_clean_end_diagnostics["usable_refs"] >= 1


assert issubclass(app_v69.App, app_v69.app_v68.App)
assert issubclass(XiaomiE10MapV69, XiaomiE10MapV69.__mro__[1])

print("SMOKE TEST V69 OK: B112 sin 3/2 + retorno conservador + clean-end saneado")

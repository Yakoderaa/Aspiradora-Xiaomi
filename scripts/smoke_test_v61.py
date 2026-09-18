import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v61
from xiaomi_e10 import XiaomiE10
from xiaomi_e10_ijai_map import IjaiMapSnapshot
from xiaomi_e10_map_v61 import XiaomiE10MapV61


# 1) Semántica de estado: el diagnóstico real V60 (todo en cero +
# remember-state=0) significa que no hay mapa persistente y el guardado está OFF.
state = XiaomiE10MapV61._classify_state({
    "remember_state": 0,
    "cur_map_id": 0,
    "map_num": 0,
    "build_map": 0,
    "has_new_map": 0,
    "map_uploads": 0,
})
assert state["status"] == "no_saved_map_remember_off"
assert state["remember_enabled"] is False
assert state["uploads_enabled"] is True
assert state["allow_realtime_upload"] is False

# 2) Tras activar remember-state, sin mapa todavía esperamos el primer guardado;
# no inventamos un map-id ni disparamos upload-by-mapid.
state = XiaomiE10MapV61._classify_state({
    "remember_state": 1,
    "cur_map_id": 0,
    "map_num": 0,
    "build_map": 0,
    "has_new_map": 0,
    "map_uploads": 0,
})
assert state["status"] == "recording_waiting_for_first_map"
assert state["allow_realtime_upload"] is False

# 3) Un cur-map-id/map-num real habilita la ruta V60/FDS.
state = XiaomiE10MapV61._classify_state({
    "remember_state": 1,
    "cur_map_id": 1707156242,
    "map_num": 1,
    "build_map": 0,
    "has_new_map": 0,
    "map_uploads": 0,
})
assert state["status"] == "saved_map_available"
assert state["saved_map"] is True
assert state["allow_realtime_upload"] is True

# 4) 10/23 es map-uploads: 0 Upload, 1 Do Not Upload.
off = XiaomiE10MapV61._classify_state({"map_uploads": 1})
on = XiaomiE10MapV61._classify_state({"map_uploads": 0})
assert off["uploads_enabled"] is False
assert on["uploads_enabled"] is True

# 5) El mapeo iniciado por el usuario activa remember-state=1.
calls = []
class Device:
    def set_property_by(self, siid, piid, value, **kwargs):
        calls.append((siid, piid, value))
        return [{"code": 0}]
    def get_property_by(self, siid, piid):
        value = calls[-1][2] if calls else 0
        return [{"code": 0, "value": value}]

vac = XiaomiE10.__new__(XiaomiE10)
vac.device = Device()
vac.set_map_remembering(True)
assert calls == [(10, 1, 1)]
vac.set_map_remembering(False)
assert calls[-1] == (10, 1, 0)

# 6) _prepare_mapping_vacuum activa persistencia antes de preparar agua/succión/modo.
vac = XiaomiE10.__new__(XiaomiE10)
order = []
vac.set_map_remembering = lambda enabled=True, **kwargs: order.append(("remember", enabled))
vac.set_water = lambda level: order.append(("water", level))
vac.set_suction = lambda level: order.append(("suction", level))
vac.set_mode = lambda mode: order.append(("mode", mode))
vac._prepare_mapping_vacuum()
assert order[0] == ("remember", True)
assert ("water", 0) in order
assert ("suction", 1) in order
assert ("mode", 0) in order

# 7) Lectura LAN de estado usa exclusivamente propiedades conocidas.
p = XiaomiE10MapV61.__new__(XiaomiE10MapV61)
p._v60_lan_lock = threading.RLock()
p.last_v61_diagnostics = {}
p._v61_state = {}
p._v61_last_state_monotonic = 0.0
p.session_data = {}
p.did = "DID"
p.region = "sg"
class StateDevice:
    def send(self, method, payload):
        assert method == "get_properties"
        pairs = {(int(x["siid"]), int(x["piid"])) for x in payload}
        assert (10, 1) in pairs and (10, 23) in pairs
        values = {(10, 1): 0, (10, 2): 0, (10, 3): 0, (10, 14): 0, (10, 19): 0, (10, 23): 0}
        return [
            {"siid": siid, "piid": piid, "code": 0, "value": values[(siid, piid)]}
            for siid, piid in sorted(values)
        ]
p.vacuum = SimpleNamespace(device=StateDevice())
values, meta = p._read_state_lan()
assert values["remember_state"] == 0
assert values["map_uploads"] == 0
assert meta["ok"] is True

# 8) Sin mapa guardado request_fresh_upload se omite y no llama acciones.
p._probe_state = lambda force=False: {
    "status": "no_saved_map_remember_off",
    "cur_map_id": 0,
    "allow_realtime_upload": False,
}
p.last_v61_diagnostics = {"skip_reason": "sin mapa guardado"}
info = p.request_fresh_upload()
assert info["skipped"] is True
assert info["official_actions"] is False
assert info["map_id"] == 0

# 9) Sin mapa persistente load sólo permite clean-end final y no entra a V60.
p._probe_state = lambda force=False: {
    "status": "recording_waiting_for_first_map",
    "allow_realtime_upload": False,
}
p._load_record_map = lambda: (None, {"success": False, "candidates": 0})
snapshot = p.load()
assert isinstance(snapshot, IjaiMapSnapshot)
assert "esperando primer mapa persistente" in str(snapshot.parser_error)

# 10) UI V61 conserva toda la cadena anterior y usa cliente V61.
assert issubclass(app_v61.App, app_v61.app_v60.App)

print("SMOKE TEST V61 OK: remember-state + map-uploads + gating FDS + clean-end seguro")

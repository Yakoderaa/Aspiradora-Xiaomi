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


# 1) En el B112 exacto, remember-state es informativo y 10/23 es map-privacy.
idle0 = XiaomiE10MapV61._classify_state({
    "remember_state": 0,
    "cur_map_id": 0,
    "map_num": 0,
    "build_map": 0,
    "has_new_map": 0,
    "map_privacy": 0,
})
idle1 = XiaomiE10MapV61._classify_state({
    "remember_state": 1,
    "cur_map_id": 0,
    "map_num": 0,
    "build_map": 0,
    "has_new_map": 0,
    "map_privacy": 0,
})
assert idle0["status"] == "no_saved_map_idle"
assert idle1["status"] == "no_saved_map_idle"
assert idle0["privacy_enabled"] is True
assert idle0["allow_realtime_upload"] is False

# 2) build-map activo habilita la ruta realtime aunque aún no exista cur-map-id.
building = XiaomiE10MapV61._classify_state({
    "remember_state": 0,
    "cur_map_id": 0,
    "map_num": 0,
    "build_map": 1,
    "has_new_map": 0,
    "map_privacy": 0,
})
assert building["status"] == "firmware_building_map"
assert building["building"] is True
assert building["allow_realtime_upload"] is True

# 3) map-privacy=1 bloquea subida incluso durante build.
private = XiaomiE10MapV61._classify_state({
    "build_map": 1,
    "map_privacy": 1,
})
assert private["privacy_enabled"] is False
assert private["allow_realtime_upload"] is False

# 4) Un mapa guardado o pendiente habilita la ruta cuando privacy lo permite.
saved = XiaomiE10MapV61._classify_state({
    "cur_map_id": 1707156242,
    "map_num": 1,
    "map_privacy": 0,
})
pending = XiaomiE10MapV61._classify_state({
    "has_new_map": 1,
    "map_privacy": 0,
})
assert saved["saved_map"] is True and saved["allow_realtime_upload"] is True
assert pending["pending_map"] is True and pending["allow_realtime_upload"] is True

# 5) La preparación física ya no toca remember-state.
vac = XiaomiE10.__new__(XiaomiE10)
order = []
vac.set_map_remembering = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("V64 no debe escribir remember-state durante _prepare_mapping_vacuum")
)
vac.set_water = lambda level: order.append(("water", level))
vac.set_suction = lambda level: order.append(("suction", level))
vac.set_mode = lambda mode: order.append(("mode", mode))
vac._prepare_mapping_vacuum()
assert order == [("water", 0), ("suction", 1), ("mode", 0)]

# 6) Lectura LAN usa el nombre exacto map_privacy.
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
        values = {
            (10, 1): 0,
            (10, 2): 0,
            (10, 3): 0,
            (10, 14): 1,
            (10, 19): 0,
            (10, 23): 0,
        }
        return [
            {"siid": siid, "piid": piid, "code": 0, "value": value}
            for (siid, piid), value in values.items()
        ]

p.vacuum = SimpleNamespace(device=StateDevice())
values, meta = p._read_state_lan()
assert meta["ok"] is True
assert values["remember_state"] == 0
assert values["build_map"] == 1
assert values["map_privacy"] == 0
assert "map_uploads" not in values

# 7) Sin mapa/build, request_fresh_upload se omite.
p._probe_state = lambda force=False: {
    "status": "no_saved_map_idle",
    "cur_map_id": 0,
    "allow_realtime_upload": False,
}
p.last_v61_diagnostics = {"skip_reason": "sin mapa/build"}
info = p.request_fresh_upload()
assert info["skipped"] is True
assert info["official_actions"] is False

# 8) Sin mapa/build, load conserva la ruta clean-end y devuelve espera segura.
p._probe_state = lambda force=False: {
    "status": "no_saved_map_idle",
    "allow_realtime_upload": False,
}
p._load_record_map = lambda: (None, {"success": False, "candidates": 0})
snapshot = p.load()
assert isinstance(snapshot, IjaiMapSnapshot)
assert "esperando mapa real" in str(snapshot.parser_error)

assert issubclass(app_v61.App, app_v61.app_v60.App)

print("SMOKE TEST V61/V64 OK: map-privacy exacto + build-map + remember informativo")

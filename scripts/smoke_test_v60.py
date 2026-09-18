import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v60
from xiaomi_e10_map_v60 import XiaomiE10MapV60


def bare():
    p = XiaomiE10MapV60.__new__(XiaomiE10MapV60)
    p.last_v60_diagnostics = {"methods": []}
    p.last_v59_diagnostics = {"methods": []}
    p._v59_cached_snapshot = None
    p._v59_cached_winner = None
    p._v59_lock = threading.Lock()
    p._v59_stop = threading.Event()
    p._v59_last_race_monotonic = 0.0
    p._v60_lan_lock = threading.RLock()
    p._v60_last_cycle_monotonic = 0.0
    p._v60_slot0_hash = None
    p.session_data = {"user_id": "USERSECRET"}
    p.did = "DIDSECRET"
    p.region = "sg"
    return p


# 1) BUG V59: piid=4 es metadata/descriptor del output, NO map-id.
response = {
    "siid": 10,
    "aiid": 1,
    "transport": "cloud",
    "out": [{"piid": 4, "value": "hello"}],
}
p = bare()
out = p._out_values(response)
assert out == {4: "hello"}
maps, diag = p._parse_map_list_value(out[4])
assert maps == []
assert diag["shape"]["placeholder"] is True
assert p._known_refs_only(response) == []
meta = p._action_meta_exact(response)
assert meta["map_id"] is None
assert meta["out_piids"] == [4]

# 2) Una lista REAL en PIID 4 sí crea map-id.
valid_value = '[{"name":"Casa","id":123456,"cur":true},{"name":"Piso","id":123457,"cur":false}]'
maps, diag = p._parse_map_list_value(valid_value)
assert [m["id"] for m in maps] == [123456, 123457]
assert maps[0]["cur"] is True
assert diag["valid_maps"] == 2

# 3) Estructura 10/1 exacta: jamás usa piid/aiid/transport como referencias.
class MapListDevice:
    def call_action_by(self, siid, aiid, params):
        assert (siid, aiid, params) == (10, 1, [])
        return {
            "siid": 10, "aiid": 1, "transport": "lan",
            "out": [{"piid": 4, "value": valid_value}],
        }

p = bare()
p.vacuum = SimpleNamespace(device=MapListDevice())
p.CLOUD_ACTION_ENDPOINTS = ("/miotspec/action",)
class Cloud:
    def request_country(self, endpoint, region, params):
        return {
            "code": 0,
            "result": {
                "siid": 10, "aiid": 1, "transport": "cloud",
                "out": [{"piid": 4, "value": valid_value}],
            },
        }
p._cloud = lambda: Cloud()
ids, refs, details = p._map_list_exact()
assert ids == [123456, 123457]
assert refs == []
assert all(4 not in item.get("map_ids", []) for item in details)
assert not any("hello" in str(x).lower() for x in refs)

# 4) PIID 6/7/18/21 son los únicos metadatos válidos de upload.
action_response = {
    "code": 0,
    "out": [
        {"piid": 6, "value": 123456},
        {"piid": 7, "value": 3},
        {"piid": 18, "value": 1789700000},
        {"piid": 21, "value": 1},
    ],
    "transport": "cloud",
    "aiid": 14,
}
meta = p._action_meta_exact(action_response)
assert meta["map_id"] == 123456
assert meta["map_type"] == 3
assert meta["timestamp"] == 1789700000
assert meta["renew_map"] == 1
assert meta["out_piids"] == [6, 7, 18, 21]

refs = p._refs_from_action_item(meta, [], "test")
values = [value for _source, value, _priority in refs]
assert "123456_1789700000" in values
assert "1789700000_123456" in values
assert "123456_3_1789700000" in values
assert "cloud" not in values
assert "14" not in values
assert "21" not in values

# 5) Referencias explícitas sólo salen de nombres de archivo/campos URL.
explicit = {
    "result": {
        "out": [{"piid": 6, "value": 123456}],
        "map_url": "record/real-map-object.bin",
        "transport": "cloud",
    }
}
known = p._known_refs_only(explicit)
assert known == [("map_url", "record/real-map-object.bin")]

# 6) Sanitizado: nunca debe filtrar URL firmada, ruta, firma ni IDs del path.
class Resp:
    status_code = 404
class SignedError(Exception):
    response = Resp()

signed = SignedError(
    "404 Client Error: Not Found for url: "
    "https://awssgp0.fds.api.xiaomi.com/xiaomi-map-b112.record/"
    "USERSECRET/DIDSECRET/123?Expires=999&GalaxyAccessKeyId=SECRET&Signature=SECRET"
)
safe = p._sanitize_error(signed)
assert "USERSECRET" not in safe
assert "DIDSECRET" not in safe
assert "Signature=SECRET" not in safe
assert "GalaxyAccessKeyId=SECRET" not in safe
assert safe.startswith("HTTP 404")

# 7) Filtro de refs: placeholders y duplicados fuera.
clean = p._dedupe_refs([
    ("x", "hello", 0),
    ("x", "cloud", 0),
    ("x", "0", 0),
    ("x", "123_1789700000", 2),
    ("y", "123_1789700000", 1),
])
assert clean == [("x", "123_1789700000", 2)]

# 8) El hash histórico conocido se marca stale, no ganador automático.
p = bare()
p._download_slot = lambda slot: (b"fake", "get_interim_file_url", 200)
p._sha12 = lambda raw: p.STALE_SLOT0_SHA12
p._decode_any_map = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("no debe decodificar slot0 conocido como stale")
)
sha, snap = p._slot0_baseline()
assert sha == p.STALE_SLOT0_SHA12
assert snap is None
assert p.last_v60_diagnostics["methods"][-1]["known_stale"] is True

# 9) LAN realmente serializado: dos threads no deben entrar juntos.
p = bare()
state = {"inside": 0, "max": 0}
class SlowDevice:
    def call_action_by(self, siid, aiid, params):
        state["inside"] += 1
        state["max"] = max(state["max"], state["inside"])
        time.sleep(0.04)
        state["inside"] -= 1
        return {"code": 0, "out": []}
p.vacuum = SimpleNamespace(device=SlowDevice())

threads = [
    threading.Thread(target=p._call_lan_action_exact, args=(18, [], "test"))
    for _ in range(3)
]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert state["max"] == 1

# 10) App V60 sigue la cadena UI pero usa cliente V60.
assert issubclass(app_v60.App, app_v60.app_v59.App)
print("SMOKE TEST V60 OK: piid4 no es map-id + map-list real + PIID 6/7/18/21 + URL saneada + LAN serial")

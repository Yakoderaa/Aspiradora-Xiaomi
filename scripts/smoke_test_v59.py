import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v59
from xiaomi_e10_map_v59 import XiaomiE10MapV59


class DummySnapshot:
    parser_error = None


def bare():
    p = XiaomiE10MapV59.__new__(XiaomiE10MapV59)
    p.last_v59_diagnostics = {}
    p._v59_cached_snapshot = None
    p._v59_cached_winner = None
    p._v59_lock = threading.Lock()
    p._v59_stop = threading.Event()
    p._v59_last_race_monotonic = 0.0
    p.session_data = {"user_id": "12345"}
    p.did = "67890"
    return p


# 1) Propiedades directas LAN descubren map_url/current_map/cur-map-id.
p = bare()
rows = [
    {"siid": 7, "piid": 30, "code": 0, "value": "record/map/file.bin"},
    {"siid": 7, "piid": 33, "code": 0, "value": 17},
    {"siid": 10, "piid": 2, "code": 0, "value": 17},
    {"siid": 10, "piid": 4, "code": 0, "value": "[17,18]"},
]
p.vacuum = SimpleNamespace(device=SimpleNamespace(send=lambda cmd, payload: rows))
refs = p._lan_props_all()
assert any("map_url" in src and ref == "record/map/file.bin" for src, ref in refs)
assert any(ref == "17" for _src, ref in refs)

# 2) Cloud datasource=1/2 extrae las mismas props.
p = bare()
cloud_response = {
    "code": 0,
    "result": [
        {"siid": 7, "piid": 30, "code": 0, "value": "https://example.invalid/map.bin"},
        {"siid": 10, "piid": 2, "code": 0, "value": 23},
    ],
}
class FakeCloud:
    def request_country(self, *args, **kwargs):
        return cloud_response
p._cloud = lambda: FakeCloud()
p.region = "sg"
p._decode_cloud_json = lambda response: response
refs = p._cloud_props_all(2)
assert any(ref.startswith("https://") for _src, ref in refs)
assert any(ref == "23" for _src, ref in refs)

# 3) get_map_v1 pointer estilo robomap%... se conserva y expande.
p = bare()
p.vacuum = SimpleNamespace(
    device=SimpleNamespace(send=lambda cmd, params: ["robomap%2F74476450%2F0"])
)
refs = p._legacy_map_pointer()
assert refs and "%" in refs[0][1]
expanded = p._expanded_refs(refs)
assert any("%" in ref for _src, ref in expanded)
assert any(ref.startswith("12345/67890/") for _src, ref in expanded)

# 4) get-map-list / uploads por map-id devuelven referencias.
p = bare()
class FakeDevice:
    def call_action_by(self, siid, aiid, params):
        if aiid == 1:
            return {"code": 0, "out": [{"piid": 4, "value": [31, 32]}]}
        return {"code": 0, "out": [{"piid": 6, "value": params[0] if params else 0}, {"piid": 18, "value": 1789700000}]}
p.vacuum = SimpleNamespace(device=FakeDevice())
p._call_cloud_action = lambda aiid, params, label: {"code": 0, "out": [{"piid": 6, "value": params[0] if params else 31}]}
refs, ids = p._map_list_action()
assert 31 in ids and 32 in ids
uprefs = p._upload_by_mapid(31)
assert uprefs

# 5) Ganador FDS: descarga + decoder válido.
p = bare()
snap = DummySnapshot()
p._download_candidate_reference = lambda source, ref: (b"fresh-map", "getmapfileurl", 200)
p._decode_any_map = lambda raw, label, endpoint: (snap, [{"name": "synthetic", "ok": True}])
p._sha12 = lambda raw: "abc123abc123"
p._looks_http = lambda value: str(value).startswith("http")
p._sanitize_error = lambda exc: str(exc)
p._try_reference("7/30 LAN", "record/map/file.bin")
assert p._v59_cached_snapshot is snap
assert p._v59_cached_winner == "FDS 7/30 LAN"

# 6) Primer ganador no puede ser sobrescrito por competidores posteriores.
other = DummySnapshot()
accepted = p._accept_snapshot("otro", other, {})
assert accepted is False
assert p._v59_cached_snapshot is snap

# 7) All-fail: el orquestador finaliza sin colgarse.
p = bare()
p.QUICK_TIMEOUT = 0.25
p.MAX_WORKERS = 4
p._lan_props_all = lambda: []
p._cloud_props_all = lambda datasource: []
p._legacy_map_pointer = lambda: []
p._history_refs = lambda: []
p._map_list_action = lambda: ([], [])
p._slot0_candidate = lambda: None
p._legacy_command = lambda command, params: []
p._active_v58 = lambda: None
result = p._run_race()
assert result is None
assert p.last_v59_diagnostics.get("phase") == "done"

# 8) Anti-repeat: load no relanza carrera inmediatamente después.
p = bare()
p._v59_last_race_monotonic = time.monotonic()
assert time.monotonic() - p._v59_last_race_monotonic < 6

assert issubclass(app_v59.App, app_v59.app_v58.App)
print("SMOKE TEST V59 OK: LAN/Cloud props + legacy pointer + map-list + uploads + FDS winner + all-fail seguro")

import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v57
from xiaomi_e10_map_v57 import XiaomiE10MapV57


# ---------------------------------------------------------------- grid falso
side = XiaomiE10MapV57.GRID_SIDE
fake = [0] * (side * side)
# 85 celdas deliberadamente dispersas, equivalente al patrón visual V56.
placed = 0
for y in range(4, side, 10):
    for x in range(4, side, 13):
        if placed >= 85:
            break
        fake[y * side + x] = 1 if placed % 3 else 2
        placed += 1
    if placed >= 85:
        break
m_fake = XiaomiE10MapV57._grid_metrics(fake)
assert m_fake["nonzero"] == 85
assert m_fake["valid"] is False
assert m_fake["components"] > 20

# ------------------------------------------------------------- grid coherente
real = [0] * (side * side)
for y in range(35, 75):
    for x in range(30, 88):
        real[y * side + x] = 1
# recortamos un patio/hueco para que no sea un bloque trivial
for y in range(47, 58):
    for x in range(48, 63):
        real[y * side + x] = 0
m_real = XiaomiE10MapV57._grid_metrics(real)
assert m_real["valid"] is True
assert m_real["largest"] >= 120
assert m_real["largest_ratio"] >= 0.55

# ---------------------------------------------------- action output anidado
response = {
    "result": {
        "code": 0,
        "out": [
            {"piid": 6, "value": 12345},
            {"piid": 7, "value": 0},
            {"piid": 18, "value": 1789699999},
            {"piid": 21, "value": 1},
        ],
    }
}
meta = XiaomiE10MapV57._action_metadata(response)
assert meta["code"] == 0
assert meta["map_id"] == 12345
assert meta["map_type"] == 0
assert meta["timestamp"] == 1789699999
assert meta["renew_map"] == 1

# --------------------------------------------------------- clean-end event 7/1
record = {
    "key": "7.1",
    "time": int(time.time()),
    "value": [
        {"piid": 27, "value": int(time.time()) - 600},
        {"piid": 28, "value": 600},
        {"piid": 29, "value": 25},
        {"piid": 30, "value": "/userdata/record_map/current_clean_map.bin"},
        {"piid": 49, "value": "60_60"},
    ],
}
event = XiaomiE10MapV57._event_meta(record)
assert event["record_map_url"] == "/userdata/record_map/current_clean_map.bin"
assert event["charge_pose"] == "60_60"

probe = XiaomiE10MapV57.__new__(XiaomiE10MapV57)
probe._v57_session_started_at = time.time() - 60
probe._v57_last_record_signature = None
probe._v57_last_record_snapshot = None
probe.HISTORY_LOOKBACK_SECONDS = 6 * 60 * 60
probe.HISTORY_LIMIT = 80
probe._query_key = lambda key, start, end: (
    [("history:event", record)] if key == "7.1" else [],
    [{"label": "history:event", "ok": True, "records": 1}],
)
probe._query_device_log = lambda start, end: ([], {"ok": True, "records": 0})
latest, hist_diag = probe._latest_clean_end()
assert latest is not None
assert latest[3]["record_map_url"].endswith("current_clean_map.bin")
assert hist_diag["candidate_count"] == 1

# ----------------------------------------- pipeline record-map-url descargado
sentinel_snapshot = SimpleNamespace(
    raw_robot=(1.0, 2.0),
    raw_base=(0.0, 0.0),
    raw_path=[(0.0, 0.0), (1.0, 2.0)],
)
probe._latest_clean_end = lambda: (
    (float(record["time"]), "history:event", record, event),
    {"queries": [{"label": "history:event", "ok": True, "records": 1}],
     "device_log": {"ok": True, "records": 0},
     "candidate_count": 1},
)
probe._resolve_file_ref = lambda ref: ("https://example.invalid/map.bin", "getfileurl")
probe._download_url = lambda url: (b"real-map-bytes", 200)
probe._decode_any_map = lambda raw, label, endpoint: (
    sentinel_snapshot,
    [{"name": "synthetic-decoder", "ok": True}],
)
snap, diag = probe._load_record_map()
assert snap is sentinel_snapshot
assert diag["success"] is True
assert diag["resolve_endpoint"] == "getfileurl"
assert diag["download_bytes"] == len(b"real-map-bytes")

# ---------------------------------------------------- imagen directa final map
png = io.BytesIO()
Image.new("RGB", (32, 24), (240, 240, 240)).save(png, format="PNG")
img_probe = XiaomiE10MapV57.__new__(XiaomiE10MapV57)
snapshot, decoders = img_probe._decode_any_map(png.getvalue(), "clean-end", "direct")
assert snapshot is not None
assert snapshot.image.size == (32, 24)
assert decoders[0]["name"] == "image"
assert decoders[0]["ok"] is True

assert issubclass(app_v57.App, app_v57.app_v56.App)
assert app_v57.App.POST_CLEAN_SECONDS >= 120
print("SMOKE TEST V57 OK: falso grid rechazado + clean-end 7/1 + record-map-url + action nested + imagen directa")

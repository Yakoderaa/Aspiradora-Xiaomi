import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v40
from xiaomi_e10_ijai_map import XiaomiE10IjaiMapClient


assert XiaomiE10IjaiMapClient._is_wifi_sn("1234567890ABCDEFGH")
assert not XiaomiE10IjaiMapClient._is_wifi_sn("hello")

class Snapshot:
    raw_robot = (12.0, 8.0)
    raw_base = (10.0, 8.0)
    raw_path = [(10.0, 8.0), (11.0, 8.0), (12.0, 8.0)]

scale = app_v40.App._v40_detect_scale(Snapshot())
assert scale == 1.0
relative = app_v40.App._v39_relative_mm((12.0, 8.0), (10.0, 8.0))
assert relative and abs(relative["x"] - 2.0) < 1e-9 and abs(relative["y"]) < 1e-9

assert "_manual_update_found_safe" in app_v40.App.__dict__
assert "_v38_maybe_poll_map_file" in app_v40.App.__dict__
assert "_diagnostic_text" in app_v40.App.__dict__

print("SMOKE TEST V40 OK: IJAI + escala + geometría pre-update")

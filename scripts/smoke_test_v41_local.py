import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import xiaomi_e10_live_patch_v41
from xiaomi_e10_live import XiaomiE10Live

xiaomi_e10_live_patch_v41.install()
raw = [123, 1.0, 2.0, 0.5, 1]
assert XiaomiE10Live._extract_action_output(raw, 5) == raw
parsed = XiaomiE10Live.parse_trajectory(raw)
assert len(parsed) == 1
assert parsed[0]["id"] == 123
assert parsed[0]["x"] == 1.0 and parsed[0]["y"] == 2.0
assert 4294967295 in XiaomiE10Live.FALLBACK_PROBE_ENDS
assert max(XiaomiE10Live.HISTORY_SPANS) >= 65535
print("SMOKE TEST V41 LOCAL OK: 10/12 numérico + rango uint32")

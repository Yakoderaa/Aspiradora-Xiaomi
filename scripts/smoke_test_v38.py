import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from app_v38 import App
from xiaomi_map import XiaomiE10MapClient


response = {
    "code": 0,
    "result": {
        "url": "https://example.invalid/map.bin",
    },
}
raw = json.dumps(response).encode("utf-8")
assert XiaomiE10MapClient._extract_url(raw) == "https://example.invalid/map.bin"
assert XiaomiE10MapClient._extract_url(bytearray(raw)) == "https://example.invalid/map.bin"
assert XiaomiE10MapClient._extract_url(json.dumps(response)) == "https://example.invalid/map.bin"

assert App._parse_geometry("1420x880+250+100") == (1420, 880, 250, 100)
assert App._parse_geometry("1180x720-1200+40") == (1180, 720, -1200, 40)
assert App._parse_geometry("bad") is None
assert App._parse_geometry("20x20+0+0") is None

assert hasattr(App, "_v38_maybe_poll_map_file")
assert hasattr(App, "_v38_capture_geometry")
assert hasattr(App, "destroy")

print("smoke_test_v38 OK")

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v104

for path in (
    SRC / "app_v104.py",
    SRC / "main_v104.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v104.App, app_v104.app_v103.App)
assert app_v104.App.COARSE_FACTOR == 2
assert app_v104.App.COARSE_MIN_HASHES == 2
assert app_v104.App.COARSE_MIN_SECONDS == 25.0

# La reducción 2x2 debe ser independiente de la permutación local.
base = {
    "side": 4,
    "resolution": 0.2,
    "base_cell": [2.0, 2.0],
    "blob_sha12": "abc",
    "timestamp": 1,
}
a = dict(base)
a["cells"] = [
    1, 0, 0, 0,
    0, 0, 0, 0,
    0, 0, 0, 1,
    0, 0, 0, 0,
]
b = dict(base)
b["cells"] = [
    0, 1, 0, 0,
    0, 0, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 0,
]
ca = app_v104.App._v104_to_layout_invariant_coarse(a)
cb = app_v104.App._v104_to_layout_invariant_coarse(b)
assert ca["side"] == 2
assert ca["resolution"] == 0.4
assert ca["cells"] == cb["cells"] == [1, 0, 0, 1]

source = (SRC / "app_v104.py").read_text(encoding="utf-8")
for required in (
    "xiaomi-live-coarse-invariant",
    "permutación local ignorada=True",
    "COARSE_MIN_HASHES = 2",
    "COARSE_MIN_SECONDS = 25.0",
    "tile2-1203, tile2-0213",
    "Mapa Xiaomi preliminar",
):
    assert required in source, required

print(
    "SMOKE TEST V104 OK: layout-invariant 2x2 Xiaomi preview + "
    "automatic V57 precise upgrade"
)

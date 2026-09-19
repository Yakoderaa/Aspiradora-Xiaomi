import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v103

for path in (
    SRC / "app_v103.py",
    SRC / "main_v103.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v103.App, app_v103.app_v102.App)
assert app_v103.App.LIVE_CONFIDENCE_FRAMES == 4
assert app_v103.App.LIVE_MIN_PREVIEW_SECONDS == 60.0
assert app_v103.App.LIVE_MIN_PREVIEW_CELLS == 100
assert app_v103.App.LIVE_MAX_GROWTH_RATIO == 2.4

dummy = app_v103.App.__new__(app_v103.App)
assert dummy._v103_canonical_candidate(
    "acum[2]|tile2-0213|nonzero"
) == "tile2-0213|nonzero"
assert dummy._v103_canonical_candidate(
    "tile2-0312|nonzero"
) == "tile2-0312|nonzero"

source = (SRC / "app_v103.py").read_text(encoding="utf-8")
for required in (
    "self.map_selected_xy = None",
    "current_key == selected_key",
    "LIVE_CONFIDENCE_FRAMES = 4",
    'out["v103_confident"] = True',
    "LIVE_MIN_PREVIEW_SECONDS = 60.0",
    "LIVE_MIN_PREVIEW_CELLS = 100",
    "salto geométrico",
    "validando geometría Xiaomi",
    "un acumulado preview inválido nunca se dibuja",
):
    assert required in source, required

print(
    "SMOKE TEST V103 OK: unstable accumulated grids blocked + "
    "delayed confidence gate + growth reset + map_selected_xy initialized"
)

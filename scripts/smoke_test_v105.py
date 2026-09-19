import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v105

for path in (
    SRC / "app_v105.py",
    SRC / "main_v105.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v105.App, app_v105.app_v104.App)
assert app_v105.App.CONSENSUS_WINDOW == 5
assert app_v105.App.CONSENSUS_RATIO == 0.60
assert app_v105.App._v105_required_votes(2) == 2
assert app_v105.App._v105_required_votes(3) == 2
assert app_v105.App._v105_required_votes(5) == 3

history = [
    {"sha": "a", "cells": [1, 1, 0, 0]},
    {"sha": "b", "cells": [1, 0, 1, 0]},
    {"sha": "c", "cells": [1, 1, 1, 0]},
]
assert app_v105.App._v105_consensus(history, 2) == [1, 1, 1, 0]

source = (SRC / "app_v105.py").read_text(encoding="utf-8")
for required in (
    "xiaomi-live-coarse-consensus",
    "_v105_frozen_previews",
    "mapping_active pasa a False",
    "status=3 o status=4",
    "_v93_prev_frame_cells",
    "cleaning_area",
):
    assert required in source, required

print(
    "SMOKE TEST V105 OK: rolling consensus + retained preview "
    "during return/dock + cleaning area telemetry"
)

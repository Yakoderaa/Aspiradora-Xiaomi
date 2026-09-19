import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v106

for path in (
    SRC / "app_v106.py",
    SRC / "main_v106.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v106.App, app_v106.app_v105.App)
assert app_v106.App.DENSITY_WINDOW == 5
assert app_v106.App.DENSITY_MIN_HASHES == 3

grid = {
    "side": 4,
    "cells": [
        1, 0, 1, 1,
        0, 0, 0, 1,
        0, 0, 0, 0,
        1, 1, 1, 1,
    ],
}
packed = app_v106.App._v106_block_counts(grid)
assert packed["coarse_side"] == 2
assert packed["counts"] == [1, 3, 2, 2]

history = [
    {"sha": "a", "counts": [1, 3, 0, 2]},
    {"sha": "b", "counts": [1, 2, 1, 2]},
    {"sha": "c", "counts": [2, 3, 0, 4]},
    {"sha": "d", "counts": [1, 4, 0, 3]},
    {"sha": "e", "counts": [1, 3, 1, 2]},
]
median = app_v106.App._v106_median_low_counts(history)
assert median == [1, 3, 0, 2]

cells, chosen = app_v106.App._v106_expand_density(
    median, 2, [2.0, 2.0]
)
assert chosen == sum(median) == 6
assert sum(cells) == 6

source = (SRC / "app_v106.py").read_text(encoding="utf-8")
for required in (
    "xiaomi-live-density-consensus",
    "median_low",
    "0.20 * 0.20",
    "ya no se rellena",
    "durante retorno y dock",
):
    assert required in source, required

print(
    "SMOKE TEST V106 OK: density-preserving tile2 preview + "
    "rolling median + V105 retained map"
)

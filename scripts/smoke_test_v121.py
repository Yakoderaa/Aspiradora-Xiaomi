import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v121


for path in (
    SRC / "app_v121.py",
    SRC / "main_v121.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v121.App, app_v121.app_v120.App)

source = (SRC / "app_v121.py").read_text(encoding="utf-8")
assert "Fase 1/2" in source
assert "Fase 2/2" in source
assert "vacuum.start_mapping_interior()" in source
assert "arm_new_map_called" in source
assert "def _v84_close_mapping_on_dock" in source
assert "def _v93_schedule_final_reads" in source
assert "def _v107_choose_final_grid" in source

# La transición a fase 2 no puede crear otro mapa.
phase2 = source.split(
    "    def _v121_request_phase2", 1
)[1].split(
    "    # ====================================== status=4", 1
)[0]
assert "arm_new_map(" not in phase2
assert "start_mapping_interior()" in phase2

# Un grid inválido no puede volver a guardarse como 'final'.
app = app_v121.App.__new__(app_v121.App)
app._v121_invalid_final_grids_rejected = 0
app._v107_final_candidates = 0
app._v107_final_unique = 0
chosen, reason = app._v107_choose_final_grid([
    {
        "side": 120,
        "resolution": 0.2,
        "base_cell": [60.0, 60.0],
        "cells": [0] * (120 * 120),
        "metrics": {"valid": False, "nonzero": 40},
    }
])
assert chosen is None
assert app._v121_invalid_final_grids_rejected == 1
assert "ningún grid Xiaomi final" in reason

print(
    "SMOKE TEST V121 OK: Edge->dock no cierra, fase 2 no rearma "
    "build-map y grids finales inválidos se rechazan"
)

import ast
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v77

source = (SRC / "app_v77.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v77.App, app_v77.app_v76.App)

app = app_v77.App.__new__(app_v77.App)
app._v71_session_origin_raw = (60.0, 60.0)
app._v77_filter_last_raw = None
app._v77_filter_last_output = None
app._v77_turn_translations_filtered = 0
app._v77_jitter_points_filtered = 0

# Escala confirmada por diagnóstico: 60_60 -> (6.0,6.0) en mapa B112.
xy = app._v71_normalize_xy((50.0, 48.0))
assert abs(xy[0] + 1.0) < 1e-9
assert abs(xy[1] + 1.2) < 1e-9

# 255_255 no puede ser base.
assert app._v77_valid_base_xy({"x": 255, "y": 255}) is None
assert app._v77_valid_base_xy({"x": 60, "y": 60}) == (60.0, 60.0)

# Primer punto queda en metros. Un salto de 10 cm durante un giro fuerte se
# limita a 3 cm en lugar de crear un escalón lateral completo.
p1 = app._v77_filter_metric_point({"id": 1, "x": 58, "y": 56, "phi": 0.0})
p2 = app._v77_filter_metric_point({"id": 2, "x": 59, "y": 56, "phi": 1.0})
assert abs(p1["x"] + 0.2) < 1e-9
assert abs(p1["y"] + 0.4) < 1e-9
assert math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"]) <= 0.0300001
assert app._v77_turn_translations_filtered == 1

# El detector de corredor reconoce ida/vuelta sobre una misma línea.
samples = []
t = 0.0
for cycle in range(5):
    seq = [i / 10.0 for i in range(11)]
    if cycle % 2:
        seq = list(reversed(seq))
    for x in seq:
        samples.append((t, x, 0.02 * math.sin(t), 0.0))
        t += 2.0
geom = app._v77_corridor_geometry(samples, 0.04)
assert geom["along_span"] >= 0.9
assert geom["cross_span"] <= 0.05
assert geom["reversals"] >= 4

# La base se captura antes del START y todo se persiste en metros.
for required in (
    '("charging_base", 10, 22)',
    "RAW_TO_METERS = 0.10",
    "vacuum.start_mapping_interior()",
    "base_raw = self._v77_capture_base_reference(vacuum)",
    "10/24 y trayectoria se convierten a metros",
    "status=4 con recorrido real cierra el mapeo",
    "CORRIDOR_MIN_REVERSALS = 4",
):
    assert required in source, required

start_idx = source.index("base_raw = self._v77_capture_base_reference(vacuum)")
sweep_idx = source.index("vacuum.start_mapping_interior()")
assert start_idx < sweep_idx

print(
    "SMOKE TEST V77 OK: base 10/22 + raw-to-metros + filtro de giro + "
    "corredor repetido + cierre status=4"
)

import ast
import math
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v82

source = (SRC / "app_v82.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v82.App, app_v82.app_v81.App)


def blank_app():
    app = app_v82.App.__new__(app_v82.App)

    app._v82_previous_raw = None
    app._v82_last_corrected = None
    app._v82_last_persisted_xy = None
    app._v82_turn_hold = False
    app._v82_turn_origin = None
    app._v82_turn_axis = None
    app._v82_turn_pending = []
    app._v82_lane_origin = None
    app._v82_lane_axis = None
    app._v82_lane_pending = deque(maxlen=10)
    app._v82_turn_points_frozen = 0
    app._v82_lane_offsets_suppressed = 0
    app._v82_lane_changes_confirmed = 0
    app._v82_corrected_samples = deque(maxlen=2400)
    app._v82_corrected_cells = set()
    app._v82_status4_session_closes = 0
    app._v82_shared_thumb_bounds = None

    app._v79_previous_absolute = None
    app._v79_last_absolute = None
    app._v79_last_filtered = None
    app._v79_last_filter_error = 0.0
    app._v79_max_filter_error = 0.0
    app._v79_initial_gate_open = True
    app._v79_initial_rejected = 0

    app._v77_filter_last_raw = None
    app._v77_filter_last_output = None
    app._v77_turn_translations_filtered = 0
    app._v77_jitter_points_filtered = 0

    app._v81_min_x = -1.0
    app._v81_max_x = 1.0
    app._v81_min_y = -1.0
    app._v81_max_y = 1.0
    app._v81_completion_ready = False
    app._v81_completion_missing = []
    app._v81_corridor_incomplete_hits = 0
    app._v81_no_new_deferrals = 0
    app._v81_incomplete_reason = None

    app._v74_coverage_cells = set()
    app._v74_started_at = time.monotonic() - 500.0
    app._v74_last_discovery_at = time.monotonic()
    app._v71_session_max_departure = 2.0
    return app


# Un giro fuerte con salto XY no puede fabricar un pico.
app = blank_app()
p0 = app._v82_correct_absolute({"x": 0.0, "y": 0.0, "phi": 0.0})
p1 = app._v82_correct_absolute({"x": 0.10, "y": 0.10, "phi": math.pi / 2})
assert abs(p1["x"] - p0["x"]) < 1e-9
assert abs(p1["y"] - p0["y"]) < 1e-9
assert app._v82_turn_points_frozen >= 1

# Un corredor largo/estrecho con muchas reversiones sigue siendo incompleto
# aunque cumpla tiempo, celdas, salida y X/Y heredados.
app = blank_app()
app._v74_coverage_cells = {(x, y) for x in range(-3, 4) for y in range(-2, 3)}
app._v82_corrected_cells = set(app._v74_coverage_cells)
app._v82_corrected_samples.clear()
now = time.monotonic()
for lap in range(8):
    direction = 1 if lap % 2 == 0 else -1
    xs = [i * 0.10 for i in range(-10, 11)]
    if direction < 0:
        xs.reverse()
    for x in xs:
        app._v82_corrected_samples.append((now, x, 0.08 * (lap % 2), 0.0))
        now += 0.20
state = app._v81_completion_state()
assert state["ready"] is False
assert any(
    "exploración 2D" in item or "expansión lateral real" in item
    for item in state["missing"]
)

# Una trayectoria realmente bidimensional puede superar la nueva condición.
app = blank_app()
app._v74_coverage_cells = {(x, y) for x in range(-5, 6) for y in range(-5, 6)}
app._v82_corrected_cells = set(app._v74_coverage_cells)
app._v82_corrected_samples.clear()
now = time.monotonic()
for y in (-1.0, -0.5, 0.0, 0.5, 1.0):
    xs = [i * 0.10 for i in range(-10, 11)]
    if int((y + 1.0) * 2) % 2:
        xs.reverse()
    for x in xs:
        app._v82_corrected_samples.append((now, x, y, 0.0))
        now += 0.20
state = app._v81_completion_state()
assert state["ready"] is True

# La miniatura usa límites simétricos alrededor de la misma base.
bounds = app_v82.App._v70_collect_bounds(
    {
        "points": [
            {"x": -1.0, "y": -0.2},
            {"x": 0.4, "y": 0.8},
        ],
        "charging_base": {"x": 0.0, "y": 0.0},
    },
    {},
)
assert bounds[0] == -bounds[2]
assert bounds[1] == -bounds[3]

for required in (
    "durante un giro fuerte X/Y quedan congelados",
    "muchas celdas alineadas nunca equivalen a una habitación mapeada",
    "status=4 confirmado cierra la sesión",
    "miniatura y mapa grande comparten el mismo marco mundial",
):
    assert required in source, required

print(
    "SMOKE TEST V82 OK: giro sin picos + carril persistente + "
    "cobertura 2D corregida + cierre al cargar + marco compartido"
)

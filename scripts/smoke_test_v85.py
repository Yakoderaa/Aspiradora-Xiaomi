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

import app_v85

source = (SRC / "app_v85.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v85.App, app_v85.app_v84.App)


def blank_app():
    app = app_v85.App.__new__(app_v85.App)

    app._v85_frame_offset = (0.0, 0.0)
    app._v85_last_raw = None
    app._v85_last_transformed = None
    app._v85_rebases = 0
    app._v85_impossible_steps_blocked = 0
    app._v85_max_raw_step = 0.0
    app._v85_max_blocked_step = 0.0
    app._v85_last_rebase = None
    app._v85_recent_rebases = deque(maxlen=12)

    app._v83_lane_candidate = None
    app._v83_point_seq = 0
    app._v83_decision_counts = {
        "ACEPTADO": 0,
        "GIRO PURO": 0,
        "OFFSET TRANSITORIO": 0,
        "CAMBIO DE CARRIL": 0,
    }
    app._v83_recent_decisions = deque(maxlen=24)
    app._v83_recovery_gate_blocks = 0
    app._v83_recovery_gate_accepts = 0
    app._v83_last_recovery_gate = None
    app._v83_last_recovery_trigger = None
    app._v83_max_output_error = 0.0

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

    app._v79_previous_absolute = None
    app._v79_last_absolute = None
    app._v79_last_filtered = None
    app._v79_last_filter_error = 0.0
    app._v79_max_filter_error = 0.0

    app._v77_filter_last_raw = None
    app._v77_filter_last_output = None
    app._v77_corridor_last_geometry = None

    app._v74_finish_requested = False
    app._v74_last_discovery_at = time.monotonic()
    app._v73_recovery_active = False
    app._v73_last_recovery_at = 0.0
    return app


# Secuencia normal: pasos de 10 cm permanecen exactamente donde vienen.
app = blank_app()
p0 = app._v82_correct_absolute({"x": 0.0, "y": 0.0, "phi": 0.0})
p1 = app._v82_correct_absolute({"x": 0.1, "y": 0.0, "phi": 0.0})
assert abs(p0["x"]) < 1e-9
assert abs(p1["x"] - 0.1) < 1e-9
assert app._v85_rebases == 0

# Reproduce el fallo V84: después de movimiento normal aparece un salto raw de
# 3.33 m. V85 debe congelar ESA muestra y continuar con los deltas siguientes.
jump_x = 0.1 + 3.33
p2 = app._v82_correct_absolute({"x": jump_x, "y": 0.0, "phi": 0.01})
assert math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"]) < 1e-9
assert app._v85_rebases == 1
assert app._v85_impossible_steps_blocked == 1
assert app._v85_max_blocked_step > 3.3

p3 = app._v82_correct_absolute({"x": jump_x + 0.1, "y": 0.0, "phi": 0.02})
assert abs((p3["x"] - p2["x"]) - 0.1) < 1e-9

# Si el firmware vuelve al marco anterior, tampoco debe dibujar otra diagonal.
p4 = app._v82_correct_absolute({"x": 0.2, "y": 0.0, "phi": 0.03})
assert math.hypot(p4["x"] - p3["x"], p4["y"] - p3["y"]) < 1e-9
assert app._v85_rebases == 2

p5 = app._v82_correct_absolute({"x": 0.3, "y": 0.0, "phi": 0.04})
assert abs((p5["x"] - p4["x"]) - 0.1) < 1e-9

# Ningún punto corregido del escenario puede teletransportarse.
points = [p0, p1, p2, p3, p4, p5]
for a, b in zip(points, points[1:]):
    assert math.hypot(b["x"] - a["x"], b["y"] - a["y"]) <= 0.11

for required in (
    "una sola muestra 10/24 no puede teletransportar",
    "discontinuidad del marco se reancla",
    "cobertura/completitud sólo ven la trayectoria continua",
    "vuelve al marco anterior",
):
    assert required in source, required

print(
    "SMOKE TEST V85 OK: salto 3.33 m bloqueado + continuidad conservada + "
    "retorno de marco absorbido sin diagonales falsas"
)

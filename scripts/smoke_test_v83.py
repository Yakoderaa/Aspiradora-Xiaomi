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

import app_v83

source = (SRC / "app_v83.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v83.App, app_v83.app_v82.App)


def blank_app():
    app = app_v83.App.__new__(app_v83.App)

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


# Un giro realmente sobre el lugar congela X/Y.
app = blank_app()
p0 = app._v82_correct_absolute({"x": 0.0, "y": 0.0, "phi": 0.0})
p1 = app._v82_correct_absolute({"x": 0.02, "y": 0.01, "phi": math.pi / 2})
assert abs(p1["x"] - p0["x"]) < 1e-9
assert abs(p1["y"] - p0["y"]) < 1e-9
assert app._v83_decision_counts["GIRO PURO"] == 1

# Giro con avance real: 10 cm de traslación se conserva, no se congela.
app = blank_app()
app._v82_correct_absolute({"x": 0.0, "y": 0.0, "phi": 0.0})
p = app._v82_correct_absolute({"x": 0.10, "y": 0.0, "phi": math.pi / 2})
assert abs(p["x"] - 0.10) < 1e-9
assert abs(p["y"]) < 1e-9
assert app._v83_decision_counts["ACEPTADO"] >= 1

# Un salto lateral dudoso no puede acumular una separación enorme:
# al superar 22 cm se acepta la posición absoluta.
app = blank_app()
app._v82_correct_absolute({"x": 0.0, "y": 0.0, "phi": 0.0})
p = app._v82_correct_absolute({"x": 0.0, "y": 0.25, "phi": math.pi / 2})
assert math.hypot(p["x"] - 0.0, p["y"] - 0.25) <= app.MAX_FILTER_ERROR_METERS + 1e-9
assert app._v83_decision_counts["CAMBIO DE CARRIL"] >= 1

# Un recovery no puede dispararse si se descubrió área hace pocos segundos.
app = blank_app()
now = time.monotonic()
app._v74_last_discovery_at = now - 10.0
allowed, meta = app._v83_recovery_gate(
    "pasadas ida/vuelta sobre el mismo corredor",
    now=now,
)
assert allowed is False
assert "todavía descubre área" in meta["reason"]

# Tras suficiente tiempo sin descubrir y fuera del cooldown, puede autorizarse.
app._v74_last_discovery_at = now - 90.0
app._v77_corridor_last_geometry = {
    "cross_span": 0.18,
    "along_span": 1.0,
    "reversals": 6,
}
allowed, meta = app._v83_recovery_gate(
    "pasadas ida/vuelta sobre el mismo corredor",
    now=now,
)
assert allowed is True
assert meta["kind"] == "corredor"

# El cooldown duro bloquea un segundo recovery inmediato.
app._v73_last_recovery_at = now - 30.0
allowed, meta = app._v83_recovery_gate(
    "oscilación real sin avance",
    now=now,
)
assert allowed is False
assert "cooldown" in meta["reason"]

for required in (
    "sólo un giro con desplazamiento casi nulo congela X/Y",
    "no hay recovery mientras se sigan descubriendo celdas nuevas",
    "cooldown duro",
    "CAMBIO DE CARRIL",
):
    assert required in source, required

print(
    "SMOKE TEST V83 OK: giro+avance conservado + error absoluto acotado + "
    "cambio de carril rápido + recovery bloqueado durante exploración + cooldown"
)

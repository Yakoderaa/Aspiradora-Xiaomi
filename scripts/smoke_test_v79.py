import ast
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v79

source = (SRC / "app_v79.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v79.App, app_v79.app_v78.App)


def blank_app():
    app = app_v79.App.__new__(app_v79.App)
    app._v71_session_origin_raw = (60.0, 60.0)
    app._v79_previous_absolute = None
    app._v79_last_absolute = None
    app._v79_last_filtered = None
    app._v79_last_filter_error = 0.0
    app._v79_max_filter_error = 0.0
    app._v79_initial_gate_open = False
    app._v79_initial_rejected = 0
    app._v79_stationary_recoveries = 0
    app._v79_corridor_recoveries = 0
    app._v77_filter_last_raw = None
    app._v77_filter_last_output = None
    app._v77_turn_translations_filtered = 0
    app._v77_jitter_points_filtered = 0
    return app


app = blank_app()

# Outlier inicial: se consume pero no se persiste.
far = app._v77_filter_metric_point(
    {"id": 1, "x": 75.0, "y": 60.0, "phi": 0.0}
)
assert far is None
assert app._v79_initial_rejected == 1
assert app._v79_initial_gate_open is False

# Un punto cercano al dock abre la sesión.
p1 = app._v77_filter_metric_point(
    {"id": 2, "x": 61.0, "y": 59.0, "phi": 0.0}
)
assert p1 is not None
assert abs(p1["x"] - 0.1) < 1e-9
assert abs(p1["y"] + 0.1) < 1e-9
assert app._v79_initial_gate_open is True

# Giro fuerte: la muestra actual puede limitarse, pero NO puede arrastrar error.
p2 = app._v77_filter_metric_point(
    {"id": 3, "x": 62.0, "y": 59.0, "phi": 1.0}
)
assert p2 is not None
assert app._v79_last_filter_error > 0.0

# La siguiente posición vuelve al absoluto raw/base, no a output_anterior+delta.
p3 = app._v77_filter_metric_point(
    {"id": 4, "x": 61.0, "y": 59.0, "phi": 1.05}
)
assert p3 is not None
assert abs(p3["x"] - 0.1) < 1e-9
assert abs(p3["y"] + 0.1) < 1e-9
assert math.hypot(
    app._v79_last_absolute[0] - 0.1,
    app._v79_last_absolute[1] + 0.1,
) < 1e-9

assert app._v79_recovery_kind(
    "pasadas ida/vuelta sobre el mismo corredor"
) == "corridor"
assert app._v79_recovery_kind(
    "oscilación real sin avance"
) == "stationary"

for required in (
    "cada muestra parte siempre de (10/24 - base) * 0.10",
    "cobertura y detectores usan coordenadas absolutas",
    "atasco estacionario y corredor repetido tienen contadores independientes",
    "INITIAL_GATE_RADIUS_METERS = 0.80",
):
    assert required in source, required

# Regresión crítica: V79 no debe volver a integrar desde el output filtrado.
assert "ox + dx" not in source
assert "oy + dy" not in source

print(
    "SMOKE TEST V79 OK: filtro absoluto sin deriva + gate inicial + "
    "recoveries separados"
)

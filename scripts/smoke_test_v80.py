import ast
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v80

source = (SRC / "app_v80.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v80.App, app_v80.app_v79.App)


def blank_app():
    app = app_v80.App.__new__(app_v80.App)
    app._v80_initial_buffer = []
    app._v80_initial_validated = False
    app._v80_initial_buffer_rejected = 0
    app._v80_initial_buffer_resets = 0
    app._v80_initial_flush_count = 0
    app._v79_previous_absolute = None
    app._v80_render_snapshot = None
    app._v80_main_points = 0
    app._v80_main_hash = "—"
    app._v80_thumb_points = 0
    app._v80_thumb_hash = "—"
    return app


app = blank_app()

# Un primer punto a 60 cm ya no puede abrir el recorrido aunque el gate V79
# anterior hubiera tolerado hasta 80 cm.
assert app._v80_buffer_initial_point(
    {"id": 1, "x": 0.60, "y": 0.0, "phi": 0.0}
) == []
assert app._v80_initial_buffer_rejected == 1
assert not app._v80_initial_validated

# Secuencia continua desde el dock: se acumula y se libera junta.
assert app._v80_buffer_initial_point(
    {"id": 2, "x": 0.10, "y": 0.00, "phi": 0.0}
) == []
assert app._v80_buffer_initial_point(
    {"id": 3, "x": 0.18, "y": 0.02, "phi": 0.0}
) == []
assert app._v80_buffer_initial_point(
    {"id": 4, "x": 0.24, "y": 0.03, "phi": 0.0}
) == []
flushed = app._v80_buffer_initial_point(
    {"id": 5, "x": 0.30, "y": 0.04, "phi": 0.0}
)
assert len(flushed) == 4
assert app._v80_initial_validated
assert app._v80_initial_flush_count == 4

# Hash estable de snapshot: misma geometría = misma firma.
snapshot = {
    "points": [
        {"id": -1, "phase": 2, "x": 0.0, "y": 0.0},
        {"id": 2, "phase": 2, "x": 0.1, "y": 0.0},
    ],
    "robot": {"x": 0.1, "y": 0.0, "angle": 0.0},
    "charging_base": {"x": 0.0, "y": 0.0, "angle": 0.0},
}
count1, hash1 = app._v80_snapshot_signature(snapshot)
count2, hash2 = app._v80_snapshot_signature(dict(snapshot))
assert count1 == count2 == 2
assert hash1 == hash2

# El detector de corredor V80 acepta hasta 30 cm.
assert abs(app_v80.App.CORRIDOR_MAX_WIDTH - 0.30) < 1e-9

# Comparación IJAI: currentPose 5.8,5.6 respecto de dock 6,6 = -0.2,-0.4.
app._v40_native_robot = (5.8, 5.6)
app._v40_native_base = (6.0, 6.0)
app._v40_upload_date = None
app._v79_last_absolute = (-0.6, -0.4, 0.0)
app._v80_ijai_relative = None
app._v80_ijai_delta = None
app._v80_ijai_age = None
app._v80_ijai_base_source = "—"
app._v80_update_ijai_comparison()
assert abs(app._v80_ijai_relative[0] + 0.2) < 1e-9
assert abs(app._v80_ijai_relative[1] + 0.4) < 1e-9
assert abs(app._v80_ijai_delta[0] - 0.4) < 1e-9
assert abs(app._v80_ijai_delta[1] - 0.0) < 1e-9

for required in (
    "ningún punto se persiste hasta validar continuidad física desde el dock",
    "mapa grande y tarjeta activa reciben el mismo snapshot",
    "IJAI es sólo diagnóstico",
    "CORRIDOR_MAX_WIDTH = 0.30",
):
    assert required in source, required

print(
    "SMOKE TEST V80 OK: buffer inicial + snapshot único + "
    "corredor 0.30 m + comparación IJAI"
)

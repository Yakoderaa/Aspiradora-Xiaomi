import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v72


app = app_v72.App.__new__(app_v72.App)
app._v72_views = {}
app._v72_active_map_seen = None

# Helpers geométricos puros.
snapshot = {
    "points": [
        {"x": -2.0, "y": -1.0},
        {"x": 3.0, "y": 2.0},
    ],
    "charging_base": {"x": 0.0, "y": 0.0},
}
app.plan_store = None

bounds = app._v72_bounds(snapshot)
assert bounds == (-2.0, -1.0, 3.0, 2.0)
assert app._v72_default_base_center(snapshot) == (0.0, 0.0)

scale = app._v72_fit_scale_about_center(
    bounds,
    (0.0, 0.0),
    1000,
    600,
    28,
)
assert scale is not None and scale > 0

# Si la base está muy corrida respecto de la geometría, el fit centrado en base
# debe reducir la escala para que todo siga visible alrededor de ella.
far_bounds = (-1.0, -1.0, 20.0, 2.0)
far_scale = app._v72_fit_scale_about_center(
    far_bounds,
    (0.0, 0.0),
    1000,
    600,
    28,
)
assert far_scale < scale

# Contrato de la capa V72.
assert app_v72.App.ZOOM_STEP > 1.0
assert app_v72.App.MIN_SCALE > 0
assert app_v72.App.MAX_SCALE > app_v72.App.MIN_SCALE
assert issubclass(app_v72.App, app_v72.app_v71.App)

source = Path(SRC / "app_v72.py").read_text(encoding="utf-8")
for required in (
    '<MouseWheel>',
    '<Double-Button-2>',
    'Zoom Extents',
    '_fixed_map_legend = True',
    'mode"] = "base"',
    'mode"] = "manual"',
    'mode"] = "extents"',
    'canvas.scale("all"',
    'self._v72_legend.lift()',
):
    assert required in source, required

# La leyenda histórica queda intacta para versiones antiguas y sólo se omite
# cuando la capa nueva declara una leyenda fija.
legacy = Path(SRC / "app_v6.py").read_text(encoding="utf-8")
assert '_fixed_map_legend' in legacy
assert 'Perímetro' in legacy
assert 'Interior' in legacy

# V72 no cambia reglas de transición/mapeo V71.
for forbidden in (
    'RETURN_NEAR_CONFIRM_SAMPLES =',
    'PHASE2_EDGE_CONFIRM_SAMPLES =',
    'def _v67_watch_base_worker',
    'def _apply_map_state',
):
    assert forbidden not in source, forbidden

print("SMOKE TEST V72 OK: zoom rueda + Zoom Extents + base centrada + leyenda fija")

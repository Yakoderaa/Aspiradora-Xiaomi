import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v99

for path in (SRC / "app_v99.py", SRC / "main_v99.py"):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v99.App, app_v99.app_v98.App)

# Early mapping must not generate a fake room surface.
early = {"points": [{"x": -0.1 * i, "y": 0.0} for i in range(12)]}
metrics = app_v99.App._v97_geometry_metrics(early)
assert metrics["mature"] is False
assert app_v99.App._v87_floor_cells(early) == set()

# Stronger V99 maturity gate.
assert app_v99.App.EARLY_MIN_POINTS >= 60
assert app_v99.App.EARLY_MIN_MINOR_SPAN_M >= 0.90
assert app_v99.App.EARLY_MIN_RATIO >= 0.45

# Bounds can grow but never shrink when unioned.
a = (-2.0, -2.0, 2.0, 2.0)
b = (-1.0, -1.0, 1.0, 1.0)
c = app_v99.App._v99_union_bounds(a, b)
assert c == a
d = app_v99.App._v99_union_bounds(a, (-3.0, -1.0, 2.5, 1.0))
assert d == (-3.0, -2.0, 2.5, 2.0)

# Translation must cover the map UI and dynamic selected-map labels.
dummy = app_v99.App.__new__(app_v99.App)
dummy.settings = {"language": "en"}
assert dummy._v98_translate("Plano de la vivienda") == "Home floor plan"
assert dummy._v98_translate("Mapa seleccionado: Mi casa") == "Selected map: Mi casa"
assert dummy._v98_translate("Eliminar") == "Delete"
dummy.settings = {"language": "pt"}
assert dummy._v98_translate("Plano de la vivienda") == "Planta da residência"
assert dummy._v98_translate("Mapa seleccionado: Mi casa") == "Mapa selecionado: Mi casa"
assert dummy._v98_translate("Renombrar") == "Renomear"

# Accent controls must explicitly stay white in every interactive state.
source = (SRC / "app_v99.py").read_text(encoding="utf-8")
for required in (
    'fg="#ffffff"',
    'activeforeground="#ffffff"',
    '"action_blue"',
    '"action_blue_hover"',
    "sin grid Xiaomi ni exploración 2D madura no se dibuja ninguna superficie estimada",
    "los bounds sólo pueden crecer",
    "self.local_map.clear_map(keep_rooms=False)",
    "self.plan_store.delete_map_data(map_id)",
    'self._button(actions, "Eliminar"',
):
    assert required in source, required

print(
    "SMOKE TEST V99 OK: no fake early surface + monotonic viewport + "
    "dark-theme action contrast + dynamic i18n + map deletion"
)

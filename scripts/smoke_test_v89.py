import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v89

for path in (SRC / "app_v89.py", SRC / "main_v89.py"):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v89.App, app_v89.app_v88.App)

# La política visual V89 debe interceptar el mismo método que V87/V88 usan
# tanto en el mapa principal como en las miniaturas.
class FakeCanvas:
    def create_line(self, *args, **kwargs):
        raise AssertionError("V89 no debe crear líneas del recorrido")

obj = object.__new__(app_v89.App)
obj._v89_route_draw_calls_blocked = 0
snapshot = {
    "points": [
        {"x": 0.0, "y": 0.0},
        {"x": 0.5, "y": 0.0},
        {"x": 0.5, "y": 0.5},
    ]
}
before = [dict(p) for p in snapshot["points"]]
assert obj._v87_draw_route(FakeCanvas(), snapshot, lambda x, y: (x, y)) is None
assert obj._v89_route_draw_calls_blocked == 1
assert snapshot["points"] == before

length = app_v89.App._v89_route_length(snapshot["points"])
assert abs(length - 1.0) < 1e-9

source = (SRC / "app_v89.py").read_text(encoding="utf-8")
for required in (
    "DIAGNÓSTICO V89 ACTIVO",
    "recorrido interno: OCULTO EN UI",
    "perímetro + relleno + base + robot",
    "LocalMapStore",
    "mapa grande y miniaturas",
):
    assert required in source, required

# La leyenda V89 no debe anunciar una capa visual que ya no existe.
legend_section = source.split("def _v88_install_legend", 1)[1].split(
    "# =========================================================== diagnóstico", 1
)[0]
assert 'text="Recorrido"' not in legend_section
assert "MAP_ROUTE" not in legend_section

print(
    "SMOKE TEST V89 OK: recorrido oculto en UI, datos intactos y diagnóstico conservado"
)

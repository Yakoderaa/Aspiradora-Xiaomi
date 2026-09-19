import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v87

for path in (SRC / "app.py", SRC / "app_v87.py", SRC / "xiaomi_e10.py", SRC / "main_v87.py"):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v87.App, app_v87.app_v86.App)

source_app = (SRC / "app.py").read_text(encoding="utf-8")
source_e10 = (SRC / "xiaomi_e10.py").read_text(encoding="utf-8")
source_v87 = (SRC / "app_v87.py").read_text(encoding="utf-8")

for required in ('"Limpiar bordes"', '"Espiral"', "def start_edge_clean", "def start_spiral_clean"):
    assert required in source_app, required

for required in (
    "def start_edge",
    "def start_spiral",
    "return self._start_with_sweep_type(mode, 0)",
    "return self._start_with_sweep_type(mode, 2)",
    "return self._start_with_sweep_type(mode, 4)",
):
    assert required in source_e10, required

assert "DIAGNÓSTICO V87 ACTIVO" in source_v87

for required in (
    "def _v87_floor_cells",
    "def _v87_draw_floor",
    "def _v87_draw_base_and_robot",
    "sin grilla",
    "base verde con carga",
    "no altera coordenadas, cobertura ni lógica física",
):
    assert required in source_v87, required

# La huella visual debe crear superficie continua alrededor de una trayectoria
# mínima sin alterar los puntos originales.
snapshot = {
    "points": [
        {"x": 0.0, "y": 0.0},
        {"x": 0.1, "y": 0.0},
        {"x": 0.2, "y": 0.0},
    ]
}
before = [dict(p) for p in snapshot["points"]]
cells = app_v87.App._v87_floor_cells(snapshot)
assert len(cells) >= 9
assert snapshot["points"] == before

print(
    "SMOKE TEST V87 OK: Global=0, Bordes=2, Espiral=4 y mapa continuo tipo Mi Home"
)

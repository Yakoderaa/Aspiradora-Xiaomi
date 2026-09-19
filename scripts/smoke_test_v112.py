import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v112
import xiaomi_e10_map_v112

for path in (
    SRC / "app_v112.py",
    SRC / "main_v112.py",
    SRC / "xiaomi_e10_map_v112.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v112.App, app_v112.app_v111.App)
assert issubclass(
    xiaomi_e10_map_v112.XiaomiE10MapV112,
    xiaomi_e10_map_v112.XiaomiE10MapV111,
)

# El caso real V111: baseline principal 265 no puede terminar en 196.
minimum = xiaomi_e10_map_v112.XiaomiE10MapV112._v112_min_retained_cells(265)
assert minimum == 223
assert 196 < minimum
assert 240 >= minimum

# Una planta no puede ser menor que la trayectoria por más de su margen físico.
ok, axes = xiaomi_e10_map_v112.XiaomiE10MapV112._v112_span_gate({
    "path_span": (4.70, 2.00),
    "floor_span": (4.30, 1.70),
})
assert ok and axes["x"] and axes["y"]

bad, axes = xiaomi_e10_map_v112.XiaomiE10MapV112._v112_span_gate({
    "path_span": (4.70, 2.00),
    "floor_span": (3.60, 1.70),
})
assert not bad and not axes["x"]

# Contrato V88: transform debe seguir siendo aceptado.
sig = inspect.signature(app_v112.App._v87_draw_rooms_and_plan)
assert "transform" in sig.parameters
assert sig.parameters["transform"].default is None

app_source = (SRC / "app_v112.py").read_text(encoding="utf-8")
for forbidden in (
    "vacuum.stop()\n        except",
    "vacuum.manual(5)",
):
    # No deben existir en el monitor V112.
    monitor = app_source.split(
        "def _v81_dock_monitor_worker", 1
    )[1].split("def _handle_ui_event", 1)[0]
    assert forbidden not in monitor, forbidden

for required in (
    "Retorno prolongado",
    "auto-stops bloqueados",
    "MIN_V93_RETENTION_RATIO",
):
    combined = app_source + (
        SRC / "xiaomi_e10_map_v112.py"
    ).read_text(encoding="utf-8")
    assert required in combined, required

print(
    "SMOKE TEST V112 OK: V93 retention + path span gate + "
    "renderer contract + dock timeout without auto-stop"
)

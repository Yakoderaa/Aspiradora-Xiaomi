import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v109
import robot_plans
import xiaomi_e10_map_v109

for path in (
    SRC / "app_v109.py",
    SRC / "main_v109.py",
    SRC / "xiaomi_e10_map_v109.py",
    SRC / "robot_plans.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v109.App, app_v109.app_v108.App)
assert issubclass(
    xiaomi_e10_map_v109.XiaomiE10MapV109,
    xiaomi_e10_map_v109.XiaomiE10MapV107,
)

# Privacidad.
redacted, count = app_v109.App._v109_redact_ips(
    "Conectado · 192.168.1.27 | otra=10.0.0.5"
)
assert redacted == "Conectado · [IP OCULTA] | otra=[IP OCULTA]"
assert count == 2

# Conversión correcta: mapa local en metros -> E10 raw 0,10 m/unidad.
plan = {"device_origin": {"x": 60.0, "y": 60.0}}
x, y = robot_plans.local_point_to_device(1.0, -0.5, plan)
assert (x, y) == (70.0, 55.0)
rect = robot_plans.local_rect_to_device(
    {"x0": -1.0, "y0": -0.5, "x1": 1.0, "y1": 0.5},
    plan,
)
assert rect == {
    "x0": 50.0,
    "y0": 55.0,
    "x1": 70.0,
    "y1": 65.0,
}

# Transformaciones físicas conservan cantidad de celdas.
side = 8
cells = [0] * (side * side)
cells[3 * side + 4] = 1
cells[4 * side + 5] = 1
out = xiaomi_e10_map_v109.XiaomiE10MapV109._v109_transform_cells(
    cells,
    side,
    [4.0, 4.0],
    0.2,
    "mirror_y",
)
assert sum(out) == 2

# El scoring debe preferir piso cercano a la trayectoria.
candidate = [0] * (side * side)
candidate[3 * side + 4] = 1
candidate[3 * side + 5] = 1
score_near, diag_near = (
    xiaomi_e10_map_v109.XiaomiE10MapV109._v109_path_score(
        candidate,
        side,
        [4.0, 4.0],
        0.2,
        [(0.1, 0.1), (0.3, 0.1)],
        "identity",
        {"components": 1, "largest_ratio": 1.0, "adjacency_ratio": 0.5},
    )
)
score_far, _ = (
    xiaomi_e10_map_v109.XiaomiE10MapV109._v109_path_score(
        candidate,
        side,
        [4.0, 4.0],
        0.2,
        [(2.0, 2.0), (2.2, 2.0)],
        "identity",
        {"components": 1, "largest_ratio": 1.0, "adjacency_ratio": 0.5},
    )
)
assert score_near > score_far
assert diag_near["coverage"] > 0.0

source = (SRC / "app_v109.py").read_text(encoding="utf-8")
for required in (
    'super()._set_connection(True, "Conectado")',
    "DIAGNÓSTICO V109 DE EMERGENCIA",
    "una excepción heredada no puede dejar F12 en blanco",
    "Administrar mapas",
    "Habitaciones",
    "Zonas",
    "Bloquear / desbloquear",
    "toda la gestión de habitaciones/zonas vive a la derecha",
    "escala local→raw=metros/0.10",
):
    assert required in source, required

plans_source = (SRC / "robot_plans.py").read_text(encoding="utf-8")
assert "LOCAL_METERS_PER_RAW = 0.10" in plans_source
assert "float(x) / LOCAL_METERS_PER_RAW" in plans_source

print(
    "SMOKE TEST V109 OK: safe diagnostics + IP privacy + "
    "right sidebar + zone raw scale + physical final layout"
)

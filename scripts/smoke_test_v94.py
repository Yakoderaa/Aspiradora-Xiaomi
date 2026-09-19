import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v94

for path in (
    SRC / "app_v94.py",
    SRC / "main_v94.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v94.App, app_v94.app_v93.App)

cases = [
    (0, 0, False, "Dormido", "idle"),
    (1, 0, False, "En espera", "idle"),
    (2, 0, False, "Pausado", "paused"),
    (3, 0, False, "Volviendo a la base", "returning"),
    (4, 0, False, "Cargando", "charging"),
    (5, 0, False, "Aspirando", "cleaning"),
    (5, 0, True, "Aspirando · mapeando", "cleaning"),
    (6, 0, False, "Aspirando y trapeando", "cleaning"),
    (7, 0, False, "Trapeando", "cleaning"),
    (8, 0, False, "Actualizando firmware", "updating"),
]
for code, fault, mapping, expected_text, expected_style in cases:
    text, style = app_v94.App._v94_display_state(
        code,
        "fallback",
        fault,
        mapping_active=mapping,
    )
    assert text == expected_text, (code, text)
    assert style == expected_style, (code, style)

# Un fault residual no debe tapar un estado físico activo.
text, style = app_v94.App._v94_display_state(
    4,
    "Cargando",
    2105,
    mapping_active=False,
)
assert text == "Cargando"
assert style == "charging"

text, style = app_v94.App._v94_display_state(
    5,
    "Aspirando",
    12,
    mapping_active=False,
)
assert text == "Aspirando"
assert style == "cleaning"

# Fuera de un estado físico activo, el fault sí sigue siendo visible.
text, style = app_v94.App._v94_display_state(
    1,
    "En espera",
    12,
    mapping_active=False,
)
assert text == "Error · código 12"
assert style == "error"

source = (SRC / "app_v94.py").read_text(encoding="utf-8")
for required in (
    "ESTADO ·",
    "Volviendo a la base",
    "Cargando",
    "Aspirando",
    "Aspirando y trapeando",
    "Trapeando",
    "Actualizando firmware",
    "_render_status",
    "_set_connection",
    "_sync_mapping_step_buttons",
):
    assert required in source, required

print(
    "SMOKE TEST V94 OK: estado físico global permanente + "
    "conexión/fault + sufijo de mapeo"
)

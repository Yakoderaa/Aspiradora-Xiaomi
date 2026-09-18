import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v75

source = (SRC / "app_v75.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v75.App, app_v75.app_v74.App)

# Regresión del origen V74 observado: la lectura previa no puede fijar (0,0).
app = app_v75.App.__new__(app_v75.App)
app._v71_session_origin_raw = None
app._v71_session_origin_source = None
assert app._v71_set_origin((0.0, 39.0), "10/24 antes de mapeo único V74") is False
assert app._v71_session_origin_raw is None

# Dos posiciones distintas son el gate mínimo.
assert app._v75_distinct_path_xy([
    {"x": 59, "y": 58},
]) == [(59.0, 58.0)]
assert app._v75_distinct_path_xy([
    {"x": 59, "y": 58},
    {"x": 59, "y": 58},
    {"x": 58, "y": 58},
]) == [(59.0, 58.0), (58.0, 58.0)]

# El cierre viejo queda neutralizado y recovery exige sesión vigente.
for required in (
    "mapping_seen_moving = False",
    "status=1 aislado no termina el mapa",
    "_v75_recovery_valid",
    "and not bool(getattr(self, \"_v74_finish_requested\", False))",
    "vacuum.start_mapping_interior()",
    "primera posición del nuevo sweep normal · V75",
):
    assert required in source, required

# Ninguna recuperación puede reiniciar sin revalidar inmediatamente antes.
restart_index = source.index("vacuum.start_mapping_interior()")
window = source[max(0, restart_index - 500):restart_index]
assert "_v75_recovery_valid" in window

print(
    "SMOKE TEST V75 OK: origen post-START + bloqueo de fin legado + "
    "recovery cancelable/revalidada"
)

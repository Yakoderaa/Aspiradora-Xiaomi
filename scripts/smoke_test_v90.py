import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v90

for path in (SRC / "app_v90.py", SRC / "main_v90.py"):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v90.App, app_v90.app_v89.App)
assert app_v90.App.START_CONFIRM_TIMEOUT_MS == 60000

# Objeto mínimo para probar el gate sin iniciar Tk ni tocar el robot.
obj = object.__new__(app_v90.App)
obj.mapping_active = True
obj._v74_finish_requested = False
obj._v84_returning = False
obj._v90_start_confirmed = False
obj._v90_departure_confirmed = False
obj._v90_status4_prestart_blocks = 0
obj._v90_status4_nodeparture_blocks = 0
obj._v90_return_predeparture_blocks = 0
obj._v90_close_permissions = 0
obj._v90_last_gate_reason = ""
obj._v90_departure_confirmed_at = None
obj._v90_departure_source = None
obj._v90_start_confirmed_at = None
obj._v90_start_serial = None
obj._v90_prestart_points = 0
obj._v90_prestart_saved = 0
obj._v84_physical_status = 4
obj._v74_last_status = 4
obj._v81_dock_last_status = 4
obj._v84_dock_latched = False

# 1) Status=4 antes del START jamás puede cerrar.
assert obj._v84_should_finalize_dock() is False
assert obj._v90_status4_prestart_blocks == 1

# 2) START confirmado sin salida física todavía tampoco puede cerrar.
obj._v90_start_confirmed = True
assert obj._v84_should_finalize_dock() is False
assert obj._v90_status4_nodeparture_blocks == 1

# 3) Un status=3 temprano tampoco arma el estado de retorno.
assert obj._v84_note_returning("smoke") is False
assert obj._v84_returning is False
assert obj._v90_return_predeparture_blocks == 1

# 4) Un estado físico de limpieza posterior al START sí confirma salida.
assert obj._v90_note_physical_status(5, "smoke") is True
assert obj._v90_departure_confirmed is True
assert obj._v90_departure_source == "smoke: status=5"

# 5) Una vez START+salida están confirmados, el cierre V84 vuelve a operar.
assert obj._v84_should_finalize_dock() is True
assert obj._v90_close_permissions == 1

source = (SRC / "app_v90.py").read_text(encoding="utf-8")
for required in (
    "DIAGNÓSTICO V90 ACTIVO",
    "status=4 previo al START",
    "status 5/6/7",
    "START no se confirma en 60 s",
    "puntos 10/24 por sí solos nunca prueban salida física",
    "START tardío/obsoleto descartado por V90",
    "vacuum.dock()",
):
    assert required in source, required

# V89 sigue siendo la política visual heredada.
assert app_v90.App.ROUTE_VISIBLE is False

print(
    "SMOKE TEST V90 OK: dock bloqueado antes de START/salida y habilitado sólo tras status físico 5/6/7"
)

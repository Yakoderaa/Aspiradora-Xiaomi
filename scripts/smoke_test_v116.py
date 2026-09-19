import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v116


for path in (
    SRC / "app_v116.py",
    SRC / "main_v116.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v116.App, app_v116.app_v115.App)

# La bandera local de mapeo sólo puede bloquear si el robot está realmente
# activo. Dock/carga/espera convierten la bandera en residual.
assert app_v116.App._v116_mapping_flag_is_stale(True, 4)
assert app_v116.App._v116_mapping_flag_is_stale(True, 3)
assert app_v116.App._v116_mapping_flag_is_stale(True, 1)
assert not app_v116.App._v116_mapping_flag_is_stale(True, 5)
assert not app_v116.App._v116_mapping_flag_is_stale(True, 6)
assert not app_v116.App._v116_mapping_flag_is_stale(False, 4)

source = (SRC / "app_v116.py").read_text(encoding="utf-8")
for required in (
    "command=self.start_clean",
    "clic recibido",
    "_v116_clean_clicks",
    "_v116_rebind_clean_buttons",
    "_v116_clear_stale_mapping_state",
    "sin native_grid final; limpieza global permitida",
    "start_global_verified",
):
    assert required in source, required

# V116 no puede volver a introducir la condición V115 que rechazaba todo
# start_clean simplemente por mapping_active.
start_block = source.split("    def start_clean(self):", 1)[1].split(
    "    # =========================================================== diagnóstico",
    1,
)[0]
assert "Terminá o detené el mapeo antes de iniciar" not in start_block

print(
    "SMOKE TEST V116 OK: botones reenlazados + clic observable + "
    "mapping_active residual no bloquea status charging/idle"
)

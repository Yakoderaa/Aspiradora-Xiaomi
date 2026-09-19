import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v95

for path in (
    SRC / "app_v95.py",
    SRC / "main_v95.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v95.App, app_v95.app_v94.App)

due = app_v95.App._v95_recovery_due
assert due(20.0, 10.0, 0.0, 0.0, 6.0) is True
assert due(14.0, 10.0, 0.0, 0.0, 6.0) is False
assert due(20.0, 10.0, 18.0, 0.0, 6.0) is False
assert due(30.0, 10.0, 18.0, 22.0, 6.0) is True
assert due(30.0, 0.0, 0.0, 0.0, 6.0) is False

source = (SRC / "app_v95.py").read_text(encoding="utf-8")
for required in (
    "Iniciar limpieza",
    "Volver a base",
    "MAP_ACTIVITY_GRACE_SECONDS",
    "_poll_local_map",
    "_v38_maybe_poll_map_file",
    "status 5/6/7",
    "set_suction",
    "set_water",
    "mapping_active",
):
    assert required in source, required

print(
    "SMOKE TEST V95 OK: watchdog LAN/Cloud + rearm por status activo + "
    "controles globales de limpieza/base"
)

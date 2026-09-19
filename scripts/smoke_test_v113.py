import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v111
import app_v113

for path in (
    SRC / "app_v113.py",
    SRC / "main_v113.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v113.App, app_v111.App)

sig = inspect.signature(app_v113.App._v87_draw_rooms_and_plan)
assert "transform" in sig.parameters
assert sig.parameters["transform"].default is None

source = (SRC / "app_v113.py").read_text(encoding="utf-8")
monitor = source.split(
    "def _v81_dock_monitor_worker", 1
)[1].split("def _handle_ui_event", 1)[0]

assert "vacuum.stop()" not in monitor
assert "vacuum.manual(" not in monitor
assert "MIN_V93_RETENTION_RATIO" not in source
assert "se conserva exactamente la selección geométrica de V111" in source
assert "no existe retención mínima artificial" in source

print(
    "SMOKE TEST V113 OK: V111 geometry frozen + renderer contract + "
    "dock timeout without automatic stop"
)

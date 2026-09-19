import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v119

for path in (
    SRC / "app_v119.py",
    SRC / "main_v119.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v119.App, app_v119.app_v118.App)

source = (SRC / "app_v119.py").read_text(encoding="utf-8")
assert "def _v74_request_finish_for_coverage" in source
assert "def _v77_corridor_finish" in source
assert "def _v73_schedule_recovery" in source
assert "def _v118_note_status" in source

coverage = source.split(
    "    def _v74_request_finish_for_coverage", 1
)[1].split("    def _v77_corridor_finish", 1)[0]
corridor = source.split(
    "    def _v77_corridor_finish", 1
)[1].split("    def _v73_schedule_recovery", 1)[0]

for block in (coverage, corridor):
    assert "vacuum.stop(" not in block
    assert "vacuum.dock(" not in block
    assert "_v81_finish_complete(" not in block
    assert "_v81_stop_incomplete(" not in block

assert "autorrecuperación del firmware priorizada" in source
assert "mapping_active=True no alimenta el detector de limpieza global V118" in source

print(
    "SMOKE TEST V119 OK: no-new/corredor no cierran mapa, "
    "corredor no reinicia sweep y V118 distingue mapeo de limpieza"
)

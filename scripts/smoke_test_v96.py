import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v96

for path in (
    SRC / "app_v96.py",
    SRC / "main_v96.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v96.App, app_v96.app_v95.App)
assert app_v96.App.INITIAL_BUFFER_START_RADIUS >= 0.80
assert app_v96.App.CLOUD_FILE_POLL_SECONDS >= 8.0
assert app_v96.App.LOCAL_ACTIVE_POLL_MS >= 700

# El caso real de V95: la primera pose útil puede llegar a ~0.45 m del dock.
dummy = app_v96.App.__new__(app_v96.App)
dummy._v80_initial_buffer = []
dummy._v80_initial_validated = False
dummy._v80_initial_buffer_rejected = 0
dummy._v80_initial_buffer_resets = 0
dummy._v80_initial_flush_count = 0
dummy._v96_initial_last_reason = "—"
dummy._v96_initial_first_distance = None
dummy._v96_initial_span = 0.0
dummy._v96_initial_late_starts = 0
dummy._v96_initial_discontinuities = 0

out = []
for x in (-0.45, -0.40, -0.35, -0.30):
    out = app_v96.App._v80_buffer_initial_point(
        dummy,
        {"x": x, "y": -0.10, "phi": 0.0},
    )
assert dummy._v80_initial_validated is True
assert len(out) == 4
assert dummy._v80_initial_flush_count == 4
assert dummy._v96_initial_late_starts == 1

# Una discontinuidad grande antes de validar no puede aprobar el buffer.
dummy2 = app_v96.App.__new__(app_v96.App)
dummy2._v80_initial_buffer = []
dummy2._v80_initial_validated = False
dummy2._v80_initial_buffer_rejected = 0
dummy2._v80_initial_buffer_resets = 0
dummy2._v80_initial_flush_count = 0
dummy2._v96_initial_last_reason = "—"
dummy2._v96_initial_first_distance = None
dummy2._v96_initial_span = 0.0
dummy2._v96_initial_late_starts = 0
dummy2._v96_initial_discontinuities = 0
app_v96.App._v80_buffer_initial_point(
    dummy2, {"x": -0.20, "y": 0.0, "phi": 0.0}
)
app_v96.App._v80_buffer_initial_point(
    dummy2, {"x": 0.70, "y": 0.0, "phi": 0.0}
)
assert dummy2._v80_initial_validated is False
assert dummy2._v96_initial_discontinuities == 1

# Gate Cloud: jamás debe arrancar otro worker si ya hay uno activo.
due = app_v96.App._v96_cloud_due
assert due(True, 100.0, 0.0, 12.0) is False
assert due(False, 100.0, 95.0, 12.0) is False
assert due(False, 100.0, 80.0, 12.0) is True

source = (SRC / "app_v96.py").read_text(encoding="utf-8")
for required in (
    "rebases V85 bloqueados",
    "solapamiento=PROHIBIDO",
    "UI_EVENT_BUDGET",
    "RENDER_MIN_INTERVAL_SECONDS",
    "_v96_schedule_local_poll",
    "INITIAL_BUFFER_START_RADIUS = 0.90",
):
    assert required in source, required

print(
    "SMOKE TEST V96 OK: arranque tardío continuo + V85 bloqueado pre-gate + "
    "un solo worker LAN/Cloud + render/UI coalescidos"
)

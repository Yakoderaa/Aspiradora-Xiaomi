import ast
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v81

source = (SRC / "app_v81.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v81.App, app_v81.app_v80.App)


def blank_app():
    app = app_v81.App.__new__(app_v81.App)
    app._v81_min_x = None
    app._v81_max_x = None
    app._v81_min_y = None
    app._v81_max_y = None
    app._v81_completion_ready = False
    app._v81_completion_missing = []
    app._v81_corridor_incomplete_hits = 0
    app._v81_no_new_deferrals = 0
    app._v81_incomplete_reason = None
    app._v81_dock_commands_sent = 0
    app._v81_dock_monitor_started_at = None
    app._v81_dock_last_status = None
    app._v81_dock_last_distance = None
    app._v81_dock_near_samples = 0
    app._v81_dock_timeout = False
    app._v81_dock_confirmed = False
    app._v74_coverage_cells = set()
    app._v74_started_at = time.monotonic() - 400.0
    app._v71_session_max_departure = 0.0
    return app


app = blank_app()

# V80 habría terminado el ejemplo real con ~10 celdas y 0.95 m.
for i in range(10):
    app._v74_coverage_cells.add((i, 0))
app._v71_session_max_departure = 0.95
app._v81_min_x = -0.8
app._v81_max_x = 0.5
app._v81_min_y = -0.2
app._v81_max_y = 0.3
state = app._v81_completion_state()
assert state["ready"] is False
assert any("cobertura" in x for x in state["missing"])
assert any("salida" in x for x in state["missing"])
assert any("ancho Y" in x for x in state["missing"])

# Cobertura suficientemente extendida sí puede completar.
app._v74_coverage_cells = {(x, y) for x in range(-2, 3) for y in range(-2, 3)}
app._v71_session_max_departure = 1.6
app._v81_min_x = -0.8
app._v81_max_x = 0.8
app._v81_min_y = -0.7
app._v81_max_y = 0.7
state = app._v81_completion_state()
assert state["ready"] is True

assert app_v81.App.MAX_INCOMPLETE_CORRIDOR_EVENTS >= 3
assert app_v81.App.DOCK_SEARCH_TIMEOUT_SECONDS >= 90.0
assert app_v81.App.DOCK_NEAR_RADIUS_METERS >= 0.60

for required in (
    "corredor repetido nunca convierte un mapa insuficiente en mapa terminado",
    "durante retorno no hay antiatasco, reversa ni segundo dock",
    "No se reenviaron comandos de dock",
    "MAX_INCOMPLETE_CORRIDOR_EVENTS = 4",
):
    assert required in source, required

# Regresión crítica: el monitor V81 jamás debe emitir un segundo vacuum.dock().
monitor_start = source.index("def _v81_dock_monitor_worker")
monitor_end = source.index("# ============================================================= eventos UI")
monitor = source[monitor_start:monitor_end]
assert "vacuum.dock()" not in monitor
assert "vacuum.manual(4)" not in monitor

print(
    "SMOKE TEST V81 OK: completitud reforzada + corredor no finaliza "
    "prematuramente + dock de un solo comando"
)

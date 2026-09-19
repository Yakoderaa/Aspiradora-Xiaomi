import ast
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v86

source = (SRC / "app_v86.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v86.App, app_v86.app_v85.App)

app = app_v86.App.__new__(app_v86.App)

# ETA de carga: +4 puntos en 4 minutos => 1 %/min.
charge = deque([(0.0, 50), (120.0, 52), (240.0, 54)])
rate = app._v86_estimate_rate(charge, "charge")
assert rate is not None and abs(rate - 1.0) < 1e-9
eta = app._v86_eta_minutes(54, rate, "charge")
assert eta is not None and abs(eta - 46.0) < 1e-9

# ETA de aspirado: -4 puntos en 4 minutos => 1 %/min.
clean = deque([(0.0, 100), (120.0, 98), (240.0, 96)])
rate = app._v86_estimate_rate(clean, "clean")
assert rate is not None and abs(rate - 1.0) < 1e-9
eta = app._v86_eta_minutes(96, rate, "clean")
assert eta is not None and abs(eta - 96.0) < 1e-9

# El aviso debe diferirse mientras el dock físico no esté confirmado.
app._v86_completion_pending = False
app._v86_completion_deferred = 0
app._v86_completion_delivered_at = None
app._v84_dock_latched = False
app._v84_physical_status = 3
app._v81_dock_confirmed = False
assert app._v70_notify_mapping_complete() is False
assert app._v86_completion_pending is True
assert app._v86_completion_deferred == 1

for required in (
    "aviso de mapeo terminado no aparece hasta status=4",
    "ETA de carga usa la tasa real observada",
    "autonomía de aspirado usa la tasa real observada",
    "ejecutable se empaqueta desde main_v86",
):
    assert required in source, required

print(
    "SMOKE TEST V86 OK: aviso diferido hasta dock + ETA carga/aspirado "
    "basada en consumo real"
)

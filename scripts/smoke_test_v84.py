import ast
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v84

source = (SRC / "app_v84.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v84.App, app_v84.app_v83.App)


class FakeMap:
    def __init__(self):
        self.robot = {"x": 2.0, "y": -0.5, "angle": 1.0}
        self.base = {"x": 0.0, "y": 0.0, "angle": 0.0}

    def snapshot(self):
        return {
            "robot": dict(self.robot) if self.robot else None,
            "charging_base": dict(self.base) if self.base else None,
        }

    def set_robot(self, robot):
        self.robot = dict(robot) if isinstance(robot, dict) else robot

    def set_charging_base(self, base):
        self.base = dict(base) if isinstance(base, dict) else base


def blank_app():
    app = app_v84.App.__new__(app_v84.App)

    app._v84_physical_status = 3
    app._v84_returning = True
    app._v84_dock_latched = False
    app._v84_dock_source = None
    app._v84_dock_confirmed_at = None
    app._v84_recovery_invalidations = 0
    app._v84_timeout_overrides = 0
    app._v84_robot_snaps = 0
    app._v84_initial_status4_ignored = 0
    app._v84_stale_robot_before_dock = None
    app._v84_last_close_reason = None

    app._v75_recovery_generation = 7
    app._v75_recovery_cancellations = 0
    app._v73_recovery_active = True
    app._v73_pose_window = deque()
    app._v73_repeat_triggered = True

    app._v81_dock_timeout = True
    app._v81_dock_confirmed = False
    app._v81_dock_last_status = 3
    app._v81_dock_last_distance = 1.2
    app._v73_dock_failed = True
    app._v73_dock_guard_active = True

    app._v74_last_status = 3
    app._v74_finish_requested = False
    app._v73_phase_saved = {1: 0, 2: 0}
    app._v71_session_max_departure = 0.0
    app.mapping_active = False

    app.local_map = FakeMap()
    app._render_maps = lambda: None
    return app


# status=4 debe ganar incluso si V81 ya había marcado timeout.
app = blank_app()
first = app._v84_mark_dock_authoritative("smoke status=4", final=True)
assert first is True
assert app._v84_dock_latched is True
assert app._v84_physical_status == 4
assert app._v81_dock_confirmed is True
assert app._v81_dock_timeout is False
assert app._v73_dock_failed is False
assert app._v73_dock_guard_active is False
assert app._v75_recovery_generation > 7
assert app._v84_timeout_overrides == 1

# El robot visual debe terminar exactamente encima del dock.
assert app._v84_snap_robot_to_dock(force=True) is True
assert app.local_map.robot["x"] == 0.0
assert app.local_map.robot["y"] == 0.0
assert app.local_map.base["x"] == 0.0
assert app.local_map.base["y"] == 0.0
assert app._v84_stale_robot_before_dock == (2.0, -0.5)

# Ningún recovery puede validarse una vez iniciado el retorno o fijado el dock.
allowed, meta = app._v83_recovery_gate(
    "pasadas ida/vuelta sobre el mismo corredor"
)
assert allowed is False
assert "retorno/base física" in meta["reason"]

# Un status=4 inicial, antes de movimiento real, no debe cerrar un mapa nuevo.
app = blank_app()
app.mapping_active = True
app._v84_returning = False
app._v84_dock_latched = False
app._v74_finish_requested = False
app._v73_phase_saved = {1: 0, 2: 0}
app._v71_session_max_departure = 0.0
assert app._v84_should_finalize_dock() is False

# En cuanto hubo recorrido real, status=4 sí es final físico.
app._v73_phase_saved[2] = 3
assert app._v84_should_finalize_dock() is True

for required in (
    "una sola lectura status=4 confirma físicamente el dock",
    "status=3 o status=4 invalida recovery/antiatasco",
    "robot se renderiza exactamente en la base (0,0)",
    "status=4 inicial antes de que el robot salga del dock no finaliza",
    "V74, V81, V83 y el render comparten el mismo estado físico V84",
    "Relectura final obligatoria ANTES de tocar las ruedas",
):
    assert required in source, required

print(
    "SMOKE TEST V84 OK: status=4 autoritativo, timeout anulado, "
    "recovery cancelado y robot visual fijado al dock"
)

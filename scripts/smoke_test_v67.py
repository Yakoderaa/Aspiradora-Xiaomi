import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v67


# 1) Evidencia de base: status operativo o charging-state físico.
assert app_v67.App._v67_base_evidence(4, None) == (True, "status=4 cargando")
assert app_v67.App._v67_base_evidence(1, 1) == (True, "battery charging-state=1")
assert app_v67.App._v67_base_evidence(3, 2) == (False, None)
assert app_v67.App._v67_should_send_dock(3, 2) is False
assert app_v67.App._v67_should_send_dock(1, 2) is True
assert app_v67.App._v67_should_send_dock(4, 2) is False


# 2) Armar transición no depende de Tk ni de status_ok; deja Paso 2 pendiente
# y levanta un watchdog propio.
class FakeVacuum:
    pass


class FakeThread:
    created = []

    def __init__(self, target=None, args=(), daemon=None, **kwargs):
        self.target = target
        self.args = args
        self.daemon = daemon
        FakeThread.created.append(self)

    def start(self):
        # No ejecutamos el worker en este test unitario.
        return None


orig_thread = app_v67.threading.Thread
app_v67.threading.Thread = FakeThread
try:
    app = app_v67.App.__new__(app_v67.App)
    app.vacuum = FakeVacuum()
    app.mapping_active = False
    app._auto_step2_pending = False
    app._auto_step2_scheduled = False
    app._v67_step1_session_active = True
    app._v67_watch_serial = 8
    app._v67_watch_running = False
    app._v67_start_scheduled = False
    app._v67_transition_diag = {}
    assert app._v67_arm_transition("edge_only_complete") is True
    assert app._auto_step2_pending is True
    assert app._v67_watch_running is True
    assert app._v67_watch_serial == 9
    assert app._v67_transition_diag["completion_event"] == "edge_only_complete"
    assert len(FakeThread.created) == 1
    assert FakeThread.created[0].args[1] == 9
finally:
    app_v67.threading.Thread = orig_thread


# 3) Commit de Paso 2 es one-shot. Si dos mecanismos intentan arrancarlo,
# sólo el primero cambia fase y lanza el worker.
app = app_v67.App.__new__(app_v67.App)
app.vacuum = FakeVacuum()
app._v67_watch_serial = 12
app._auto_step2_pending = True
app._auto_step2_scheduled = True
app._v67_watch_running = True
app._v67_start_scheduled = True
app.mapping_active = False
app.mapping_phase = 0
app.mapping_seen_moving = False
app.mapping_transitioning = False
app.mapping_step2_complete = False
app._v67_transition_diag = {"watch_serial": 12}

ui = []
launches = []
app.show_page = lambda page: ui.append(("page", page))
app._sync_mapping_step_buttons = lambda: ui.append(("sync",))
app._render_maps = lambda: ui.append(("render",))
app._set_banner = lambda text: ui.append(("banner", text))
app._v67_launch_interior_worker = lambda vacuum: launches.append(vacuum)

started = app._v67_commit_step2_start(
    12, 1, 1, 92, "battery charging-state=1"
)
assert started is True
assert app.mapping_active is True
assert app.mapping_phase == 2
assert app.mapping_transitioning is True
assert app._auto_step2_pending is False
assert app._v67_transition_diag["step2_started"] is True
assert len(launches) == 1

# Segundo disparo: no debe lanzar otra vez.
started_again = app._v67_commit_step2_start(
    12, 4, 1, 92, "status=4 cargando"
)
assert started_again is False
assert len(launches) == 1


# 4) Lectura combinada: charging-state puede faltar sin romper status=4.
class ProbeVacuum:
    def _get_many(self, defs):
        names = [x[0] for x in defs]
        assert names == ["status", "battery", "charging_state"]
        return {"status": 4, "battery": 77}

state = app_v67.App._v67_read_base_state(ProbeVacuum())
assert state["status"] == 4
assert state["battery"] == 77
assert state["charging_state"] is None


assert issubclass(app_v67.App, app_v67.app_v66.App)

print("SMOKE TEST V67 OK: watchdog base + charging-state + Paso 2 one-shot")

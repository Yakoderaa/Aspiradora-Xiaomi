from pathlib import Path
from types import SimpleNamespace
import inspect
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app_source = text("src/app_cleanroom.py")
core_source = text("src/fresh_robot_core.py")
arbiter_source = text("src/robot_command_arbiter.py")
scheduler_source = text("src/scheduler_agent.py")
main_source = text("src/main_current.py")
installer_source = text("installer/AspiradoraXiaomi.iss")
meta = json.loads(text("release_meta.json"))
# V152 es una regresión histórica: no exige seguir siendo la release activa.\n
assert "class App(app_v151.App)" in app_source
assert "FreshRobotCore" in app_source
assert "def start_new_mapping" in app_source
assert "def start_clean" in app_source
assert "def stop_clean" in app_source
assert "def dock" in app_source
assert "def finish_mapping" in app_source
assert "def _v114_run_safe_rectangles" in app_source
assert "def _v127_try_phase2_recovery" in app_source
assert "def _v74_watch_mapping_worker" in app_source
assert "def _v84_close_mapping_on_dock" in app_source
assert "def _sync_no_go_async" in app_source
assert "return super()._sync_no_go_async()" not in app_source
assert "core.sync_virtual_walls(" in app_source
assert "return False" in app_source

assert "start_mapping_whole_home" not in core_source
assert "start_mapping_exploration" not in core_source
assert "_v128" not in core_source
assert "arm_new_map" not in core_source
assert "_request_build_once" in core_source
assert "10, 17, [1]" in core_source
assert "START_ACTION_BY_MODE = {0: 3, 1: 5, 2: 6}" in core_source
assert "PROCESS_ARBITER = RobotCommandArbiter()" in core_source
assert "self.arbiter = arbiter or PROCESS_ARBITER" in core_source
assert "except FreshSessionCancelled:" in core_source
assert 'with self.arbiter._io_lock:' in core_source
assert 'with self._io_lock:' in arbiter_source
assert '"stop latent edge"' in core_source
assert '"twice clean off"' in core_source

assert "ReadMostlyMiotProxy" in arbiter_source
assert "_NAV_ACTIONS" in arbiter_source
assert "_NAV_PROPERTIES" in arbiter_source
assert "(9, 6)" in arbiter_source
assert "(8, 10)" in arbiter_source

assert "FreshRobotCore" in scheduler_source
assert "start_whole_clean" not in scheduler_source
assert "start_zone_clean" not in scheduler_source

assert "function PrepareToInstall" in installer_source
assert "taskkill.exe" in installer_source
assert "MySchedulerExeName" in installer_source

from fresh_robot_core import FreshRobotCore, FreshSessionCancelled
from robot_command_arbiter import (
    LegacyWriteBlocked,
    RobotCommandArbiter,
)

run_global_source = inspect.getsource(FreshRobotCore._run_global)
assert run_global_source.rfind("self.arbiter.finish(") < run_global_source.rfind(
    "on_finished(dict(diag))"
), run_global_source


class FakeDevice:
    def __init__(self):
        self.props = {
            (2, 1): 4,
            (2, 2): 0,
            (2, 4): 0,
            (2, 8): 2,
            (7, 1): 1,
            (7, 5): 3,
            (7, 6): 2,
            (8, 10): 1,
            (10, 14): 0,
            (10, 19): 0,
            (10, 24): [0, 0, 0],
            (10, 22): [0, 0, 0],
        }
        self.actions = []
        self.writes = []

    def info(self, *args, **kwargs):
        return SimpleNamespace(model="xiaomi.vacuum.b112")

    def get_property_by(self, siid, piid):
        return [{
            "siid": int(siid),
            "piid": int(piid),
            "code": 0,
            "value": self.props.get((int(siid), int(piid))),
        }]

    def send(self, command, payload):
        assert command == "get_properties", command
        rows = []
        for item in payload:
            key = (int(item["siid"]), int(item["piid"]))
            rows.append({
                "did": item["did"],
                "siid": key[0],
                "piid": key[1],
                "code": 0,
                "value": self.props.get(key),
            })
        return rows

    def set_property_by(self, siid, piid, value):
        key = (int(siid), int(piid))
        self.props[key] = value
        self.writes.append(("property", key, value))
        return [{"siid": key[0], "piid": key[1], "code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        key = (int(siid), int(aiid))
        self.actions.append((key, params))

        if key == (2, 2):
            self.props[(2, 1)] = 1
        elif key == (3, 1):
            self.props[(2, 1)] = 4
        elif key in ((2, 3), (2, 5), (2, 6)):
            self.props[(2, 1)] = {3: 5, 5: 6, 6: 7}[key[1]]
        elif key == (10, 17):
            # Reproduce el ACK ambiguo real del B112.
            return {"id": 77, "exe_time": 0}
        elif key == (7, 3):
            # En Fresh Core sólo se permite como STOP de estado latente.
            assert isinstance(params, list) and params[-1] == 2, params

        return {"code": 0, "out": []}


class FakeVacuum:
    def __init__(self):
        self.device = FakeDevice()

    def _get_many(self, definitions):
        raw = getattr(self.device, "_raw_device", self.device)
        return {
            name: raw.props.get((int(siid), int(piid)))
            for name, siid, piid in definitions
        }

    def status(self):
        raw = getattr(self.device, "_raw_device", self.device)
        return SimpleNamespace(status=raw.props.get((2, 1), -1))


vacuum = FakeVacuum()
arbiter = RobotCommandArbiter()
core = FreshRobotCore(vacuum, arbiter=arbiter, source="smoke")
raw = core.raw_device

session = arbiter.begin("mapping-smoke", "smoke")
try:
    neutral = core._neutralize_navigation_state()
    assert neutral["after"]["mode"] == 0, neutral
    assert neutral["after"]["sweep_type"] == 0, neutral
    assert neutral["after"]["repeat"] == 0, neutral
    assert raw.props[(8, 10)] == 0, raw.props

    before, after, suction, water = core._normalize(0, 2, 0)
    assert after["mode"] == 0, after
    assert after["sweep_type"] == 0, after
    assert raw.props[(7, 5)] == 2
    assert raw.props[(7, 6)] == 0

    build_response, build_ack = core._request_build_once()
    assert build_ack == "ambiguous-no-code", (build_response, build_ack)

    action, response = core._start_standard(0)
    assert action == (2, 3), action
    started = core._wait_started(session, timeout=1.0)
    assert int(started["status"]) == 5, started
    assert int(started["sweep_type"]) == 0, started

    # Cualquier writer heredado queda bloqueado aunque conozca el transporte.
    try:
        vacuum.device.call_action_by(7, 3, ["", 0, 1])
        raise AssertionError("7/3 heredado atravesó el proxy")
    except LegacyWriteBlocked:
        pass

    try:
        vacuum.device.set_property_by(2, 8, 2)
        raise AssertionError("sweep_type heredado atravesó el proxy")
    except LegacyWriteBlocked:
        pass
finally:
    arbiter.finish(session, "smoke done")

# El proxy sigue bloqueando navegación heredada incluso sin sesión activa.
try:
    vacuum.device.call_action_by(2, 3)
    raise AssertionError("START heredado quedó habilitado fuera de sesión")
except LegacyWriteBlocked:
    pass

# Sólo existe un START oper=1 en la prueba física: 2/3.
starts = []
for (key, params) in raw.actions:
    if key in {(2, 1), (2, 3), (2, 5), (2, 6), (7, 3)}:
        if key == (7, 3):
            if isinstance(params, list) and params[-1] == 1:
                starts.append((key, params))
        else:
            starts.append((key, params))
assert starts == [((2, 3), None)], starts

# Los 7/3 presentes son exclusivamente STOP para borrar estados latentes.
room_ops = [
    params[-1]
    for key, params in raw.actions
    if key == (7, 3) and isinstance(params, list)
]
assert room_ops and set(room_ops) == {2}, room_ops

assert arbiter.legacy_blocks >= 3, arbiter.audit_snapshot()

# Un rechazo explícito jamás puede contarse como aceptación.
try:
    core._assert_not_rejected({"code": -1}, "rechazo smoke")
    raise AssertionError("code=-1 fue aceptado")
except RuntimeError:
    pass

# Reproduce el defecto C de la auditoría al revés: si llega cancelar antes del
# START, Fresh Core ejecuta la cancelación y NO manda 2/3 después.
raw.props[(2, 1)] = 4
session_cancel_before_start = arbiter.begin("cancel-before-start", "smoke")
starts_before = len([
    row for row in raw.actions
    if row[0] in {(2, 1), (2, 3), (2, 5), (2, 6)}
])
try:
    session_cancel_before_start.cancel_action = "dock"
    try:
        core._start_standard(0, session=session_cancel_before_start)
        raise AssertionError("START fue enviado después de cancelar")
    except FreshSessionCancelled as exc:
        assert exc.reason == "dock_requested", exc.reason
finally:
    arbiter.finish(session_cancel_before_start, "cancel-before-start done")
starts_after = len([
    row for row in raw.actions
    if row[0] in {(2, 1), (2, 3), (2, 5), (2, 6)}
])
assert starts_after == starts_before, (starts_before, starts_after, raw.actions)
assert raw.props[(2, 1)] == 4

# Volver a base es cancelación de la secuencia, no un "fin normal" que permita
# iniciar otra pasada después.
raw.props[(2, 1)] = 5
session2 = arbiter.begin("cancel-dock-smoke", "smoke")
try:
    session2.cancel_action = "dock"
    reason = core._monitor_until_terminal(session2, mapping=False)
    assert reason == "dock_requested", reason
    assert raw.props[(2, 1)] == 4
finally:
    arbiter.finish(session2, "cancel smoke done")

# El transporte genérico heredado es de sólo lectura incluso cuando no hay
# una sesión activa.
try:
    vacuum.device.send("set_properties", [])
    raise AssertionError("send(set_properties) heredado atravesó el proxy")
except LegacyWriteBlocked:
    pass

try:
    vacuum.device.call_action_by(9, 6, ["[]"])
    raise AssertionError("paredes heredadas 9/6 atravesaron el proxy")
except LegacyWriteBlocked:
    pass

try:
    vacuum.device.set_property_by(8, 10, 1)
    raise AssertionError("twice-clean heredado atravesó el proxy")
except LegacyWriteBlocked:
    pass

print("V152 Fresh Core smoke OK")

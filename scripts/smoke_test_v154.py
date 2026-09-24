from pathlib import Path
from types import SimpleNamespace
import inspect
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


core_source = text("src/native_start_core.py")
app_source = text("src/app_native_start.py")

assert "class NativeStartCore" in core_source
assert "\"native start-sweep 2/1\"" in core_source
assert "A2/1 único START" in core_source
assert "set_property_by(" not in core_source
assert "7, 3" not in core_source
assert "10, 17" not in core_source
assert "def start_new_mapping" in app_source
assert "return self._baseline_disabled(\"Mapear vivienda\")" in app_source
assert "def _sync_no_go_async" in app_source
assert "src\\scheduler_baseline_disabled.py" in build
assert "RegDeleteValue" in installer
assert "AspiradoraXiaomiScheduler" in installer
assert "\n[Run]\n" not in installer.replace("\r\n", "\n")

from native_start_core import NativeStartCore
from robot_command_arbiter import RobotCommandArbiter


class FakeDevice:
    def __init__(self):
        self.props = {
            (2, 1): 4,
            (2, 2): 0,
            (2, 4): 0,
            (2, 8): 0,
            (7, 1): 0,
            (7, 5): 2,
            (7, 6): 0,
            (8, 10): 0,
            (10, 14): 0,
            (10, 19): 0,
            (10, 24): "60_60_0",
            (10, 22): "60_60",
        }
        self.actions = []
        self.writes = []
        self.reads_after_start = 0

    def info(self, *args, **kwargs):
        return SimpleNamespace(model="xiaomi.vacuum.b112")

    def get_property_by(self, siid, piid):
        key = (int(siid), int(piid))
        return [{"siid": key[0], "piid": key[1], "code": 0, "value": self.props.get(key)}]

    def send(self, command, payload):
        assert command == "get_properties"
        rows = []
        if self.props[(2, 1)] == 5:
            self.reads_after_start += 1
            if self.reads_after_start >= 3:
                self.props[(2, 1)] = 4
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
        self.writes.append((int(siid), int(piid), value))
        raise AssertionError("Native Start nunca debe escribir propiedades")

    def call_action_by(self, siid, aiid, params=None):
        key = (int(siid), int(aiid))
        self.actions.append((key, params))
        if key == (2, 1):
            self.props[(2, 1)] = 5
        elif key == (2, 2):
            self.props[(2, 1)] = 1
        elif key == (3, 1):
            self.props[(2, 1)] = 4
        else:
            raise AssertionError(f"acción inesperada: {key}")
        return {"code": 0, "out": []}


class FakeVacuum:
    def __init__(self):
        self.device = FakeDevice()

    def _get_many(self, definitions):
        raw = getattr(self.device, "_raw_device", self.device)
        if raw.props[(2, 1)] == 5:
            raw.reads_after_start += 1
            if raw.reads_after_start >= 3:
                raw.props[(2, 1)] = 4
        return {
            name: raw.props.get((int(siid), int(piid)))
            for name, siid, piid in definitions
        }


vacuum = FakeVacuum()
arbiter = RobotCommandArbiter()
core = NativeStartCore(vacuum, arbiter=arbiter, source="smoke")
raw = core.raw_device

started = []
finished = []
core._run_normal(
    lambda d: started.append(d),
    lambda d: finished.append(d),
)

assert raw.writes == [], raw.writes
assert raw.actions == [((2, 1), None)], raw.actions
assert started and started[0]["start_action"] == (2, 1), started
assert finished and finished[0]["error"] is None, finished
assert finished[0]["finish_reason"] == "dock", finished
assert finished[0]["writes_before_start"] == 0, finished

# Si el estado limpio esperado no está presente, la prueba aborta SIN escribir.
vacuum2 = FakeVacuum()
vacuum2.device.props[(2, 8)] = 2
core2 = NativeStartCore(vacuum2, arbiter=RobotCommandArbiter(), source="smoke2")
raw2 = core2.raw_device
core2._run_normal(None, lambda d: finished.append(d))
assert raw2.actions == [], raw2.actions
assert raw2.writes == [], raw2.writes
assert finished[-1]["error"] and "Baseline abortado sin escribir" in finished[-1]["error"]

print("V154 Native Start smoke OK")

import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v48
import app_v49
from xiaomi_cloud_history_v49 import XiaomiCloudHistoryV49


# 1) Un request Cloud que no vuelve debe expirar sin bloquear la sonda.
slow = XiaomiCloudHistoryV49.__new__(XiaomiCloudHistoryV49)
slow.REQUEST_TIMEOUT_SECONDS = 0.03
slow.did = "fake-did"
slow.region = "sg"
slow.session_data = {"user_id": "12345"}
slow._cloud = lambda: object()


def slow_request(self, cloud, **kwargs):
    time.sleep(0.12)
    return []


slow._request_variant = types.MethodType(slow_request, slow)
started = time.monotonic()
timed = slow._request_variant_timed(
    typ="prop",
    key="10.5",
    time_start=0,
    time_end=int(time.time()),
    include_uid=True,
)
elapsed = time.monotonic() - started
assert timed["ok"] is False
assert timed["timeout"] is True
assert "timeout>" in timed["error"]
assert elapsed < 0.10, elapsed


# 2) La matriz completa debe publicar progreso incremental 0..20 y terminar.
probe = XiaomiCloudHistoryV49.__new__(XiaomiCloudHistoryV49)
probe.did = "fake-did"
probe.region = "sg"
probe.session_data = {"user_id": "12345"}


def quick_timed(self, **kwargs):
    return {
        "ok": True,
        "timeout": False,
        "records": [],
        "error": None,
        "duration": 0.001,
    }


probe._request_variant_timed = types.MethodType(quick_timed, probe)
progress = []
summary = probe.read_probe(time.time() - 30, progress_callback=progress.append)
assert summary["plans"] == 20
assert summary["planned"] == 20
assert summary["timeouts"] == 0
assert summary["aborted_reason"] is None
assert len(summary["queries"]) == 20
assert progress
assert progress[0]["completed"] == 0
assert progress[-1]["completed"] == 20
assert progress[-1]["planned"] == 20
assert any(item["stage"] == "request" for item in progress)
assert any(item["stage"] == "complete" for item in progress)


# 3) Tres timeouts consecutivos deben cortar la matriz de forma controlada.
timeouting = XiaomiCloudHistoryV49.__new__(XiaomiCloudHistoryV49)
timeouting.did = "fake-did"
timeouting.region = "sg"
timeouting.session_data = {"user_id": "12345"}


def always_timeout(self, **kwargs):
    return {
        "ok": False,
        "timeout": True,
        "records": [],
        "error": "timeout>0.01s",
        "duration": 0.01,
    }


timeouting._request_variant_timed = types.MethodType(always_timeout, timeouting)
partial = timeouting.read_probe(time.time() - 30)
assert partial["plans"] == 3
assert partial["planned"] == 20
assert partial["timeouts"] == 3
assert partial["aborted_reason"]
assert len(partial["queries"]) == 3

assert issubclass(app_v49.App, app_v48.App)
print("SMOKE TEST V49 OK: progreso incremental + timeout por request + aborto controlado")

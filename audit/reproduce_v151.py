"""Offline defect reproductions for unchanged V151. Never connects to a robot.

These assertions document defects; passing means the defect was reproduced,
not that navigation was corrected. Run with the project's dependencies.
"""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import app_v151
import xiaomi_e10


class Device:
    def __init__(self, reject=False):
        self.calls = []
        self.reject = reject

    def call_action_by(self, siid, aiid, params=None):
        self.calls.append(["action", siid, aiid, params])
        return {"code": -1 if self.reject and (siid, aiid) == (7, 3) else 0, "out": []}

    def set_property_by(self, siid, piid, value):
        self.calls.append(["set", siid, piid, value])
        return [{"code": 0}]


def vacuum(reject=False):
    v = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
    v.device = Device(reject)
    v._targeted_clean_guard = 0
    v._global_clean_guard = 0
    v._motor_start_audit = []
    return v


class InlineThread:
    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def recovery_bypass():
    v = vacuum()
    v.status = lambda: SimpleNamespace(status=5)
    app = SimpleNamespace(
        vacuum=v, mapping_active=True, mapping_phase=2,
        _v151_direct_global_owner=True, _v145_session_latched=False,
        _v145_reset_guard=False, _v138_safe_reasserts_enabled=True,
        _v127_phase2_recovery_active=False, _v127_phase2_recoveries=0,
        _v127_phase2_recovery_last_at=0, _v94_last_status_code=5,
        _v74_last_discovery_at=time.monotonic()-200,
        _v84_returning=False, _v84_dock_latched=False,
        _v117_live_pose={"x": 1.5, "y": 0},
        _v128_phase2_reasserts=0, _v128_phase2_retries=0,
        _v128_phase2_idle_seen=0, _v77_corridor_samples=[],
        _post_ui=lambda *args: None,
    )
    for n in ("PHASE2_RECOVERY_MAX", "PHASE2_RECOVERY_NO_NEW_SECONDS",
              "PHASE2_RECOVERY_COOLDOWN_SECONDS", "PHASE2_REASSERT_WAIT_SECONDS",
              "PHASE2_REASSERT_RETRY_WAIT_SECONDS"):
        setattr(app, n, getattr(app_v151.App, n))
    app._v127_phase2_recovery_allowed = MethodType(app_v151.App._v127_phase2_recovery_allowed, app)
    app._v128_status_code = app_v151.App._v128_status_code
    assert app_v151.App._v151_owner_active(app)
    with patch("app_v128.threading.Thread", InlineThread):
        accepted = app_v151.App._v127_try_phase2_recovery(app, "corridor")
    assert accepted and ["action", 7, 3, ["", 0, 1]] in v.device.calls
    return {"owner_active": True, "recovery_dispatched": accepted, "calls": v.device.calls}


def rejected_prearm():
    v = vacuum(reject=True)
    v._get_many = lambda defs: {"status": 5 if any(c[:3] == ["action", 2, 3] for c in v.device.calls) else 4, "sweep_type": 2}
    v.start_mapping_whole_home(confirm_timeout=0.8)
    d = v._last_mapping_whole_home_diag
    assert d["success"] and d["sweep_type_after"] == 2
    assert "-1" in d["prearm_response"]
    return {"diag": d, "calls": v.device.calls}


def cancel_during_prearm():
    v = vacuum()
    cancelled = False

    def read(defs):
        nonlocal cancelled
        if any(c[:3] == ["action", 7, 3] for c in v.device.calls) and not cancelled:
            cancelled = True
            v.dock()  # User cancellation while the whole-home call is pending.
        return {"status": 5 if any(c[:3] == ["action", 2, 3] for c in v.device.calls) else 4, "sweep_type": 0}

    v._get_many = read
    v.start_mapping_whole_home(confirm_timeout=0.8)
    actions = [c[1:3] for c in v.device.calls if c[0] == "action"]
    assert actions == [[7, 3], [3, 1], [2, 3]], actions
    return {"cancelled": cancelled, "calls": v.device.calls, "late_start": True}


if __name__ == "__main__":
    result = {
        "meaning": "Offline reproductions of defects, not fixed regressions or physical navigation evidence",
        "reassert_bypasses_v151_owner": recovery_bypass(),
        "rejected_prearm_and_wrong_mode_report_success": rejected_prearm(),
        "trigger_after_cancel": cancel_during_prearm(),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

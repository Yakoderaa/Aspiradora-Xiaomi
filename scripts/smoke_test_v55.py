import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v55
from xiaomi_e10_probe_v55 import XiaomiE10ProbeV55


probe = XiaomiE10ProbeV55.__new__(XiaomiE10ProbeV55)
probe._v55_last_pose = None
probe._v55_track = []
probe._v55_motion_confirmed = False
probe._v55_xy_changes = 0
probe._v55_point_id = 550000
probe._v55_last_added_count = 0
probe._v55_action_reads_skipped = 0

pose_a = {"x": 61.0, "y": 59.0, "angle": 1.0}
pose_same = {"x": 61.0, "y": 59.0, "angle": 1.2}
pose_b = {"x": 62.0, "y": 59.0, "angle": 1.2}
pose_c = {"x": 62.0, "y": 58.0, "angle": 1.4}

assert probe._ingest_pose(pose_a) == 0
assert probe._v55_motion_confirmed is False
assert probe._v55_track == []

assert probe._ingest_pose(pose_same) == 0
assert probe._v55_motion_confirmed is False
assert probe._v55_track == []

assert probe._ingest_pose(pose_b) == 2
assert probe._v55_motion_confirmed is True
assert probe._v55_xy_changes == 1
assert len(probe._v55_track) == 2
assert (probe._v55_track[0]["x"], probe._v55_track[0]["y"]) == (61.0, 59.0)
assert (probe._v55_track[1]["x"], probe._v55_track[1]["y"]) == (62.0, 59.0)

assert probe._ingest_pose(pose_c) == 1
assert probe._v55_xy_changes == 2
assert len(probe._v55_track) == 3
assert (probe._v55_track[-1]["x"], probe._v55_track[-1]["y"]) == (62.0, 58.0)

# 10/12 debe quedar fuera del loop vivo.
out = probe._get_path_by_action([], None)
assert out == (None, [], None, (0, 0))
assert probe._v55_action_reads_skipped == 1

source = inspect.getsource(sys.modules["xiaomi_e10_probe_v55"])
for forbidden in ("call_action_by", "set_property_by", "10/18", "10/15", "10/6", "10/23"):
    assert forbidden not in source, f"V55 no debe ejecutar ni referenciar control inseguro: {forbidden}"

assert issubclass(app_v55.App, app_v55.app_v54.App)
print("SMOKE TEST V55 OK: 10/24 aislado no mueve + cambio X/Y crea trayectoria + 10/12 fuera del loop")

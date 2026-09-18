import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v73


class FakeVacuum:
    @staticmethod
    def parse_position(value):
        if isinstance(value, dict):
            return value
        parts = str(value).split("_")
        if len(parts) < 2:
            return None
        return {
            "x": float(parts[0]),
            "y": float(parts[1]),
            "angle": float(parts[2]) if len(parts) > 2 else 0.0,
        }


class FakeMap:
    def __init__(self):
        self.merges = []

    def merge_trajectory(self, points, phase=0):
        copy = [dict(point) for point in points]
        self.merges.append((int(phase), copy))
        return len(copy)


app = app_v73.App.__new__(app_v73.App)
app.vacuum = FakeVacuum()
app.local_map = FakeMap()
app.mapping_active = True
app.mapping_phase = 1
app.mapping_transitioning = False
app._v71_session_origin_raw = (61.0, 7.0)
app._v71_session_origin_source = "smoke"
app._v71_session_max_departure = 0.0
app._v71_path_points_seen = {1: 0, 2: 0}
app._v71_path_points_merged = {1: 0, 2: 0}
app._v73_session_phase = 1
app._v73_seen_track_keys = set()
app._v73_phase_new = {1: 0, 2: 0}
app._v73_phase_saved = {1: 0, 2: 0}
app._v73_transit_points = 0
app._v73_pose_window = deque()
app._v73_recovery_active = False
app._v73_recovery_count = 0
app._v73_last_recovery_at = 0.0
app._v73_last_recovery_reason = None
app._v73_repeat_triggered = False
app._v73_last_parsed_return_pose = None

# 1) Regresión exacta del diagnóstico V71: 10/24 llega como string.
distance = app._v71_raw_distance_to_origin("0_39_-2.058064")
assert distance is not None
assert abs(distance - math.hypot(61.0, 32.0)) < 1e-9
assert app._v73_last_parsed_return_pose == (0.0, 39.0, -2.058064)

# 2) Cada punto acumulado se consume una sola vez y conserva la fase al llegar.
base_cls = app_v73.app_v72.app_v71.app_v70.App
original_apply = base_cls._apply_map_state
base_cls._apply_map_state = lambda self, state: state
try:
    p1 = [
        {"id": 550001, "x": 61.0, "y": 7.0, "phi": 0.0, "update": 1},
        {"id": 550002, "x": 62.0, "y": 7.0, "phi": 0.1, "update": 1},
    ]
    app._apply_map_state({"path": p1, "robot": p1[-1], "path_source": "10/24"})
    assert len(app.local_map.merges) == 1
    assert app.local_map.merges[0][0] == 1
    assert len(app.local_map.merges[0][1]) == 2
    assert app._v73_phase_new[1] == 2

    # Repetir el mismo path acumulado no vuelve a guardarlo.
    app._apply_map_state({"path": p1, "robot": p1[-1], "path_source": "10/24"})
    assert len(app.local_map.merges) == 1

    # Punto nuevo durante regreso: se consume como tránsito, sin fase.
    app._v73_session_phase = 0
    p_return = p1 + [
        {"id": 550003, "x": 61.0, "y": 6.0, "phi": 0.2, "update": 1}
    ]
    app._apply_map_state({"path": p_return, "robot": p_return[-1], "path_source": "10/24"})
    assert len(app.local_map.merges) == 1
    assert app._v73_transit_points == 1

    # Punto realmente nuevo del interior va solamente a Paso 2.
    app._v73_session_phase = 2
    app.mapping_phase = 2
    p2 = p_return + [
        {"id": 550004, "x": 63.0, "y": 8.0, "phi": 0.3, "update": 1}
    ]
    app._apply_map_state({"path": p2, "robot": p2[-1], "path_source": "10/24"})
    assert len(app.local_map.merges) == 2
    assert app.local_map.merges[-1][0] == 2
    assert len(app.local_map.merges[-1][1]) == 1
    assert app._v73_phase_new[2] == 1
finally:
    base_cls._apply_map_state = original_apply

# 3) La detección de giro entiende radianes y grados.
assert abs(app._v73_angle_delta(0.0, math.pi / 2.0) - math.pi / 2.0) < 1e-9
assert abs(app._v73_angle_delta(0.0, 90.0) - math.pi / 2.0) < 1e-9

# 4) V73 conserva íntegra la UI/viewport V72.
assert issubclass(app_v73.App, app_v73.app_v72.App)

source = Path(SRC / "app_v73.py").read_text(encoding="utf-8")
for required in (
    "vacuum.reset_live_path_session()",
    'transformed["path"] = []',
    "V73 incremental por llegada/fase",
    "proximidad al origen NO autoriza Paso 2",
    "phase != 2",
    "self._v71_phase2_watch_serial += 1",
    "v73_dock_guard_failed",
    "DOCK_GUARD_STABLE_SECONDS",
    "super().dock()",
):
    assert required in source, required

# No debe volver a existir una confirmación de Paso 2 por estar simplemente
# cerca del origen: la proximidad se usa sólo como detector de acople fallido.
watch_start = source.index("def _v67_watch_base_worker")
watch_end = source.index("def _v67_recheck_base_before_step2")
watch_source = source[watch_start:watch_end]
assert 'confirm_mode = "session-origin"' not in watch_source
assert "near_origin" in watch_source
assert "v73_dock_retry" in watch_source

print(
    "SMOKE TEST V73 OK: fases incrementales + 10/24 string + anti-bucle "
    "+ acople protegido + viewport V72"
)

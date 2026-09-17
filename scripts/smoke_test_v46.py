import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v46
from xiaomi_cloud_history_v46 import XiaomiCloudHistoryV46


# Xiaomi suele envolver el value histórico en una lista JSON de un elemento.
record_prop = {
    "time": 2000,
    "value": json.dumps(["[100,1,2,0,1,2,3,0,1]"]),
}
points = XiaomiCloudHistoryV46._points_from_record(record_prop)
assert len(points) == 2
assert points[0]["id"] == 100
assert points[0]["x"] == 1.0 and points[0]["y"] == 2.0
assert points[1]["id"] == 101
assert points[1]["x"] == 2.0 and points[1]["y"] == 3.0

# Fallback event: history como [{piid:5,value:...}].
record_event = {
    "createTime": 2_001_000,
    "history": json.dumps([
        {"piid": 5, "value": "[200,3,4,0,1,4,5,0,1]"},
    ]),
}
event_points = XiaomiCloudHistoryV46._points_from_record(record_event)
assert len(event_points) == 2
assert event_points[0]["id"] == 200
assert event_points[1]["id"] == 201

# Un registro anterior al comienzo de la fase no puede contaminar el mapa.
merged, accepted, newest = XiaomiCloudHistoryV46._merge_records(
    [
        {"time": 1000, "value": "[1,50,50,0,1,51,50,0,1]"},
        record_prop,
    ],
    minimum_time=1500,
)
assert accepted == 1
assert len(merged) == 2
assert newest == 2000
assert merged[0]["x"] == 1.0

# Una única coordenada jamás confirma movimiento.
assert app_v46.App._distinct_xy_count([{"x": 0, "y": 0}]) == 1
assert app_v46.App._distinct_xy_count([
    {"x": 0, "y": 0},
    {"x": 0, "y": 0},
]) == 1
assert app_v46.App._distinct_xy_count([
    {"x": 0, "y": 0},
    {"x": 0.2, "y": 0},
]) == 2

# Detección conservadora de unidades usando distancia entre poses.
assert app_v46.App._detect_history_scale([
    {"x": 0, "y": 0}, {"x": 0.25, "y": 0}, {"x": 0.5, "y": 0},
]) == 1.0
assert app_v46.App._detect_history_scale([
    {"x": 0, "y": 0}, {"x": 25, "y": 0}, {"x": 50, "y": 0},
]) == 0.01
assert app_v46.App._detect_history_scale([
    {"x": 0, "y": 0}, {"x": 250, "y": 0}, {"x": 500, "y": 0},
]) == 0.001

print("SMOKE TEST V46 OK: historial prop/event 10.5 + filtro temporal + movimiento seguro")

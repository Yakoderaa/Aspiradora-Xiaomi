import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class FakeMap:
    def __init__(self):
        self.merged = []

    def merge_trajectory(self, points, phase=0):
        self.merged.extend((phase, dict(point)) for point in points)
        return len(points)


def main():
    from app_v34 import App

    app = object.__new__(App)
    app.mapping_active = True
    app.mapping_phase = 1
    app.mapping_transitioning = False
    app.local_map = FakeMap()
    app._v34_last_relative = None
    app._v34_motion_confirmed = False
    app._v34_position_changes = 0
    app._v34_point_id = App.LIVE_POINT_ID_BASE

    static = {"x": -1.0, "y": 0.0, "angle": 3.009508}
    check(app._record_relative_motion(static) == 0, "La primera pose sólo debe ubicar el robot")
    check(app._record_relative_motion(static) == 0, "Una pose idéntica no debe crear trayectoria")
    check(len(app.local_map.merged) == 0, "Una 10/24 fija no debe crear paredes ni puntos falsos")
    check(not app._v34_motion_confirmed, "No debe marcar movimiento con coordenadas congeladas")

    moved = {"x": -0.90, "y": 0.0, "angle": 3.0}
    check(app._record_relative_motion(moved) == 2, "El primer cambio real debe guardar inicio y nueva pose")
    check(app._v34_motion_confirmed, "Debe confirmar movimiento cuando X/Y cambian")
    check(len(app.local_map.merged) == 2, "Debe existir una trayectoria de dos muestras tras el primer movimiento")

    check(
        len(App._distinct_wall_points([{"x": -1, "y": 0}, {"x": -0.9, "y": 0}])) == 2,
        "Dos puntos distintos siguen siendo sólo dos muestras",
    )
    check(
        not App._path_has_real_motion([{"x": -1, "y": 0}, {"x": -1, "y": 0}]),
        "Dos poses iguales no son movimiento",
    )
    check(
        App._path_has_real_motion([{"x": -1, "y": 0}, {"x": -0.9, "y": 0}]),
        "Una variación real de X/Y debe detectarse",
    )

    print("SMOKE TEST V34 OK: sin paredes fantasma + movimiento real confirmado")


if __name__ == "__main__":
    main()

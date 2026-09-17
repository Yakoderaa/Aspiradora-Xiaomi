import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_robot_uses_charging_base_as_origin():
    from app_v32 import App

    app = object.__new__(App)
    app._coord_origins = {}
    app._coord_prev_local = {}
    app._coord_last_change = {}
    app._charging_confirmed = False

    state = {
        "robot": {"x": 59.0, "y": 60.0, "angle": 3.009508},
        "charging_base": {"x": 60.0, "y": 60.0, "angle": 0.0},
        "path": [],
    }

    candidates = app._coordinate_candidates(state)
    pose, origin = candidates["robot"]
    check(origin[:2] == (60.0, 60.0), "10/22 debe ser el origen de 10/24")

    local = app._localize_candidate("robot", pose, origin)
    check(local is not None, "Debe poder localizar robot-location contra la base")
    check(abs(local[0] + 1.0) < 1e-9, "59-60 debe dar X=-1, no X=0")
    check(abs(local[1]) < 1e-9, "60-60 debe dar Y=0")


def test_diagnostic_button_matches_update_button_style():
    from app_v32 import App

    source = inspect.getsource(App._install_global_diagnostics_access)
    check('"Diagnóstico"' in source, "El botón debe llamarse Diagnóstico")
    check("self._button(" in source, "Debe usar el mismo constructor visual que Buscar actualizaciones")
    check("compact=True" in source, "Debe usar el mismo tamaño compacto")
    check("DIAGNÓSTICO MIoT" not in source, "No debe conservar el texto anterior")


def main():
    test_robot_uses_charging_base_as_origin()
    test_diagnostic_button_matches_update_button_style()
    print("SMOKE TEST V32 OK: base como origen + botón Diagnóstico unificado")


if __name__ == "__main__":
    main()

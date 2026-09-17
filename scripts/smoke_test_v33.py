import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    from app_v33 import App
    from xiaomi_e10_probe import XiaomiE10Probe

    state = {
        "robot": {"x": 59.0, "y": 60.0, "angle": 3.009508},
        "charging_base": {"x": 60.0, "y": 60.0, "angle": 0.0},
    }
    relative = App._relative_robot_from_state(state)
    check(relative is not None, "Debe obtener coordenada relativa")
    check(relative["x"] == -1.0 and relative["y"] == 0.0, "Debe usar 10/24 - 10/22")
    check(5 in XiaomiE10Probe.MAP_READABLE_PIIDS and 24 in XiaomiE10Probe.MAP_READABLE_PIIDS, "La sonda debe incluir 10/5 y 10/24")
    print("SMOKE TEST V33 OK: delta directo al plano + sonda MIoT")


if __name__ == "__main__":
    main()

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
    from app_v36 import App

    relative_mm = App._cloud_relative((1250.0, 500.0), (250.0, 500.0))
    check(relative_mm is not None, "Debe calcular posición cloud relativa")
    check(abs(relative_mm["x"] - 1.0) < 1e-9, "Debe convertir mm a metros")
    check(abs(relative_mm["y"]) < 1e-9, "Y relativo debe quedar en cero")

    relative_m = App._cloud_relative((1.25, 0.5), (0.25, 0.5))
    check(abs(relative_m["x"] - 1.0) < 1e-9, "Debe conservar coordenadas ya expresadas en metros")

    app = object.__new__(App)
    app.settings = {"cloud_session": "{}", "device_did": "123"}
    check(app._cloud_session_ready(), "Debe detectar sesión cloud configurada")

    print("SMOKE TEST V36 OK: fallback Xiaomi Cloud listo")


if __name__ == "__main__":
    main()

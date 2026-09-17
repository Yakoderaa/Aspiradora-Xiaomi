import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    import app_v24
    import app_v25

    check(issubclass(app_v25.App, app_v24.App), "v25 debe conservar selector de dispositivos y UI v24")
    check("_draw_e10_visual" in app_v25.App.__dict__, "v25 no reemplazó la ilustración por foto del E10")
    check("_render_status" in app_v25.App.__dict__, "v25 no controla la visibilidad de la fila Error")
    check(2103 in app_v25.App.NON_ERROR_STATE_CODES, "2103 debe tratarse como estado de carga, no como fallo")

    dummy = object.__new__(app_v25.App)
    check(not dummy._is_real_fault(SimpleNamespace(fault=0)), "fault=0 no debe mostrarse")
    check(not dummy._is_real_fault(SimpleNamespace(fault=2103)), "2103 no debe mostrarse como error")
    check(not dummy._is_real_fault(SimpleNamespace(fault=2105)), "2105 no debe mostrarse como error")
    check(dummy._is_real_fault(SimpleNamespace(fault=514)), "un fallo real debe seguir siendo visible")

    image_path = ROOT / "assets" / "xiaomi_robot_vacuum_e10.jpg"
    check(image_path.exists(), "La foto oficial del Xiaomi Robot Vacuum E10 no está en assets")
    with Image.open(image_path) as image:
        check(image.width >= 300 and image.height >= 200, "La foto oficial del E10 es demasiado pequeña")

    print("SMOKE TEST V25 OK: foto oficial E10 incluida y Error oculto cuando no hay fallo real")


if __name__ == "__main__":
    main()

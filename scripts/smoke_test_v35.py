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
    import app_v34
    from app_v35 import App

    class MapStore:
        def __init__(self):
            self.robot = None
            self.base = None

        def set_robot(self, value):
            self.robot = dict(value) if isinstance(value, dict) else value

        def set_charging_base(self, value):
            self.base = dict(value) if isinstance(value, dict) else value

    class Label:
        def __init__(self):
            self.text = ""

        def configure(self, **kwargs):
            self.text = str(kwargs.get("text", self.text))

    app = object.__new__(App)
    app.local_map = MapStore()
    app.mapping_active = True
    app._v34_motion_confirmed = False
    app._v35_raw_relative = None
    app.map_status_label = Label()
    app._render_maps = lambda: None

    original_apply = app_v34.App._apply_map_state
    app_v34.App._apply_map_state = lambda self, state: None
    try:
        App._apply_map_state(app, {
            "robot": {"x": 59.0, "y": 60.0, "angle": 3.009508},
            "charging_base": {"x": 60.0, "y": 60.0, "angle": 0.0},
        })
    finally:
        app_v34.App._apply_map_state = original_apply

    check(app._v35_raw_relative is not None, "Debe conservar el delta MIoT crudo para diagnóstico")
    check(app._v35_raw_relative["x"] == -1.0, "El delta crudo debe seguir siendo -1")
    check(app.local_map.base["x"] == 0.0 and app.local_map.base["y"] == 0.0, "La base visual debe quedar en 0,0")
    check(app.local_map.robot["x"] == 0.0 and app.local_map.robot["y"] == 0.0, "Sin movimiento confirmado, el robot debe quedar sobre la base")
    check("delta MIoT crudo X -1.000" in app.map_status_label.text, "La UI debe distinguir delta crudo de posición visual")

    print("SMOKE TEST V35 OK: delta fijo no desplaza robot + base visual única")


if __name__ == "__main__":
    main()

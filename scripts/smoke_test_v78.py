import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v78

source = (SRC / "app_v78.py").read_text(encoding="utf-8")
ast.parse(source)
assert issubclass(app_v78.App, app_v78.app_v77.App)


class FakeSentinelCharging:
    def _get_many(self, _defs):
        return {"charging_base": "255_255", "status": 4}

    @staticmethod
    def parse_position(value):
        if value == "255_255":
            return {"x": 255.0, "y": 255.0, "angle": 0.0}
        return None


class FakeRealBase:
    def _get_many(self, _defs):
        return {"charging_base": "60_60", "status": 4}

    @staticmethod
    def parse_position(value):
        if value == "60_60":
            return {"x": 60.0, "y": 60.0, "angle": 0.0}
        return None


class FakeSentinelNotCharging:
    def _get_many(self, _defs):
        return {"charging_base": "255_255", "status": 1}

    @staticmethod
    def parse_position(value):
        return {"x": 255.0, "y": 255.0, "angle": 0.0}


def blank_app():
    app = app_v78.App.__new__(app_v78.App)
    app.BASE_CAPTURE_SAMPLES = 4
    app.BASE_CAPTURE_INTERVAL = 0
    app.BASE_MIN_VALID_SAMPLES = 3
    app.CHARGING_CONFIRM_SAMPLES = 3
    app.BASE_STABILITY_RAW = 1.0
    app._v77_base_capture_valid = 0
    app._v77_base_capture_status = None
    app._v77_base_capture_spread = None
    app._v78_base_method = None
    app._v78_charging_samples = 0
    app._v78_sentinel_samples = 0
    return app


app = blank_app()
base = app._v77_capture_base_reference(FakeSentinelCharging())
assert base == (60.0, 60.0)
assert app._v78_base_method == "fallback dock B112 60_60"
assert app._v78_charging_samples == 4
assert app._v78_sentinel_samples == 4

app = blank_app()
base = app._v77_capture_base_reference(FakeRealBase())
assert base == (60.0, 60.0)
assert app._v78_base_method == "10/22 real"
assert app._v77_base_capture_valid == 4

app = blank_app()
try:
    app._v77_capture_base_reference(FakeSentinelNotCharging())
except RuntimeError:
    pass
else:
    raise AssertionError("El fallback 60_60 no debe habilitarse sin status=4")

for required in (
    "B112_DOCK_FALLBACK_RAW = (60.0, 60.0)",
    "charging_samples >= self.CHARGING_CONFIRM_SAMPLES",
    "fallback dock B112 60_60",
    "el fallback 60_60 nunca se usa si el robot no confirma",
):
    assert required in source, required

print("SMOKE TEST V78 OK: 10/22 real preferido + fallback dock B112 solo con carga confirmada")

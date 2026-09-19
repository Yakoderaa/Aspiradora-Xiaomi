import ast
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v100
from xiaomi_e10_map_v100 import XiaomiE10MapV100

for path in (
    SRC / "app_v100.py",
    SRC / "main_v100.py",
    SRC / "update_helper.py",
    SRC / "xiaomi_e10_map_v100.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v100.App, app_v100.app_v99.App)
assert app_v100.App.MAP_BG == "#dfe9f2"
assert app_v100.App.CLOUD_FILE_POLL_SECONDS == 6.0
assert app_v100.App.LIVE_MIN_NONZERO <= 8
assert app_v100.App.CLOUD_WORKER_STALL_SECONDS <= 18.0
assert issubclass(XiaomiE10MapV100, XiaomiE10MapV100.__mro__[1])

# Simula el tipo de frame que V92 ya observó: conectado y coherente, pero
# todavía por debajo del gate de "mapa completo" de V57.
side = 120
cells = [0] * (side * side)
for x in range(56, 64):
    for y in range(59, 61):
        cells[y * side + x] = 1

class Client:
    last_v92_diagnostics = {
        "selected": {"base_distance": 0.0}
    }

    @staticmethod
    def _grid_metrics(values):
        nonzero = sum(1 for value in values if int(value))
        return {
            "valid": False,
            "nonzero": nonzero,
            "components": 1,
            "largest": nonzero,
            "largest_ratio": 1.0,
            "adjacency_ratio": 1.5,
        }

dummy = app_v100.App.__new__(app_v100.App)
dummy._v40_client = Client()
dummy._v100_live_rejects = 0
dummy._v100_live_accepts = 0
dummy._v100_last_live_metrics = {}
dummy._v100_last_live_reason = "—"
snapshot = SimpleNamespace(
    grid_cells=cells,
    grid_side=side,
    grid_resolution=0.2,
    grid_base_cell=(60.0, 60.0),
    grid_blob_sha12="abc",
    upload_date=1,
)
grid = app_v100.App._v100_live_grid_from_snapshot(dummy, snapshot)
assert grid is not None
assert grid["preview"] is True
assert grid["source"] == "xiaomi-live-partial"
assert dummy._v100_live_accepts == 1

source = (SRC / "app_v100.py").read_text(encoding="utf-8")
client_source = (SRC / "xiaomi_e10_map_v100.py").read_text(encoding="utf-8")
assert "def load_live_partial" in client_source
assert 'self._download_slot("0")' in client_source
assert "def request_live_upload" in client_source
assert "_run_v60_cycle" not in client_source
assert "AspiradoraXiaomiLiveGrid" in source
assert "client.load_live_partial()" in source
for required in (
    "XIAOMI LIVE PARCIAL",
    "el tema nunca modifica el fondo de los canvases de mapa",
    "CLOUD_FILE_POLL_SECONDS = 6.0",
    "LIVE_MIN_NONZERO = 8",
    "self._v100_force_canvas_bg(canvas, thumbnail=True)",
):
    assert required in source, required

helper = (SRC / "update_helper.py").read_text(encoding="utf-8")
assert '"install_detail": "La instalación está en proceso"' in helper
assert "La instalación se ejecuta en segundo plano, sin CMD ni ventanas externas." not in helper

print(
    "SMOKE TEST V100 OK: Xiaomi partial live grid + fixed blue canvases + "
    "6s cloud cadence + simplified installer text"
)

import ast
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v88
from local_mapping import LocalMapStore

for path in (
    SRC / "app_v88.py",
    SRC / "main_v88.py",
    SRC / "local_mapping.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v88.App, app_v88.app_v87.App)
assert app_v88.App.MAP_CELL == 0.10

# El sentinela del B112 nunca debe mandar la base fuera del mapa.
base, fallback = app_v88.App._v88_correct_base_cell((255.0, 255.0), 120)
assert fallback is True
assert base == (60.0, 60.0)

base, fallback = app_v88.App._v88_correct_base_cell((59.5, 61.0), 120)
assert fallback is False
assert base == (59.5, 61.0)

# Planta rectangular de 1 x 2 m alrededor del dock. El renderer debe usar
# los límites nativos, no los límites del recorrido.
cells = [0] * (120 * 120)
for gy in range(50, 70):
    for gx in range(55, 65):
        cells[gy * 120 + gx] = 1

grid = {
    "side": 120,
    "resolution": 0.1,
    "base_cell": (60.0, 60.0),
    "cells": cells,
    "source": "smoke",
}
bounds = app_v88.App._v88_grid_bounds(grid)
assert bounds == (-0.5, -1.0, 0.5, 1.0), bounds

# La geometría nativa debe quedar guardada por mapa y sobrevivir una recarga.
with tempfile.TemporaryDirectory() as tmp:
    store = LocalMapStore(Path(tmp))
    store.set_native_grid({
        "side": 4,
        "resolution": 0.1,
        "base_cell": [2.0, 2.0],
        "cells": [
            0, 0, 0, 0,
            0, 1, 1, 0,
            0, 1, 1, 0,
            0, 0, 0, 0,
        ],
        "source": "smoke",
        "blob_sha12": "abc123",
        "timestamp": 123,
        "metrics": {"valid": True},
    })
    first = store.snapshot()["native_grid"]
    assert first["base_cell"] == [2.0, 2.0]
    assert first["blob_sha12"] == "abc123"

    reopened = LocalMapStore(Path(tmp))
    second = reopened.snapshot()["native_grid"]
    assert second == first

source = (SRC / "app_v88.py").read_text(encoding="utf-8")
for required in (
    "DIAGNÓSTICO V88 ACTIVO",
    "grid Xiaomi validado",
    "Mapa Xiaomi",
    "Recorrido",
    "255_255",
    "set_native_grid",
    "doble clic rueda=Zoom Extents",
    "V85/V86 conservan trayectoria física",
):
    assert required in source, required

print(
    "SMOKE TEST V88 OK: grid Xiaomi persistente, base 255_255 corregida, "
    "bounds nativos y fallback V87 conservado"
)

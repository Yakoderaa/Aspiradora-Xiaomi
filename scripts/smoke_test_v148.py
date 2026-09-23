from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v148.py")
assert "class App(app_v147.App)" in app
assert "v148_persistent_strip" in app
assert "def _v148_escape_geometry" in app
assert "rebase_stable" in app
assert "ESCAPE_SUCCESS_VOTES = 3" in app

import app_v148

probe = object.__new__(app_v148.App)
probe._v148_persistent_strip_hits = 0

# Caso V147 real: corredor angosto que sigue avanzando de extremo pero
# acumula muchas inversiones. No debe volver a verse como expansión sana.
pts = []
for cycle in range(10):
    base = cycle * 0.42
    for i in range(19):
        pts.append((base + i * 0.10, 0.04 * (cycle % 2)))
    for i in range(8):
        pts.append((base + 1.8 - i * 0.10, 0.04 * ((cycle + 1) % 2)))

m = probe._v142_classify_path(pts[-220:])
assert m["v148_2d_ratio"] <= 0.20, m
assert m["v148_persistent_strip"] is True, m
assert m["oscillation_evidence"] is True, m
assert m["pattern"] == "oscillation_corridor", m

# Validación del segundo escape observado: crecimiento enorme en X, cero
# crecimiento transversal y ventana reciente 3.7 x 0.2. Debe fallar.
probe._v148_escape_pre_bbox = (2.6, 4.6, -0.6, 0.7)
probe._v148_escape_axis = "x"
probe._v148_escape_rebases = 1
probe._v85_rebases = 1
bad = {
    "bbox": (2.6, 13.2, -0.6, 0.7),
    "span_x": 10.6,
    "span_y": 1.3,
    "recent_span_x": 3.7,
    "recent_span_y": 0.2,
    "oscillation_evidence": False,
    "v148_persistent_strip": False,
}
bad_result = probe._v148_escape_geometry(bad)
assert bad_result["candidate"] is False, bad_result
assert bad_result["cross_growth_m"] == 0.0, bad_result

# Escape real: crece fuera del corredor y la ventana reciente también
# adquiere dos dimensiones.
good = {
    "bbox": (2.2, 6.0, -1.3, 1.6),
    "span_x": 3.8,
    "span_y": 2.9,
    "recent_span_x": 1.5,
    "recent_span_y": 0.8,
    "oscillation_evidence": False,
    "v148_persistent_strip": False,
}
good_result = probe._v148_escape_geometry(good)
assert good_result["candidate"] is True, good_result

# El mismo crecimiento queda invalidado si V85 cambió de marco.
probe._v85_rebases = 2
rebase_result = probe._v148_escape_geometry(good)
assert rebase_result["candidate"] is False, rebase_result
assert rebase_result["rebase_stable"] is False, rebase_result

print("V148-IA smoke OK")

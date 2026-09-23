from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v147.py")
main = text("src/main_v147.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v146.App)" in app
assert "oscillation_corridor" in app
assert "def _v147_corridor_geometry" in app
assert "def _v147_schedule_escape" in app
assert "ESCAPE_MAX_CONSECUTIVE = 3" in app
assert "misma sesión" in app.lower()
assert "import app_v147" in main
assert "app_v147.App().mainloop()" in main
assert 'scripts\\smoke_test_v147.py' in build
assert 'src\\main_v147.py' in build
assert "V147-IA" in workflow

import app_v147

probe = object.__new__(app_v147.App)

# Regresión real V146: mucha distancia acumulada, múltiples inversiones,
# corredor estrecho y desplazamiento neto pequeño. Debe ser oscilación.
osc = []
for cycle in range(8):
    forward = [(i * 0.1, (cycle % 2) * 0.05) for i in range(10)]
    backward = [(0.9 - i * 0.1, ((cycle + 1) % 2) * 0.05) for i in range(10)]
    osc.extend(forward + backward)
m = probe._v142_classify_path(osc)
assert m["pattern"] == "oscillation_corridor", m
assert m["oscillation_evidence"] is True, m
assert m["oscillation_reversals"] >= 5, m
assert m["straightness"] <= 0.14, m

# Pasillo real con avance sostenido: estrecho, pero sin inversiones repetidas.
progress = [(i * 0.08, (i % 3) * 0.03) for i in range(60)]
p = probe._v142_classify_path(progress)
assert p["pattern"] != "oscillation_corridor", p
assert p["oscillation_evidence"] is False, p

# Caso que V144 cortó de más: avance fuerte sobre un eje debe seguir siendo progreso.
old_false_positive = [(i * 0.07, 0.04 * ((i // 8) % 2)) for i in range(45)]
q = probe._v142_classify_path(old_false_positive)
assert q["pattern"] != "oscillation_corridor", q

print("V147-IA smoke OK")

# Trigger final V147 tras actualizar workflow/release.

# Trigger final V147 CI compat.

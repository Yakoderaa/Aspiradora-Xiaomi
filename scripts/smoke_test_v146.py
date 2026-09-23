from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def text(path):
    return (ROOT / path).read_text(encoding="utf-8")

app = text("src/app_v146.py")
main = text("src/main_v146.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v145.App)" in app
assert "def _v142_classify_path" in app
assert "def _v146_apply_progress_evidence" in app
assert "def _v146_bad_evidence" in app
assert "def _v142_mapping_monitor" in app
assert "def _v143_phase1_is_valid" in app
assert "recent_new_cells" in app
assert "net_displacement_m" in app
assert "corridor_progress" in app
assert "bad_votes_8" in app
assert "AI_LOOP_NO_PROGRESS_SECONDS" in app
assert "revisitar celdas por sí solo jamás dispara auto-abort" in app
assert "import app_v146" in main
assert "app_v146.App().mainloop()" in main
assert 'scripts\\smoke_test_v146.py' in build
assert "main_current.py" in build
assert "release_meta.json" in workflow
assert "$meta.notes" in workflow

import app_v146

probe = object.__new__(app_v146.App)
corridor = []
xs = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 2.0, 1.5, 1.0, 0.5]
for row in range(6):
    y = (row % 3) * 0.2
    for x in xs:
        corridor.append((x, y))
metrics = probe._v142_classify_path(corridor)
assert metrics["pattern"] == "expanding", metrics
assert metrics["recent_span_m"] >= 2.0, metrics
assert metrics["directional_progress"] is True, metrics

stuck = []
for i in range(40):
    angle = (i % 8) * 0.78539816339
    stuck.append((0.12 * math.cos(angle), 0.12 * math.sin(angle)))
stuck_metrics = probe._v142_classify_path(stuck)
assert stuck_metrics["pattern"] == "stuck", stuck_metrics

print("V146-IA smoke OK")


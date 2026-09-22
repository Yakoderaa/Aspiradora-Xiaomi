from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v131.py")
main = text("src/main_v131.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v130.App)" in app
assert "DOCK_GUARD_STABLE_SECONDS = 5.5" in app
assert "DOCK_NEAR_STALL_SAMPLES = 5" in app
assert "DOCK_MAX_RETRIES = 3" in app
assert "DOCK_RETRY_REVERSE_SECONDS = 1.55" in app

edge = app[
    app.index("def _v131_start_edge_exploration"):
    app.index("# ====================== pose:")
]
assert 'vacuum.set_sweep_type(2)' in edge
assert '"mapping_edge_v131/start-only-sweep"' in edge
assert '"mapping_edge_v131/start-sweep-fallback"' in edge
assert "2,\n                    3," in edge
assert "2,\n                        1," in edge
assert '7, 3, ["", 2, 1]' not in edge
assert "vacuum.stop()" in app[app.index("def _v131_wait_edge_start"):app.index("def _v131_start_edge_exploration")]

pose = app[
    app.index("def _v117_update_live_pose"):
    app.index("# ====================================== feedback")
]
assert "current == self._v131_prestart_robot_key" in pose
assert '"x": 0.0' in pose
assert "primer 10/24 post-START" in pose

assert "import app_v131" in main
assert "app_v131.App().mainloop()" in main
assert 'scripts\\smoke_test_v131.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143))
assert any(v in workflow for v in ("V131", "V132", "V133", "V134", "V135", "V136", "V137", "V138", "V139", "V140", "V141", "V142-IA", "V143-IA"))

print("V131 smoke OK")

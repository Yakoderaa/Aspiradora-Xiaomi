from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v138.py")
main = text("src/main_v138.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v137.App)" in app

reset = app[
    app.index("def _v138_reset_cleaning_state"):
    app.index("def _v138_start_factory_edge")
]
assert '["", 2, 2]' in reset
assert '["", 0, 2]' in reset
assert '["", 4, 2]' in reset
assert "vacuum.stop" in reset
assert "vacuum.manual(10)" in reset
assert "set_property_by(7, 1, 0)" in reset
assert "set_property_by(8, 10, 0)" in reset
assert "vacuum.set_mode(0)" in reset
assert "vacuum.set_sweep_type(0)" in reset

edge = app[
    app.index("def _v138_start_factory_edge"):
    app.index("def _v138_progress_worker")
]
assert "vacuum.set_sweep_type(2)" in edge
assert '"mapping_edge_v138/factory"' in edge
assert "\n                2,\n                3," in edge
assert '["", 2, 1]' not in edge

start = app[
    app.index("def start_new_mapping"):
    app.index("def _v138_retry_factory_edge")
]
assert "vacuum.arm_new_map(1)" in start
assert "_v138_reset_cleaning_state" in start
assert "_v138_start_factory_edge" in start
assert "start_mapping_exploration" not in start

phase2 = app[
    app.index("def _v121_request_phase2"):
    app.index("def _v127_try_phase2_recovery")
]
assert "escaped_room" in phase2
assert "_v138_retry_factory_edge" in phase2
assert "vacuum.start_mapping_whole_home(" in phase2
assert "vacuum.arm_new_map(" not in phase2

assert "app_v128.App._v127_try_phase2_recovery" in app
assert "manual_with_exit" in app
assert "original_manual(10)" in app
assert "proceso finalizó" in app

assert "import app_v138" in main
assert "app_v138.App().mainloop()" in main
assert 'scripts\\smoke_test_v138.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (138, 139, 140))
assert any(v in workflow for v in ("V138", "V139", "V140"))

print("V138 smoke OK")

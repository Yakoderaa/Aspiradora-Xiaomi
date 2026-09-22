from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v135.py")
main = text("src/main_v135.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v134.App)" in app
start = app[
    app.index("def start_new_mapping"):
    app.index("def _v121_request_phase2")
]
assert "vacuum.arm_new_map(" not in start
assert 'vacuum.set_mode(0)' in start
assert 'vacuum.set_sweep_type(2)' in start
assert '"mapping_edge_v135/native-v87"' in start
assert "2,\n                    3," in start
assert "7, 3" not in start
assert "2,\n                    1," not in start
phase2 = app[
    app.index("def _v121_request_phase2"):
    app.index("def _handle_ui_event")
]
assert "start_mapping_whole_home" not in phase2
assert "mapping_active = False" in phase2
assert "no inicia Paso 2 automáticamente" in phase2
assert "import app_v135" in main
assert "app_v135.App().mainloop()" in main
assert 'scripts\\smoke_test_v135.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (135, 136, 137, 138))
assert any(v in workflow for v in ("V135", "V136", "V137", "V138"))

print("V135 smoke OK")

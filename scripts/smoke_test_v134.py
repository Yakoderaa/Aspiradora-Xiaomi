from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v134.py")
main = text("src/main_v134.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v133.App)" in app
method = app[
    app.index("def _v131_start_edge_exploration"):
    app.index("def _handle_ui_event")
]
assert "vacuum.device.call_action_by(7, 3, [\"\", 2, 1])" in method
assert "vacuum.set_sweep_type(2)" in method
assert "vacuum.device.set_property_by(7, 1, 0)" in method
assert "_send_motor_start" not in method
assert "2, 1," not in method
assert "2, 3," not in method
assert "No se lanzó ningún START alternativo" in method
assert "import app_v134" in main
assert "app_v134.App().mainloop()" in main
assert 'scripts\\smoke_test_v134.py' in build
assert "main_current.py" in build
assert "release_meta.json" in workflow

print("V134 smoke OK")

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v133.py")
main = text("src/main_v133.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v132.App)" in app
assert "DOCK_MAX_RETRIES = 4" in app
assert "DOCK_RETRY_REVERSE_PROFILE = (1.55, 2.05, 2.45, 2.80)" in app
assert "DOCK_RETRY_TURN_PROFILE = (0.00, 0.18, 0.18, 0.28)" in app
worker = app[
    app.index("def _v73_dock_guard_worker"):
    app.index("def _handle_ui_event")
]
assert "vacuum.manual(4)" in worker
assert "vacuum.manual(turn)" in worker
assert "vacuum.dock()" in worker
assert '"v73_dock_guard_failed"' in worker
assert "vacuum.stop()" in worker
assert "conserva íntegramente la prueba EDGE 2/1 de V132" in app
assert "import app_v133" in main
assert "app_v133.App().mainloop()" in main
assert 'scripts\\smoke_test_v133.py' in build
assert 'src\\main_v133.py' in build
assert "V133" in workflow

print("V133 smoke OK")

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v136.py")
main = text("src/main_v136.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v135.App)" in app

start = app[
    app.index("def start_new_mapping"):
    app.index("def dock")
]
assert "vacuum.start_mapping_perimeter()" in start
assert "start_mapping_exploration" not in start
assert "_send_motor_start" not in start
assert "start_mapping_whole_home" not in start

events = app[
    app.index("def _handle_ui_event"):
    app.index("def _diagnostic_text")
]
assert "self._watch_edge_only" in events
assert "self._v67_arm_transition(kind)" in events
assert '"auto_step2_started"' in events
assert "No se inicia el Paso 2" in events

dock = app[
    app.index("def dock"):
    app.index("def _v67_commit_step2_start")
]
assert "_v136_manual_abort = True" in dock

diag = app[app.index("def _diagnostic_text"):]
assert "XiaomiE10Edge.start_mapping_perimeter() exacto de V64" in diag
assert "_watch_edge_only() exacto de V68" in diag
assert "_v67_arm_transition() -> base confirmada -> start_mapping_interior()" in diag
assert "NO usa start_mapping_whole_home V123" in diag

assert "import app_v136" in main
assert "app_v136.App().mainloop()" in main
assert 'scripts\\smoke_test_v136.py' in build
assert 'src\\main_v136.py' in build
assert "V136" in workflow

print("V136 smoke OK")

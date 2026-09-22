from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v137.py")
main = text("src/main_v137.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v136.App)" in app

start = app[
    app.index("def start_new_mapping"):
    app.index("def dock")
]
assert "vacuum.arm_new_map(1)" in start
assert "vacuum.start_mapping_exploration(" in start
assert "_watch_edge_only" not in start
assert "start_mapping_interior" not in start

phase2 = app[
    app.index("def _v121_request_phase2"):
    app.index("def _handle_ui_event")
]
assert "vacuum.start_mapping_whole_home(" in phase2
assert "start_mapping_interior" in phase2  # sólo comentario explicando que NO se usa
assert "vacuum.start_mapping_interior(" not in phase2
assert "_v137_manual_cancel" in phase2
assert "arm_new_map(" not in phase2

diag = app[app.index("def _diagnostic_text"):]
assert "movimiento físico V123 restaurado" in diag
assert "NO usa start_mapping_interior() para Paso2" in diag
assert "NO usa watcher EDGE V68" in diag

assert "import app_v137" in main
assert "app_v137.App().mainloop()" in main
assert 'scripts\\smoke_test_v137.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (137, 138, 139, 140, 141, 142, 143, 144))
assert any(v in workflow for v in ("V137", "V138", "V139", "V140", "V141", "V142", "V142", "V142-IA", "V143-IA"))

print("V137 smoke OK")

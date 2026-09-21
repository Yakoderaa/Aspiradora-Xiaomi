from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v129.py")
main = text("src/main_v129.py")
build = text("build.ps1")

assert "class App(app_v128.App)" in app
assert "strategy" in app and "PASSIVE ONLY" in app
assert "commands_sent" in app
assert "v129_phase2_stuck_detected" in app
assert "v129_phase2_idle" in app
assert "import app_v129" in main
assert "app_v129.App().mainloop()" in main
assert "scripts\\smoke_test_v129.py" in build
assert any(f"src\\main_v{v}.py" in build for v in (129, 130, 131, 132))

method = app[
    app.index("def _v127_try_phase2_recovery"):
    app.index("def _render_status")
]
for forbidden in (
    ".stop(",
    ".manual(",
    "_send_motor_start(",
    "start_mapping_whole_home(",
    ".dock(",
):
    assert forbidden not in method, forbidden

print("V129 smoke OK")

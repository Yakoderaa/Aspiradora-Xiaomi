from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v128.py")
map_client = text("src/xiaomi_e10_map_v128.py")
main = text("src/main_v128.py")
build = text("build.ps1")

assert "class App(app_v127.App)" in app
assert "class XiaomiE10MapV128(XiaomiE10MapV127)" in map_client
assert "v128_phase2_reassert" in app
assert "v128_phase2_idle_retry" in app
assert "allow_when_guarded=True" in app
assert "POLISH_MAX_GROWTH_RATIO = 1.12" in map_client
assert "orthogonal >= 3 or around >= 6" in map_client
assert "import app_v128" in main
assert "app_v128.App().mainloop()" in main
assert "scripts\\smoke_test_v128.py" in build
assert any(f"src\\main_v{v}.py" in build for v in (128, 129, 130, 131, 132, 133))

method = app[
    app.index("def _v127_try_phase2_recovery"):
    app.index("def _handle_ui_event")
]
assert "vacuum.stop(" not in method
assert "vacuum.manual(" not in method
assert "start_mapping_whole_home(" not in method
assert '"v128_phase2_reassert"' in method
assert '"v128_phase2_idle_retry"' in method

print("V128 smoke OK")

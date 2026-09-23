from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


engine = text("src/adaptive_navigation.py")
app = text("src/app_v143.py")
main = text("src/main_v143.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "VERSION = 2" in engine
assert "v142_mapping_noise_cleared" in engine
assert "record_mapping_session" in engine
assert "session_key" in engine
assert "missing session_key" in engine

assert "class App(app_v142.App)" in app
assert "def _v143_phase1_is_valid" in app
assert "status=4 por sí solo NO habilita Paso2" in app
assert "spiral_or_loop" in app
assert "stuck" in app
assert "AI_BAD_PATTERN_STREAK = 3" in app
assert "self._v143_manual_return_requested = True" in app
assert "phase1_rejected" in app
assert "app_v141.App._handle_ui_event" in app
assert "record_mapping_session" in app

assert "import app_v143" in main
assert "app_v143.App().mainloop()" in main
assert 'scripts\\smoke_test_v143.py' in build
assert "main_current.py" in build
assert "release_meta.json" in workflow
assert "APP_DISPLAY_VERSION" in workflow
assert "-IA" in workflow

print("V143-IA smoke OK")

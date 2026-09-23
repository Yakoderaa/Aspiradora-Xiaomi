from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


engine = text("src/adaptive_navigation.py")
app = text("src/app_v142.py")
main = text("src/main_v142.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class AdaptiveNavigationMemory" in engine
assert "ai_navigation_memory.json" in engine
assert "record_room_attempt" in engine
assert "should_retry_room" in engine
assert "consecutive_worse" in engine
assert "record_mapping_pattern" in engine

assert "class App(app_v141.App)" in app
assert "Navegación inteligente (IA)" in app
assert "Borrar aprendizaje de IA" in app
assert "def clean_local_room" in app
assert "_v142_finish_room_pass" in app
assert "verified_double" in app
assert "verified_triple" in app
assert "spiral_or_loop" in app
assert "stuck" in app
assert "no toma el control de ruedas" in app
assert "backup-v141-pre-ia" in app

assert "import app_v142" in main
assert "app_v142.App().mainloop()" in main
assert 'scripts\\smoke_test_v142.py' in build
assert "main_current.py" in build

assert 'APP_DISPLAY_VERSION' in workflow
assert '-IA' in workflow
assert "release_meta.json" in workflow

print("V142-IA smoke OK")

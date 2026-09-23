from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v144.py")
main = text("src/main_v144.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v143.App)" in app
assert "AI_AUTO_ABORT_MIN_SECONDS = 45.0" in app
assert "AI_AUTO_ABORT_MIN_PATH_M = 5.0" in app
assert '"v144_ai_auto_abort"' in app
assert "def _v144_execute_auto_abort" in app
assert "phase1-auto-abort-ai" in app
assert "ai_auto_abort_phase1" in app
assert "app_v141.App.dock(self)" in app
assert "regreso automático IA" in app
assert "proceso finalizó" in app
assert "self.mapping_active = False" in app
assert "self.mapping_phase = 0" in app
assert "self._v143_commit_mapping_session" in app

assert "import app_v144" in main
assert "app_v144.App().mainloop()" in main
assert 'scripts\\smoke_test_v144.py' in build
assert "main_current.py" in build
assert "release_meta.json" in workflow
assert "APP_DISPLAY_VERSION" in workflow
assert "-IA" in workflow

print("V144-IA smoke OK")

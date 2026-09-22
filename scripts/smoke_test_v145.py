from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v145.py")
main = text("src/main_v145.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")
v137 = text("src/app_v137.py")

assert "class App(app_v144.App)" in app
assert "def _v145_latch_session" in app
assert "def _v138_start_factory_edge" in app
assert "V145 BLOCKED EDGE" in app
assert "def _v121_request_phase2" in app
assert "def _v138_wait_for_dock" in app
assert "vacuum.status()" in app
assert "vacuum.stop()" in app
assert "vacuum.dock()" in app
assert "def _v140_reset_worker" in app
assert "def _v140_confirm_reset" in app
assert "v74_mapping_started" in app
assert "v121_phase2_started" in app
assert "late-event:" in app
assert "sólo Mapear vivienda explícito" in app
assert "serial != int(getattr(self, \"_v74_mapping_serial\", -1))" in v137
assert "_v145_session_latched" in v137

assert "import app_v145" in main
assert "app_v145.App().mainloop()" in main
assert 'scripts\\smoke_test_v145.py' in build
assert 'src\\main_v145.py' in build
assert "V145-IA" in workflow
assert "APP_DISPLAY_VERSION" in workflow
assert "-IA" in workflow

print("V145-IA smoke OK")

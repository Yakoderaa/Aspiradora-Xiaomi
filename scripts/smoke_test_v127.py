from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v127.py")
map_client = text("src/xiaomi_e10_map_v127.py")
main = text("src/main_v127.py")
build = text("build.ps1")

assert "class App(app_v126.App)" in app
assert "class XiaomiE10MapV127(XiaomiE10MapV126)" in map_client
assert "ASSISTED_RETURN_WINDOW_SECONDS = 18.0" in app
assert "PHASE2_RECOVERY_NO_NEW_SECONDS = 100.0" in app
assert "start_mapping_whole_home(" in app
assert "build-map" in app
assert "arm_new_map" in app
assert "v127_final_grid_preview" in app
assert "_v127_publish_preview_grid" in app
assert "SURFACE_CLOSE_RADIUS = 2" in map_client
assert "SURFACE_MAX_GROWTH_RATIO = 2.80" in map_client
assert "_v127_dilate" in map_client
assert "_v127_erode" in map_client
assert "import app_v127" in main
assert "app_v127.App().mainloop()" in main
assert "scripts\\smoke_test_v127.py" in build
assert any(f"src\\main_v{v}.py" in build for v in (127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144))

# V127 no debe crear un mapa nuevo durante recovery de Fase 2.
phase2 = app[app.index("def _v127_try_phase2_recovery"):]
phase2 = phase2[:phase2.index("def _v73_schedule_recovery")]
assert "start_new_mapping" not in phase2
assert "arm_new_map(" not in phase2
assert "build_map" not in phase2

print("V127 smoke OK")

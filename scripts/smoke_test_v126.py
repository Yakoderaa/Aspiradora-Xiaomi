from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v126.py")
map_client = text("src/xiaomi_e10_map_v126.py")
main = text("src/main_v126.py")
requirements = text("requirements.txt").lower()
build = text("build.ps1").lower()

assert "class App(app_v123.App)" in app
assert "app_v107.App._v107_choose_final_grid" in app
assert "_grid_metrics(cells)" in app
assert "RETURN_MAX_INTERVENTIONS = 2" in app
assert "vacuum.dock()" in app
assert "vacuum.manual(1)" in app
assert "class XiaomiE10MapV126(XiaomiE10MapV111)" in map_client
assert "XiaomiE10MapV107._snapshot_from_grid" in map_client
assert "set_v110_target_area(None)" in map_client
assert "import app_v126" in main
assert "app_v126.App().mainloop()" in main

for obsolete in (
    "src/app_v124.py",
    "src/app_v125.py",
    "src/main_v124.py",
    "src/main_v125.py",
    "src/chatgpt_bridge.py",
    "scripts/smoke_test_v124.py",
    "scripts/smoke_test_v125.py",
):
    assert not (ROOT / obsolete).exists(), obsolete

assert "mcp[" not in requirements
assert "--collect-all mcp" not in build
assert "--collect-all starlette" not in build
assert "--collect-all uvicorn" not in build
assert any(f"main_v{v}.py" in build for v in (126, 127, 128, 129, 130, 131, 132, 133))
assert "smoke_test_v126.py" in build

print("V126 smoke OK")

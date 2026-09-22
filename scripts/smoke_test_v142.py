from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v142.py")
main = text("src/main_v142.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v141.App)" in app
assert "adaptive_learning.json" in app
assert "AI_ROOM_SCORE_TARGET = 0.88" in app
assert "AI_MAX_AUTO_RETRIES = 2" in app
assert '"area_first", "row_sweep", "reverse", "fine_split"' in app

room = app[
    app.index("def clean_local_room"):
    app.index("# ============================================= análisis mapa/paredes IA")
]
assert "_v142_strategy_rank" in room
assert "_v142_strategy_rects" in room
assert "_v142_score_pass" in room
assert "_v142_update_strategy_stats" in room
assert "AI_MAX_AUTO_RETRIES" in room
assert "start_zone_clean(" in room
assert "wait_for_cleaning_cycle" in room
assert "native_grid" not in room or "_v142_constrain_room" in room

assert "def _v142_analyze_native_grid" in app
assert "boundary_edges" in app
assert "estimated_wall_m" in app
assert "Borrar aprendizaje de IA" in app
assert "backup-v140-pre-ia" in app

assert "import app_v142" in main
assert "app_v142.App().mainloop()" in main
assert 'scripts\\smoke_test_v142.py' in build
assert 'src\\main_v142.py' in build
assert "V142" in workflow

print("V142 smoke OK")

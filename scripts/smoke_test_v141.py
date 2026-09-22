from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v141.py")
main = text("src/main_v141.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v140.App)" in app

edge = app[
    app.index("def _v138_start_factory_edge"):
    app.index("def _v141_watch_edge_state")
]
assert "vacuum.set_sweep_type(2)" in edge
assert '"mapping_edge_v141/vacuum-start-sweep"' in edge
assert "\n                2,\n                1," in edge
assert "7/3 set-room-clean" not in edge
assert "\n                7,\n                3," not in edge
assert "\n                2,\n                3," not in edge

mapping = app[
    app.index("def start_new_mapping"):
    app.index("def _v121_request_phase2")
]
assert "vacuum.arm_new_map(1)" in mapping
assert "_v138_reset_cleaning_state" not in mapping
assert '"reset": "NO"' in mapping
assert "EDGE Vacuum 2/1" in mapping

phase2 = app[
    app.index("def _v121_request_phase2"):
    app.index("def dock")
]
assert "app_v137.App._v121_request_phase2" in phase2
assert "escaped_room" not in phase2

clear = app[
    app.index("def _v139_confirm_clear_diagnostics"):
    app.index("# ============================================== EDGE")
]
assert "_v141_diag_events = []" in clear
assert "_v141_diag_capture = True" in clear
assert "box.delete" in clear
assert "_v139_diag_baseline = {}" in clear

orders = app[
    app.index("def _v140_parse_order_ids"):
    app.index("# ================================================ diagnóstico")
]
assert "ast.literal_eval" in orders
assert 'split(",", 1)[0]' in orders

assert "import app_v141" in main
assert "app_v141.App().mainloop()" in main
assert 'scripts\\smoke_test_v141.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (141, 142, 143))
assert any(v in workflow for v in ("V141", "V142-IA", "V143-IA"))

print("V141 smoke OK")

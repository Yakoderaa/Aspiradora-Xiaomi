from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v140.py")
main = text("src/main_v140.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v139.App)" in app

assert "Mantenimiento avanzado" in app
assert "Restablecer aspiradora (conservar Wi-Fi)" in app
assert app.count("messagebox.askyesno(") >= 2

worker = app[
    app.index("def _v140_reset_worker"):
    app.index("# ========================================================== eventos/UI")
]
assert "_v138_reset_cleaning_state" in worker
assert "_v140_delete_robot_orders" in worker
assert "set_property_by(10, 1, 0)" in worker
assert "set_property_by(7, 7, 0)" in worker
assert "_v140_reset_robot_maps" in worker
assert "replace_library" not in worker  # encapsulado en helper local
assert "wifi" not in worker.lower() or "wifi_touched" in worker

maps = app[
    app.index("def _v140_reset_robot_maps"):
    app.index("def _v140_reset_local_app_state")
]
assert '(16, "reset-map-ii", 18)' in maps
assert '(10, "reset-map", None)' in maps

local = app[
    app.index("def _v140_reset_local_app_state"):
    app.index("def _v140_reset_worker")
]
assert "self.local_map._library_defaults()" in local
assert "self.local_map.replace_library" in local
assert "self.plan_store.replace_all({})" in local

diag = app[app.index("def _diagnostic_text"):]
assert "reset profundo sin Wi-Fi" in diag
assert "NO se escriben propiedades Wi-Fi" in diag
assert "voz/idioma y contadores de consumibles: no se modifican" in diag

assert "import app_v140" in main
assert "app_v140.App().mainloop()" in main
assert 'scripts\\smoke_test_v140.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (140, 141, 142))
assert any(v in workflow for v in ("V140", "V141", "V142", "V142"))

print("V140 smoke OK")

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v139.py")
main = text("src/main_v139.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v138.App)" in app

edge = app[
    app.index("def _v138_start_factory_edge"):
    app.index("# =================================================== UI")
]
assert "vacuum.set_sweep_type(2)" in edge
assert '"mapping_edge_v139/direct-edge"' in edge
assert '["", 2, 1]' in edge
assert "\n                7,\n                3," in edge
assert "generic_start_sent" in edge
assert "start-only-sweep" not in edge
assert "\n                2,\n                3," not in edge
assert "\n                2,\n                1," not in edge

ui = app[
    app.index("def _v139_remove_top_clean_button"):
    app.index("# ================================================ diagnóstico")
]
assert "_v95_clean_button" in ui
assert "pack_forget()" in ui

diag = app[app.index("def _v139_diag_sections"):]
assert "Borrar diagnóstico" in diag
assert "messagebox.askyesno" in diag
assert "_v139_diag_baseline" in diag
assert "Sólo aparecen secciones que cambiaron" in diag
assert "no modifica el mapa ni envía comandos" in diag

assert "import app_v139" in main
assert "app_v139.App().mainloop()" in main
assert 'scripts\\smoke_test_v139.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (139, 140, 141, 142, 143, 144))
assert any(v in workflow for v in ("V139", "V140", "V141", "V142", "V142", "V142-IA", "V143-IA"))

print("V139 smoke OK")

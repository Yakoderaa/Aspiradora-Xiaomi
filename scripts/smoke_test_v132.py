from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v132.py")
main = text("src/main_v132.py")
build = text("build.ps1")
workflow = text(".github/workflows/build-release.yml")

assert "class App(app_v131.App)" in app
method = app[
    app.index("def _v131_start_edge_exploration"):
    app.index("def _diagnostic_text")
]
assert 'vacuum.set_sweep_type(2)' in method
assert '"mapping_edge_v132/start-sweep"' in method
assert "2,\n                    1," in method
assert "2,\n                    3," not in method
assert "known_bad_routes_disabled" in method
assert "No se ejecutó fallback" in method
assert "import app_v132" in main
assert "app_v132.App().mainloop()" in main
assert 'scripts\\smoke_test_v132.py' in build
assert any(f"src\\main_v{v}.py" in build for v in (132, 133, 134, 135, 136, 137, 138, 139))
assert any(v in workflow for v in ("V132", "V133", "V134", "V135", "V136", "V137", "V138", "V139"))

print("V132 smoke OK")

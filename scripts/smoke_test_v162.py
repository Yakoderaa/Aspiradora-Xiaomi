from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
targeted = (ROOT / "src" / "targeted_v157.py").read_text(encoding="utf-8")
app = (ROOT / "src" / "app_v162.py").read_text(encoding="utf-8")
main = (ROOT / "src" / "main_current.py").read_text(encoding="utf-8")
meta = (ROOT / "release_meta.json").read_text(encoding="utf-8")

fn = targeted.split("def _start_zone_locked", 1)[1].split("def _wait_cycle", 1)[0]

# Regresión V157: jamás volver a retornar después de 9/8 sin mandar 9/3.
assert "call_action_by(9, 8, [value])" in fn
assert "_set_locked(\n                9, 2" in fn
assert "call_action_by(9, 3)" in fn
assert 'route = f"{target_route}+9/3"' in fn
assert 'return "9/8", response' not in fn

# El START 9/3 debe estar fuera del except: se ejecuta para ambos targets.
except_pos = fn.index("except Exception as first:")
start_pos = fn.index("call_action_by(9, 3)")
assert start_pos > except_pos

# Error rápido, sin volver a los ~35 s del bug.
assert "start_deadline = time.monotonic() + 20.0" in targeted
assert "start_deadline = time.monotonic() + 35.0" not in targeted

# No tocar la ruta global ni reintroducir comandos viejos.
for forbidden in ("call_action_by(2, 3", "call_action_by(7, 3"):
    assert forbidden not in targeted

assert "class App(app_v161.App):" in app
assert "LIMPIEZA DIRIGIDA V162" in app
assert "9/8 -> 9/3; fallback 9/2 -> 9/3" in app
assert "import app_v162" in main
assert "app_v162.App().mainloop()" in main
assert '"generation": "V162-IA"' in meta
assert '"entry_module": "app_v162"' in meta

print("V162 smoke OK: target is loaded then 9/3 always starts room/zone cleaning.")

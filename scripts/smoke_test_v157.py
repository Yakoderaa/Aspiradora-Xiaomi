from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v157.py").read_text(encoding="utf-8")
whole = (ROOT / "src" / "whole_home_v157.py").read_text(encoding="utf-8")
targeted = (ROOT / "src" / "targeted_v157.py").read_text(encoding="utf-8")
learning = (ROOT / "src" / "route_learning_v157.py").read_text(encoding="utf-8")
scheduler = (ROOT / "src" / "scheduler_v157.py").read_text(encoding="utf-8")
plan = (ROOT / "src" / "cleaning_plan.py").read_text(encoding="utf-8")
main = (ROOT / "src" / "main_current.py").read_text(encoding="utf-8")
meta = (ROOT / "release_meta.json").read_text(encoding="utf-8")
build = (ROOT / "build.ps1").read_text(encoding="utf-8")
installer = (ROOT / "installer" / "AspiradoraXiaomi.iss").read_text(encoding="utf-8")

assert "import app_v157" in main
assert "app_v157.App()" in main
assert '"generation": "V157-IA"' in meta
assert '"entry_module": "app_v157"' in meta

# Una sola acción de vivienda en GUI, botón heredado y programaciones.
assert 'text="Limpiar vivienda"' in app
assert "def start_clean(self):" in app
assert 'return self._v157_whole_home(source="whole-home-unified")' in app
schedule_now = app.split("def _run_schedule_now", 1)[1].split("# =============================================================== eventos", 1)[0]
assert 'if target == "all":' in schedule_now
assert "return self.start_clean()" in schedule_now

# Ruta física global compartida: sólo START 2/1.
assert '_action_locked(2, 1, "V157 whole-home start 2/1")' in whole
assert "_action_locked(2, 3" not in whole
assert "_action_locked(7, 3" not in whole
assert "writes_before_start" in whole

# Aprendizaje: vivienda principal, objetivos secundarios.
assert "merge_primary" in learning
assert "merge_target" in learning
assert "TrajectorySamplerV157" in learning
assert "WRAP_UNITS = 256.0" in learning

# Habitaciones renombrables y programadas por ID estable.
assert "Renombrar habitación" in app
assert "local_map.rename_room" in app
assert '"room_ids": room_ids' in app
assert "VERSION = 4" in plan
assert 'item.setdefault("room_ids", [])' in plan

# Limpieza dirigida nunca reutiliza 2/3.
assert "call_action_by(9, 8" in targeted
assert "call_action_by(9, 3" in targeted
assert "call_action_by(2, 3" not in targeted

# Scheduler real, liviano y misma ruta de vivienda.
assert "WholeHomeRunnerV157" in scheduler
assert "TargetedRunnerV157" in scheduler
assert "time.sleep(60)" in scheduler
assert "src\\scheduler_v157.py" in build
assert "src\\scheduler_baseline_disabled.py" not in build
assert 'ValueName: "AspiradoraXiaomiScheduler"' in installer
assert "\n[Run]\n" in installer.replace("\r\n", "\n")

# V157 sigue heredando el pipeline Lite de V156 y baja aún más la frecuencia.
assert "LOCAL_ACTIVE_POLL_MS = 5000" in app
assert "LOCAL_IDLE_POLL_MS = 30000" in app
assert "RENDER_MIN_INTERVAL_SECONDS = 5.0" in app
assert "super()._diagnostic_text()" not in app.split("def _diagnostic_text", 1)[1]

print("V157 smoke OK: unified whole-home + learning + rooms scheduler + lite.")

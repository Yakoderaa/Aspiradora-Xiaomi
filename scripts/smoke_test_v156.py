from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v156.py").read_text(encoding="utf-8")
# Contrato físico preservado: build-map oficial + un único START 2/1.
worker = app.split("def _v155_mapping_worker", 1)[1]
worker = worker.split("# =============================================================== eventos", 1)[0]
assert "call_action_by(10, 17, [1])" in worker
assert "call_action_by(2, 1)" in worker
assert "call_action_by(2, 3" not in worker
assert "call_action_by(7, 3" not in worker
assert "start_mapping_whole_home" not in worker
assert "start_mapping_exploration" not in worker
assert "manual(" not in worker

# V156 no finaliza un mapa por status 0/1; espera dock físico.
assert 'if status == 4:' in worker
assert '"timeout_waiting_dock"' in worker
assert "idle_streak >= 3" in worker

# Performance: Cloud histórico/mapa deshabilitado y UI/polling desacelerados.
assert "LOCAL_ACTIVE_POLL_MS = 3000" in app
assert "LOCAL_IDLE_POLL_MS = 10000" in app
assert "RENDER_MIN_INTERVAL_SECONDS = 3.0" in app
assert "def _maybe_poll_cloud_position" in app
assert "def _v38_maybe_poll_map_file" in app
assert "Cloud de recorrido=DESACTIVADO" in app

# Coordenadas B112: unwrap módulo 256 y guía persistente.
assert "RAW_WRAP_UNITS = 256.0" in app
assert "route_guide_v156.json" in app
assert "GUIDE_SAMPLE_METERS = 0.25" in app
assert "def _v156_save_guide" in app

# El diagnóstico nuevo es deliberadamente corto; no concatena 120 versiones.
diag = app.split("def _diagnostic_text", 1)[1]
assert "super()._diagnostic_text()" not in diag

print("V156 smoke OK: lean UI + wrap256 + guide learning + physical 2/1 contract.")

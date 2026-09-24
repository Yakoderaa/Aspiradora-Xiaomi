from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v159.py").read_text(encoding="utf-8")
main = (ROOT / "src" / "main_current.py").read_text(encoding="utf-8")
meta = (ROOT / "release_meta.json").read_text(encoding="utf-8")

# La UI ya no debe esperar 250 ms cuando la cola está ociosa.
assert "self.after(8 if pending else 25, self._drain_ui_events)" in app
assert "UI_EVENT_BUDGET = 120" in app

# Telemetría y render vuelven a una cadencia responsiva sin reactivar Cloud.
assert "LOCAL_ACTIVE_POLL_MS = 1000" in app
assert "LOCAL_IDLE_POLL_MS = 5000" in app
assert "LOCAL_BUSY_RETRY_MS = 350" in app
assert "RENDER_MIN_INTERVAL_SECONDS = 1.25" in app

# Abrir Diagnóstico devuelve caché; el informe completo se construye en worker.
diag = app.split("def _diagnostic_text", 1)[1].split("def _refresh_map_diag_window", 1)[0]
assert "return self._v159_diag_cache" in diag
assert "app_v158.App._diagnostic_text(self)" in app
assert 'name="V159DiagnosticSnapshot"' in app

# Cambio de pantalla: primero navegación, render pesado diferido.
assert "def show_page(self, page):" in app
assert "PAGE_RENDER_DEFER_MS = 80" in app
assert "self._v159_page_render_request" in app

# Limpieza global/dirigida: _fresh y diagnostic viven dentro del worker.
whole = app.split("def _v157_whole_home", 1)[1].split("def _v157_start_target_job", 1)[0]
whole_prefix = whole.split("def worker", 1)[0]
whole_worker = whole.split("def worker", 1)[1]
assert "self._fresh()" not in whole_prefix
assert "core = self._fresh()" in whole_worker
assert "core._read()" not in whole_prefix

target = app.split("def _v157_start_target_job", 1)[1].split("# =============================================================== eventos", 1)[0]
target_prefix = target.split("def worker", 1)[0]
target_worker = target.split("def worker", 1)[1]
assert "self._fresh()" not in target_prefix
assert "core = self._fresh()" in target_worker

# La versión publicada debe entrar por V159.
assert "import app_v159" in main
assert "app_v159.App().mainloop()" in main
assert '"generation": "V159-IA"' in meta
assert '"entry_module": "app_v159"' in meta

print("V159 smoke OK: UI low-latency + diagnostics cache + async cleaning preflight.")

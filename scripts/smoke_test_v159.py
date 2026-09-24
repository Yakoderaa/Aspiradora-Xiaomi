from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v159.py").read_text(encoding="utf-8")

assert "self.after(8 if pending else 25, self._drain_ui_events)" in app
assert "UI_EVENT_BUDGET = 120" in app
assert "LOCAL_ACTIVE_POLL_MS = 1000" in app
assert "LOCAL_IDLE_POLL_MS = 5000" in app
assert "LOCAL_BUSY_RETRY_MS = 350" in app
assert "RENDER_MIN_INTERVAL_SECONDS = 1.25" in app

diag = app.split("def _diagnostic_text", 1)[1].split("def _refresh_map_diag_window", 1)[0]
assert "return self._v159_diag_cache" in diag
assert "app_v158.App._diagnostic_text(self)" in app
assert 'name="V159DiagnosticSnapshot"' in app

assert "def show_page(self, page):" in app
assert "PAGE_RENDER_DEFER_MS = 80" in app
assert "self._v159_page_render_request" in app

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

assert "class App(app_v158.App):" in app

print("V159 smoke OK: historical low-latency UI contract preserved.")

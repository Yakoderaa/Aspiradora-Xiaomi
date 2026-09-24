from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v161.py").read_text(encoding="utf-8")
main = (ROOT / "src" / "main_current.py").read_text(encoding="utf-8")
meta = (ROOT / "release_meta.json").read_text(encoding="utf-8")

assert "class App(app_v160.App):" in app
assert "LOCAL_ACTIVE_POLL_MS = 2000" in app
assert "LOCAL_IDLE_POLL_MS = 15000" in app
assert "RENDER_MIN_INTERVAL_SECONDS = 2.5" in app
assert "DIAG_REBUILD_SECONDS = 15.0" in app
assert "FINAL_MAP_DELAYS_MS = (15000, 45000)" in app

# No puede capturar Cloud sólo por estar docked sin una sesión V160 pendiente.
begin = app.split("def _v158_begin_capture", 1)[1].split("def _v158_next_capture", 1)[0]
assert '_v160_pending_session' in begin
assert "return False" in begin

# Primer mapa válido termina los reintentos.
next_capture = app.split("def _v158_next_capture", 1)[1].split("# =============================================== diagnóstico", 1)[0]
assert 'if bool(diag.get("saved")):' in next_capture
assert "_v158_capture = None" in next_capture
assert "_v160_pending_session = None" in next_capture

# Diagnóstico periódico no puede llamar al constructor gigante V158/V151.
compact = app.split("def _v161_compact_diagnostic_text", 1)[1].split("def _v159_request_diag_refresh", 1)[0]
assert "app_v158.App._diagnostic_text" not in compact
assert "app_v151" not in compact
assert "repr(state)" not in compact
assert '"path_points": len(path)' in compact
assert "V161CompactDiagnostic" in app

# UI sigue rápida bajo carga y duerme más cuando está ociosa.
assert "self.after(8 if pending else 60, self._drain_ui_events)" in app

# V161 no agrega órdenes físicas.
for forbidden in ("_action_locked(", "set_property(", "start_sweep(", "start_mapping_perimeter("):
    assert forbidden not in app

assert "import app_v161" in main
assert "app_v161.App().mainloop()" in main
assert '"generation": "V161-IA"' in meta
assert '"entry_module": "app_v161"' in meta

print("V161 smoke OK: compact diagnostics + single-success final capture + lower background cadence.")

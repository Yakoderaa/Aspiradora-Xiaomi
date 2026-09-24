from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v155.py").read_text(encoding="utf-8")

# Contrato histórico de V155: build oficial 10/17 + un único start 2/1.
assert "call_action_by(10, 17, [1])" in app
assert "call_action_by(2, 1)" in app
mapping = app.split("def _v155_mapping_worker", 1)[1]
mapping = mapping.split("def finish_mapping", 1)[0]
assert "call_action_by(2, 3" not in mapping
assert "call_action_by(7, 3" not in mapping
assert "start_mapping_whole_home" not in mapping
assert "start_mapping_exploration" not in mapping
assert "start_mapping_perimeter" not in mapping
assert "manual(" not in mapping
assert "set_property_by" not in mapping

print("V155 smoke OK: historical mapping contract = 10/17 + single 2/1.")

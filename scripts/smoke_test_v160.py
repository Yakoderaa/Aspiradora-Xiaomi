from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src" / "app_v160.py").read_text(encoding="utf-8")
learner = (ROOT / "src" / "map_learning_v160.py").read_text(encoding="utf-8")

assert "class App(app_v159.App):" in app
assert "_action_locked" not in app
assert "set_property" not in app
assert "start_sweep" not in app

assert '"v157_whole_finished"' in app
assert '"v155_mapping_finished"' in app
assert '"v157_target_finished"' in app
assert 'kind == "v158_final_map"' in app
assert 'name="V160MapLearning"' in app
assert 'app_v159.App._handle_ui_event(' in app

assert "MAX_SESSIONS = 8" in learner
assert "MIN_HISTORY_SUPPORT = 2" in learner
assert "SUPPORT_RATIO = 0.35" in learner
assert "combined = current_set | stable" in learner
assert "sessions = sessions[-int(self.MAX_SESSIONS):]" in learner
assert '"xiaomi-v160-ai-consensus"' in learner
assert 'str(s.get("key") or "") != session_key' in learner

assert "APRENDIZAJE DE MAPA V160-IA" in app
assert 'name="V160DiagnosticSnapshot"' in app
assert "from map_learning_v160 import MapLearningStoreV160" in app

print("V160 smoke OK: persistent AI map consensus without navigation changes.")

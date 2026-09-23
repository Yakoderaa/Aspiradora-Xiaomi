from pathlib import Path
import inspect
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v151.py")
build = text("build.ps1")

assert "class App(app_v150.App)" in app
assert "start_mapping_whole_home(" in app
assert "arm_new_map(1)" in app
assert "EDGE automático queda eliminado" in app
assert "$lastExplicitVersion" in build

import app_v151

start_source = inspect.getsource(app_v151.App.start_new_mapping)

# Contrato central: el arranque automático no ejecuta EDGE ni maniobras
# manuales; arma un mapa una vez y arranca whole-home V123.
assert start_source.count("build_diag = vacuum.arm_new_map(1)") == 1, start_source
assert "start_mapping_whole_home(" in start_source
assert "_v138_start_factory_edge(" not in start_source
assert "start_mapping_exploration(" not in start_source
assert ".manual(" not in start_source
assert "vacuum.stop()" not in start_source

probe = object.__new__(app_v151.App)
probe._v151_direct_global_owner = True
probe.mapping_active = True
probe.mapping_phase = 2
probe._v121_stage = "global-v151"
probe._v145_session_latched = False
probe._v145_reset_guard = False
probe._v151_edge_blocks = 0
probe._v151_escape_blocks = 0
probe._v151_abort_blocks = 0
probe._v151_late_control_blocks = 0
probe._v141_log = lambda *args, **kwargs: None
probe._v144_auto_abort_requested = True

assert probe._v151_owner_active() is True

# Ningún controlador heredado puede tomar ruedas o cerrar la sesión global.
edge = probe._v138_start_factory_edge(object(), "late edge")
assert edge["movement_commands"] == 0, edge
assert probe._v151_edge_blocks == 1

assert probe._v147_schedule_escape(1, {}) is False
assert probe._v151_escape_blocks == 1

assert probe._v147_request_abort(1, {}, "late abort") is None
assert probe._v151_abort_blocks == 1

assert probe._v144_execute_auto_abort(1, {}) is False
assert probe._v151_abort_blocks == 2
assert probe._v144_auto_abort_requested is False

assert probe._v149_request_global_transition(1, {}, "already global") is True
assert probe._v151_late_control_blocks == 1

# El monitor de estrategia V150 tampoco puede abrir una transición paralela
# durante el whole-home directo.
assert probe._v150_session_allows_strategy_switch(1) is False
assert probe._v151_late_control_blocks == 2

# La propiedad V151 no depende de phase/stage transitorios de V121.
probe.mapping_phase = 1
probe._v121_stage = "edge"
assert probe._v151_owner_active() is True
probe.mapping_phase = 2
probe._v121_stage = "global-v151"

# Cerrar el cerrojo desactiva inmediatamente la autoridad global.
probe._v145_session_latched = True
assert probe._v151_owner_active() is False

# No se reemplaza el whole-home nativo V123 ni el cierre final Xiaomi.
assert "def start_mapping_whole_home" not in app
assert "def _v84_close_mapping_on_dock" not in app
assert "def _v107_choose_final_grid" not in app

print("V151-IA smoke OK")

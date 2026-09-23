from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v149.py")
build = text("build.ps1")

assert "class App(app_v148.App)" in app
assert "GLOBAL_AFTER_FAILED_ESCAPES = 2" in app
assert "def _v149_request_global_transition" in app
assert "def _v149_start_global_now" in app
assert "self._v121_request_phase2(" in app
assert "arm_new_map_called" in app
assert "tercer reinicio EDGE queda eliminado" in app
assert "$lastExplicitVersion" in build
assert "-gt 147" not in build

import app_v149

# Después de dos escapes fallidos, la tercera acción debe ser transición
# whole-home; no debe llamar otra vez al EDGE heredado.
probe = object.__new__(app_v149.App)
probe._v147_escape_consecutive = 2
probe._v149_global_requested = False
probe._v149_global_started = False
probe._v149_global_failed = False
probe._v145_session_latched = False
probe._v145_reset_guard = False
probe._v74_mapping_serial = 7
probe.mapping_active = True
probe.mapping_phase = 1

called = {}
probe._v149_request_global_transition = lambda serial, metrics, reason: (
    called.update({
        "serial": serial,
        "reason": reason,
        "metrics": dict(metrics),
    })
    or True
)

metrics = {
    "pattern": "oscillation_corridor",
    "v148_persistent_strip": True,
    "v148_2d_ratio": 0.10,
    "oscillation_reversals": 9,
    "path_m": 25.6,
}
assert probe._v147_schedule_escape(7, metrics) is True
assert called["serial"] == 7, called
assert "dos escapes EDGE" in called["reason"], called

# El auto-abort heredado también debe convertirse primero a whole-home cuando
# la sesión física sigue abierta y el problema es la misma franja 1D.
called.clear()
probe._v147_request_abort(7, metrics, "legacy abort")
assert called["serial"] == 7, called
assert "whole-home" in called["reason"], called

# Con sesión cerrada el gate ya no autoriza transición global.
probe._v145_session_latched = True
assert probe._v149_can_switch_global(7, metrics) is False

assert "import app_v149" in main_current
assert "app_v149.App().mainloop()" in main_current
assert '"generation": "V149-IA"' in meta

print("V149-IA smoke OK")

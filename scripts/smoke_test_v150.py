from pathlib import Path
import inspect
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


app = text("src/app_v150.py")
build = text("build.ps1")

assert "class App(app_v149.App)" in app
assert "STRATEGY_VOTES_REQUIRED = 4" in app
assert "_v82_corrected_samples" in app
assert "def _v150_strategy_metrics" in app
assert "def _v150_request_phase2" in app
assert "vacuum.stop()" in app
assert "vacuum.start_mapping_whole_home(" in app
assert '"arm_new_map_called": False' in app
assert "def _v150_transition_session_valid" in app
assert "$lastExplicitVersion" in build

import app_v150

probe = object.__new__(app_v150.App)

# Caso físico observado: mucho ida/vuelta en una banda estrecha. La señal
# viene de V82, no del clasificador V148.
bad = []
t = 0.0
for cycle in range(12):
    for i in range(16):
        bad.append((t, i * 0.10, 0.10 * (cycle % 3), 0.0))
        t += 0.55
    for i in range(15, -1, -1):
        bad.append((t, i * 0.10, 0.10 * ((cycle + 1) % 3), math.pi))
        t += 0.55

m = probe._v150_strategy_metrics(bad, 420.0)
assert m["evidence"] is True, m
assert m["ratio_2d"] <= app_v150.App.STRATEGY_MAX_2D_RATIO, m
assert m["reversals"] >= app_v150.App.STRATEGY_MIN_REVERSALS, m
assert m["path_to_along"] >= app_v150.App.STRATEGY_MIN_PATH_TO_ALONG, m

# Pasillo legítimo en una sola dirección: puede ser angosto, pero no revierte
# ni desperdicia varias veces la misma distancia.
corridor = [
    (i * 0.7, i * 0.10, 0.04 * math.sin(i / 8.0), 0.0)
    for i in range(150)
]
c = probe._v150_strategy_metrics(corridor, 180.0)
assert c["evidence"] is False, c
assert c["reversals"] < app_v150.App.STRATEGY_MIN_REVERSALS, c

# Habitación explorada en 2D: aunque haya vueltas, el ratio transversal
# impide clasificarla como EDGE improductivo.
room = []
t = 0.0
for lap in range(6):
    for i in range(21):
        room.append((t, i * 0.10, 0.0, 0.0)); t += 0.5
    for i in range(1, 21):
        room.append((t, 2.0, i * 0.10, 1.57)); t += 0.5
    for i in range(19, -1, -1):
        room.append((t, i * 0.10, 2.0, 3.14)); t += 0.5
    for i in range(19, 0, -1):
        room.append((t, 0.0, i * 0.10, -1.57)); t += 0.5
r = probe._v150_strategy_metrics(room, 300.0)
assert r["evidence"] is False, r
assert r["ratio_2d"] > app_v150.App.STRATEGY_MAX_2D_RATIO, r

# Gate de sesión: la evidencia de estrategia V150 habilita whole-home aunque
# V148 no haya clasificado persistent_strip.
probe._v74_mapping_serial = 12
probe.mapping_active = True
probe.mapping_phase = 1
probe.mapping_transitioning = False
probe._v145_session_latched = False
probe._v145_reset_guard = False
probe._v143_manual_return_requested = False
probe._v137_manual_cancel = False
probe._v136_manual_abort = False
probe._v74_finish_requested = False
probe._v150_manual_cancel = False
probe._v150_strategy_confirmed = True
assert probe._v149_can_switch_global(
    12,
    {"v150_strategy_evidence": True, "v148_persistent_strip": False},
) is True

# Volver a base / cerrojo anulan el cambio de estrategia.
probe._v145_session_latched = True
assert probe._v149_can_switch_global(
    12,
    {"v150_strategy_evidence": True},
) is False
probe._v145_session_latched = False
probe._v143_manual_return_requested = True
assert probe._v149_can_switch_global(
    12,
    {"v150_strategy_evidence": True},
) is False

# El detector de atasco físico sigue disponible por separado: si V148 da
# evidencia fuerte, whole-home también puede ser el fallback después de escapes.
probe._v143_manual_return_requested = False
probe._v150_strategy_confirmed = False
assert probe._v149_can_switch_global(
    12,
    {
        "v148_persistent_strip": True,
        "pattern": "oscillation_corridor",
    },
) is True

# Una transición global ya solicitada bloquea nuevos escapes. No debe aumentar
# el contador ni ejecutar la maniobra heredada.
probe._v149_global_requested = True
probe._v147_escape_consecutive = 0
probe._v147_escape_total = 2
before_total = probe._v147_escape_total
assert probe._v147_schedule_escape(12, {}) is True
assert probe._v147_escape_total == before_total
probe._v149_global_requested = False

# V150 no reemplaza _v121_request_phase2: el camino natural EDGE->dock de
# V121/V137 queda intacto. Sólo la transición anticipada usa su worker aislado.
assert "def _v121_request_phase2" not in app
transition_source = inspect.getsource(app_v150.App._v150_request_phase2)
assert "arm_new_map(" not in transition_source
assert ".manual(" not in transition_source
assert "_v138_start_factory_edge" not in transition_source
assert "start_mapping_whole_home" in transition_source
assert "vacuum.stop()" in transition_source

# En transición, el worker sólo es válido en fase 2/transition y con sesión
# abierta. Esto evita que un worker tardío reviva un mapa cancelado.
dummy_vacuum = object()
probe.vacuum = dummy_vacuum
probe._v143_manual_return_requested = False
probe.mapping_phase = 2
probe._v121_stage = "transition"
probe._v150_manual_cancel = False
assert probe._v150_transition_session_valid(12, dummy_vacuum) is True
probe._v150_manual_cancel = True
assert probe._v150_transition_session_valid(12, dummy_vacuum) is False

print("V150-IA smoke OK")

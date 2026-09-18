import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v68


# Helpers: sweep-type=2 ya no es requisito.
assert app_v68.App._v68_completion_reason(
    seen_moving=True,
    departed_base=False,
    status=3,
    charging_state=2,
) == "status=3 · regresando a base"

assert app_v68.App._v68_completion_reason(
    seen_moving=False,
    departed_base=True,
    status=4,
    charging_state=1,
) == "charging-state=1 · acoplado/cargando"

# Estar en base sin haber visto movimiento/salida NO prueba que Paso 1 ocurrió.
assert app_v68.App._v68_completion_reason(
    seen_moving=False,
    departed_base=False,
    status=4,
    charging_state=1,
) is None

# Inactividad estable después de movimiento cuenta como fin.
assert app_v68.App._v68_completion_reason(
    seen_moving=True,
    departed_base=False,
    status=1,
    charging_state=2,
    idle_stable_seconds=3.0,
) == "status=1 estable tras movimiento"

# Última comprobación de timeout: si ya está de vuelta/cargando, nunca error.
assert app_v68.App._v68_timeout_completion_reason(
    seen_moving=True,
    departed_base=True,
    status=4,
    charging_state=1,
) is not None


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(float(seconds), 0.01)


class SequenceVacuum:
    def __init__(self, states):
        self.states = list(states)
        self.index = 0
        self.stop_calls = 0

    def _get_many(self, defs):
        if self.index < len(self.states):
            state = self.states[self.index]
            self.index += 1
        else:
            state = self.states[-1]
        return dict(state)

    def stop(self):
        self.stop_calls += 1


# Caso real V67: arranca acoplado, se mueve con sweep_type=0 todo el tiempo,
# luego vuelve con status=3. Antes terminaba por timeout; V68 debe completar.
clock = FakeClock()
orig_monotonic = app_v68.time.monotonic
orig_sleep = app_v68.time.sleep
app_v68.time.monotonic = clock.monotonic
app_v68.time.sleep = clock.sleep
try:
    vacuum = SequenceVacuum([
        {"status": 4, "sweep_type": 0, "charging_state": 1},
        {"status": 6, "sweep_type": 0, "charging_state": 2},
        {"status": 6, "sweep_type": 0, "charging_state": 2},
        {"status": 3, "sweep_type": 0, "charging_state": 2},
    ])
    app = app_v68.App.__new__(app_v68.App)
    app.vacuum = vacuum
    app._edge_session = 7
    app.mapping_phase = 1
    app._v68_edge_diag = {}
    app._edge_log = lambda text: None
    events = []
    app._post_ui = lambda kind, *payload: events.append((kind, payload))

    app._watch_edge_only(7)

    assert any(kind == "edge_only_complete" for kind, _ in events)
    assert not any(kind == "edge_only_error" for kind, _ in events)
    assert app._v68_edge_diag["seen_moving"] is True
    assert app._v68_edge_diag["departed_base"] is True
    assert app._v68_edge_diag["seen_edge_type"] is False
    assert "status=3" in app._v68_edge_diag["completion_reason"]
    assert app._v68_edge_diag["timeout"] is False
    assert vacuum.stop_calls == 0
finally:
    app_v68.time.monotonic = orig_monotonic
    app_v68.time.sleep = orig_sleep


# Una sesión distinta o fase distinta debe salir silenciosamente, sin error.
app = app_v68.App.__new__(app_v68.App)
app.vacuum = SequenceVacuum([
    {"status": 6, "sweep_type": 0, "charging_state": 2},
])
app._edge_session = 9
app.mapping_phase = 0
app._v68_edge_diag = {}
app._edge_log = lambda text: None
events = []
app._post_ui = lambda kind, *payload: events.append((kind, payload))
app._watch_edge_only(9)
assert events == []

assert issubclass(app_v68.App, app_v68.app_v67.App)

print("SMOKE TEST V68 OK: fin Paso 1 sin sweep_type=2 + retorno/base evita timeout falso")

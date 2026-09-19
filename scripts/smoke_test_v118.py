import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v118
import xiaomi_e10


for path in (
    SRC / "app_v118.py",
    SRC / "main_v118.py",
    SRC / "xiaomi_e10.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v118.App, app_v118.app_v117.App)


class FakeDevice:
    def __init__(self):
        self.calls = []

    def call_action_by(self, siid, aiid, params=None):
        self.calls.append((siid, aiid, params))
        return {"code": 0}

    def set_property_by(self, siid, piid, value):
        return [{"code": 0}]


vacuum = xiaomi_e10.XiaomiE10.__new__(xiaomi_e10.XiaomiE10)
vacuum.device = FakeDevice()
vacuum._global_clean_guard = 0
vacuum._global_clean_seen_active = False
vacuum._global_clean_terminal_streak = 0
vacuum._global_clean_guard_source = None
vacuum._global_clean_guard_started_at = 0.0
vacuum._global_clean_guard_cleared_at = 0.0
vacuum._blocked_duplicate_starts = 0
vacuum._last_blocked_duplicate_start = None
vacuum._motor_start_audit = []
vacuum._targeted_clean_guard = 0
vacuum._targeted_clean_blocked_mapping_calls = 0
vacuum._targeted_clean_last_blocked = None

# START inicial permitido.
vacuum._send_motor_start("initial", 2, 3)
assert vacuum.device.calls == [(2, 3, None)]

# Una vez físicamente activo, ningún segundo START puede salir.
vacuum.begin_global_clean_guard("smoke")
blocked = False
try:
    vacuum._send_motor_start("duplicate", 2, 3)
except RuntimeError:
    blocked = True
assert blocked
assert vacuum._blocked_duplicate_starts == 1
assert len(vacuum.device.calls) == 1

# Dos lecturas idle transitorias NO liberan; dock físico sí.
vacuum._note_global_clean_status(1)
vacuum._note_global_clean_status(1)
assert vacuum.global_clean_guard_active()
vacuum._note_global_clean_status(4)
assert not vacuum.global_clean_guard_active()

# El guard de mapeo también usa el candado físico independiente.
vacuum.begin_global_clean_guard("mapping-fence")
mapping_blocked = False
try:
    vacuum._reject_mapping_during_targeted_clean("smoke_mapping")
except RuntimeError:
    mapping_blocked = True
assert mapping_blocked

source=(SRC / "app_v118.py").read_text(encoding="utf-8")
for required in (
    "sesión física activa",
    "START duplicados bloqueados",
    "mismatch físico>worker V115",
    "recoveries legacy bloqueados fuera de mapeo",
    "auditoría de órdenes de ARRANQUE",
):
    assert required in source, required

print(
    "SMOKE TEST V118 OK: candado físico sobrevive al worker, "
    "bloquea START duplicado y sólo libera en dock físico"
)

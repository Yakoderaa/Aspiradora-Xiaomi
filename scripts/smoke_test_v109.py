import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v109

for path in (
    SRC / "app_v109.py",
    SRC / "main_v109.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v109.App, app_v109.app_v108.App)

# La IP visible debe ser redactable sin tocar texto normal.
redacted, count = app_v109.App._v109_redact_ips(
    "Conectado · 192.168.1.27 | otra=10.0.0.5"
)
assert redacted == "Conectado · [IP OCULTA] | otra=[IP OCULTA]"
assert count == 2

source = (SRC / "app_v109.py").read_text(encoding="utf-8")
for required in (
    'super()._set_connection(True, "Conectado")',
    "DIAGNÓSTICO V109 DE EMERGENCIA",
    "una excepción heredada no puede dejar F12 en blanco",
    "direcciones IP ocultas",
    "_refresh_map_diag_window",
    "_copy_map_diagnostics",
):
    assert required in source, required

print(
    "SMOKE TEST V109 OK: F12 fail-safe + emergency diagnostics + "
    "connection/IP privacy"
)

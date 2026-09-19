import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v98

for path in (
    SRC / "app_v98.py",
    SRC / "main_v98.py",
    SRC / "updater.py",
    SRC / "update_helper.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v98.App, app_v98.app_v97.App)
assert set(app_v98.PAGE_TITLES) == {"es", "en", "pt"}
assert app_v98.LIGHT["app_bg"] != app_v98.DARK["app_bg"]

dummy = app_v98.App.__new__(app_v98.App)
dummy.settings = {"language": "en"}
assert dummy._v98_translate("Inicio") == "Home"
assert dummy._v98_translate("Cargando") == "Charging"
dummy.settings = {"language": "pt"}
assert dummy._v98_translate("Volviendo a la base") == "Voltando à base"

source = (SRC / "app_v98.py").read_text(encoding="utf-8")
for required in (
    "self.withdraw()",
    "def _v39_restore_saved_window",
    "Español",
    "English",
    "Português",
    "Claro",
    "Oscuro",
    "update V98: descarga + SHA visibles en modal",
):
    assert required in source, required

updater = (SRC / "updater.py").read_text(encoding="utf-8")
helper = (SRC / "update_helper.py").read_text(encoding="utf-8")
assert "CREATE_NO_WINDOW" in updater
assert "--theme" in updater and "--language" in updater
assert "/VERYSILENT" in helper
assert "CREATE_NO_WINDOW" in helper
assert "/SILENT" not in helper.replace("/VERYSILENT", "")

print("SMOKE TEST V98 OK: theme/language + hidden startup + GUI-only updater")

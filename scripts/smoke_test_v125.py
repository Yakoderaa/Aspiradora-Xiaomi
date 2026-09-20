import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v125

for path in (
    SRC / "app_v125.py",
    SRC / "main_v125.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v125.App, app_v125.app_v124.App)

source = (SRC / "app_v125.py").read_text(encoding="utf-8")
assert "Ya conecté el túnel · ir al Paso 4" in source
assert "4 · Vincular Aspiradora Xiaomi dentro de ChatGPT" in source
assert "canvas.yview_moveto(1.0)" in source
assert 'bind_all("<MouseWheel>"' in source
assert "Túnel OpenAI conectado · falta vincular la app en ChatGPT" in source
assert "ChatGPT Plus no figura" in source
assert "nunca afirmar 'ChatGPT conectado'" in source

print(
    "SMOKE TEST V125 OK: wizard scrollable, Paso 4 accesible y "
    "estado túnel/vínculo ChatGPT separados"
)

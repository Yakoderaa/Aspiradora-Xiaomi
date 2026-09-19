import ast
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src"
if str(SRC) not in sys.path:
    sys.path.insert(0,str(SRC))

import app_v97

for path in (
    SRC/"app_v97.py",
    SRC/"main_v97.py",
    SRC/"windows_audio_identity.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

assert issubclass(app_v97.App, app_v97.app_v96.App)

early={"points":[{"x":-0.1*i,"y":0.0} for i in range(11)]}
m=app_v97.App._v97_geometry_metrics(early)
assert m["mature"] is False
cells=app_v97.App._v87_floor_cells(early)
assert 0 < len(cells) < 60, len(cells)

mature={"points":[]}
for row in range(6):
    y=row*0.16
    for col in range(10):
        mature["points"].append({"x":col*0.16,"y":y})
m2=app_v97.App._v97_geometry_metrics(mature)
assert m2["mature"] is True

audio=(SRC/"windows_audio_identity.py").read_text(encoding="utf-8")
for required in (
    "SND_LOOP",
    "SetDisplayName",
    "own_sessions_seen",
    "silent_session_started",
    'DISPLAY_NAME = "Aspiradora"',
):
    assert required in audio, required

source=(SRC/"app_v97.py").read_text(encoding="utf-8")
for required in (
    "huella temprana",
    "EARLY_VIEWPORT_HALF_METERS = 2.0",
    "una trayectoria casi lineal nunca",
):
    assert required in source, required

print("SMOKE TEST V97 OK: fallback temprano prudente + viewport estable + sesión Sonar Aspiradora")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v71


app = app_v71.App.__new__(app_v71.App)
app._v71_session_origin_raw = (60.0, 60.0)
app._v71_session_max_departure = 50.0

# 1) Un único origen de sesión: la base queda en (0,0).
assert app._v71_normalize_xy((60.0, 60.0)) == (0.0, 0.0)
assert app._v71_normalize_xy((61.0, 7.0)) == (1.0, -53.0)
point = app._v71_normalize_point({"x": 65.0, "y": 55.0, "phi": 0.2})
assert point["x"] == 5.0 and point["y"] == -5.0

# 2) El umbral depende de la salida real y queda acotado.
limit = app._v71_return_limit()
assert 1.0 <= limit <= 4.0
assert abs(limit - 4.0) < 1e-9

# 3) Regresión crítica V69: status=3 quieto durante mucho tiempo NO confirma base.
mode, reason = app_v71.App._v69_fallback_reason(
    status=3,
    fault=0,
    saw_returning=True,
    return_elapsed=600,
    dock_reasserted=True,
    pose_stable_seconds=600,
    battery_start=95,
    battery_now=95,
)
assert mode is None
assert reason is None

# 4) status=4 sigue siendo confirmación directa.
mode, reason = app_v71.App._v69_fallback_reason(
    status=4,
    fault=0,
    saw_returning=True,
    return_elapsed=2,
    dock_reasserted=False,
    pose_stable_seconds=0,
    battery_start=95,
    battery_now=95,
)
assert mode == "direct"
assert "status=4" in reason

# 5) Una subida de batería durante retorno sí es evidencia fuerte.
mode, reason = app_v71.App._v69_fallback_reason(
    status=3,
    fault=0,
    saw_returning=True,
    return_elapsed=20,
    dock_reasserted=True,
    pose_stable_seconds=0,
    battery_start=94,
    battery_now=95,
)
assert mode == "battery-rise"
assert "94→95" in reason

# 6) Fault activo invalida la subida de batería.
mode, reason = app_v71.App._v69_fallback_reason(
    status=3,
    fault=5,
    saw_returning=True,
    return_elapsed=20,
    dock_reasserted=True,
    pose_stable_seconds=0,
    battery_start=94,
    battery_now=95,
)
assert mode is None and reason is None

# 7) La capa V71 conserva toda la lógica V70/V69.
assert issubclass(app_v71.App, app_v71.app_v70.App)

source = Path(SRC / "app_v71.py").read_text(encoding="utf-8")
required = (
    "status=3 nunca confirma base por tiempo/quietud",
    "origen único de sesión",
    "transformed[\"path\"] = []",
    "se bloqueó un nuevo perímetro automático",
    "_v71_ensure_cards",
    "child.destroy()",
    "MAP_CARD_REFRESH_SECONDS",
)
for item in required:
    assert item in source, item

# 8) La destrucción de widgets sólo puede ocurrir durante la creación inicial
# de las cuatro tarjetas; el refresh normal reutiliza esos widgets.
refresh_start = source.index("def _v70_refresh_map_overview")
refresh_end = source.index("# =========================================================== diagnóstico")
refresh_source = source[refresh_start:refresh_end]
assert "winfo_children()" not in refresh_source
assert ".destroy()" not in refresh_source

print("SMOKE TEST V71 OK: llegada real + origen único + Paso 2 protegido + UI estable")

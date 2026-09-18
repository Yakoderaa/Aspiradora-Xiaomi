import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v70
from local_mapping import LocalMapStore


assert app_v70.App.MAP_OVERVIEW_SLOTS == 4

# Biblioteca real: el modelo de UI siempre devuelve cuatro tarjetas.
with tempfile.TemporaryDirectory() as tmp:
    store = LocalMapStore(Path(tmp))
    first_id = store.active_map_id

    cards = app_v70.App._v70_card_models(store.library_snapshot())
    assert len(cards) == 4
    assert sum(1 for card in cards if card["active"]) == 1
    assert cards[0]["id"] == first_id
    assert cards[0]["empty"] is False
    assert all(card["empty"] for card in cards[1:])

    second = store.create_map("Planta alta")
    cards = app_v70.App._v70_card_models(store.library_snapshot())
    assert len(cards) == 4
    assert sum(1 for card in cards if card["active"]) == 1
    assert next(card for card in cards if card["active"])["name"] == "Planta alta"

    third = store.create_map("Garage")
    fourth = store.create_map("Taller")
    cards = app_v70.App._v70_card_models(store.library_snapshot())
    assert len(cards) == 4
    assert all(not card["empty"] for card in cards)
    assert next(card for card in cards if card["active"])["id"] == fourth["id"]

    # Cambiar la selección persiste y la UI puede reconstruirse sin biblioteca.
    store.select_map(first_id)
    cards = app_v70.App._v70_card_models(store.library_snapshot())
    assert next(card for card in cards if card["active"])["id"] == first_id

# El aviso final siempre dice qué mapa quedó seleccionado.
message = app_v70.App._v70_completion_message("Mi casa")
assert "Mapeo terminó" in message or "mapeo terminó" in message
assert "Mapa seleccionado: Mi casa" in message

# La capa V70 conserva V69: no se reemplaza la lógica de protocolo/mapeo.
assert issubclass(app_v70.App, app_v70.app_v69.App)

# El código de la pestaña debe mantener selección visible global y local.
source = Path(SRC / "app_v70.py").read_text(encoding="utf-8")
for required in (
    "SELECCIONADO",
    "Mapa seleccionado:",
    "MAPA ·",
    "+ Crear mapa",
    "Administrar",
    "_v70_notify_mapping_complete",
):
    assert required in source, required

print("SMOKE TEST V70 OK: 4 mapas visibles + selección persistente + aviso final")

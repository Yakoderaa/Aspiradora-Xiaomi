import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class FakePointDevice:
    def __init__(self, owner):
        self.owner = owner
        self.actions = []

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, list(params or [])))
        if siid == 9:
            self.owner.suction = 4
        return {"code": 0}

    def set_property_by(self, siid, piid, value):
        return {"code": 0}


class FakePointVacuum:
    def __init__(self):
        self.device = FakePointDevice(self)
        self.suction = 1
        self.water = 0
        self.mode = 0
        self.sweep_type = 0
        self.calls = []

    def set_suction(self, value):
        self.suction = int(value)
        self.calls.append(("suction", int(value)))

    def set_water(self, value):
        self.water = int(value)
        self.calls.append(("water", int(value)))

    def set_mode(self, value):
        self.mode = int(value)
        self.calls.append(("mode", int(value)))

    def set_sweep_type(self, value):
        self.sweep_type = int(value)
        self.calls.append(("sweep", int(value)))

    def _get_many(self, _props):
        return {"status": 5, "suction": self.suction}


def main():
    import app_v21
    import pystray
    from backup_bundle import read_bundle, write_bundle
    from cleaning_plan import CleaningPlanStore
    from local_mapping import LocalMapStore
    from map_geometry import build_mapped_walls
    from robot_plans import start_point_clean
    from xiaomi_e10_edge import XiaomiE10Edge
    from xiaomi_e10_live import XiaomiE10Live

    check(issubclass(XiaomiE10Live, XiaomiE10Edge), "La telemetría live debe conservar el controlador EDGE")
    check(hasattr(app_v21.App, "_start_tray_icon"), "Falta integración de bandeja")
    check(hasattr(app_v21.App, "open_quick_actions_config"), "Falta configuración de acciones rápidas")
    check(hasattr(app_v21.App, "_sync_no_go_async"), "Falta sincronización de bloqueos por mapa")
    check(hasattr(app_v21.App, "_map_double_click"), "Falta objetivo por doble clic")
    check(hasattr(app_v21.App, "_map_drag"), "Falta desplazamiento/pan del mapa")
    check(hasattr(app_v21.App, "logout_xiaomi_account"), "Falta desconexión de cuenta Xiaomi")
    check(hasattr(app_v21.App, "_rebuild_mapped_walls"), "Falta generación de paredes persistentes")
    check(bool(getattr(pystray.Icon, "HAS_DEFAULT_ACTION", False)), "La bandeja no expone acción primaria")

    parsed = XiaomiE10Live.parse_trajectory([10, 0.0, 0.0, 0.0, 1, 1.0, 2.0, 0.25, 1])
    check(len(parsed) == 2, "El parser de trayectoria no interpretó dos poses")
    check(parsed[-1]["x"] == 1.0 and parsed[-1]["y"] == 2.0, "Coordenadas de trayectoria incorrectas")

    fake = FakePointVacuum()
    point_plan = {"device_origin": {"x": 10.0, "y": 20.0}}
    start_point_clean(fake, {"x": 1.0, "y": 2.0}, point_plan, suction=2)
    check(fake.suction == 2, "La limpieza puntual quedó en Turbo en vez de restaurar la succión elegida")
    check(fake.sweep_type == 4, "La limpieza puntual no configuró sweep_type=4")
    check(fake.device.actions and fake.device.actions[0][0] == 9, "No se envió la acción de limpieza puntual")

    perimeter = [
        {"id": 1, "phase": 1, "x": 0.0, "y": 0.0, "phi": 0.0, "update": 1},
        {"id": 2, "phase": 1, "x": 1.0, "y": 0.0, "phi": 0.0, "update": 1},
        {"id": 3, "phase": 1, "x": 2.0, "y": 0.0, "phi": 0.0, "update": 1},
        {"id": 4, "phase": 1, "x": 2.0, "y": 1.0, "phi": 1.57, "update": 1},
        {"id": 5, "phase": 1, "x": 2.0, "y": 2.0, "phi": 1.57, "update": 1},
    ]
    walls = build_mapped_walls(perimeter)
    check(walls and len(walls[0].get("points", [])) >= 3, "EDGE no produjo una pared simplificada válida")

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        maps = LocalMapStore(folder)
        first_id = maps.active_map_id
        maps.merge_trajectory(perimeter, phase=1)
        maps.set_mapped_walls(walls)
        snap = maps.snapshot()
        check(len(snap["points"]) == len(perimeter), "No se persistió la trayectoria")
        check(snap.get("mapped_walls"), "Las paredes estimadas no quedaron guardadas dentro del mapa")

        for name in ("Planta alta", "Garage", "Patio"):
            maps.create_map(name)
        check(len(maps.list_maps()) == 4, "La biblioteca no guarda cuatro mapas")
        try:
            maps.create_map("Quinto")
        except RuntimeError:
            pass
        else:
            raise AssertionError("La biblioteca permitió más de cuatro mapas")

        plan = CleaningPlanStore(folder)
        plan.set_active_map(first_id)
        zone1 = plan.add_zone("Cocina", 0, 0, 2, 2)
        plan.add_no_go("Escalera", 3, 3, 4, 4)
        schedule = plan.add_schedule({
            "name": "Mañana",
            "days": [0, 2, 4],
            "hour": 9,
            "minute": 0,
            "mode": "vacuum",
            "target": "zones",
            "zone_ids": [zone1["id"]],
        })
        check(str(schedule.get("map_id")) == first_id, "La programación no quedó asociada al mapa activo")
        check(len(plan.snapshot(first_id)["zones"]) == 1, "La zona no quedó asociada al primer mapa")

        second_id = next(item["id"] for item in maps.list_maps() if item["id"] != first_id)
        plan.set_active_map(second_id)
        plan.add_zone("Dormitorio", 5, 5, 6, 6)
        check(len(plan.snapshot(second_id)["zones"]) == 1, "La zona del segundo mapa no se guardó")
        check(len(plan.snapshot(first_id)["zones"]) == 1, "Los mapas mezclaron sus zonas")
        check(len(plan.snapshot(second_id)["schedules"]) == 0, "Las programaciones se mezclaron entre mapas")

        backup = folder / "prueba.xvac"
        write_bundle(backup, maps.library_snapshot(), plan.snapshot_all())
        restored = read_bundle(backup)
        check(len(restored["maps"]["maps"]) == 4, "El backup no conserva los cuatro mapas")
        check(restored["cleaning_plan"]["schedules"], "El backup perdió programaciones")
        restored_first = next(item for item in restored["maps"]["maps"] if item.get("id") == first_id)
        check(restored_first.get("mapped_walls"), "El .xvac perdió las paredes estimadas del mapa")

        maps_restored = LocalMapStore(folder / "restored")
        maps_restored.replace_library(restored["maps"])
        check(len(maps_restored.list_maps()) == 4, "La importación no restauró los mapas")
        maps_restored.select_map(first_id)
        check(maps_restored.snapshot().get("mapped_walls"), "La importación no restauró las paredes del mapa")

    print("SMOKE TEST OK: EDGE+live, paredes persistentes, punto/succión, 4 mapas, planes, bandeja, pan y .xvac")


if __name__ == "__main__":
    main()

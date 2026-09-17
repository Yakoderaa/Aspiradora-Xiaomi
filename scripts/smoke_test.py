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


def main():
    # Todos los módulos críticos deben importar sin ejecutar la interfaz.
    import app_v19
    import pystray
    from backup_bundle import read_bundle, write_bundle
    from cleaning_plan import CleaningPlanStore
    from local_mapping import LocalMapStore
    from xiaomi_e10_edge import XiaomiE10Edge
    from xiaomi_e10_live import XiaomiE10Live

    check(issubclass(XiaomiE10Live, XiaomiE10Edge), "La telemetría live debe conservar el controlador EDGE")
    check(hasattr(app_v19.App, "_start_tray_icon"), "Falta integración de bandeja")
    check(hasattr(app_v19.App, "open_quick_actions_config"), "Falta configuración de acciones rápidas")
    check(bool(getattr(pystray.Icon, "HAS_DEFAULT_ACTION", False)), "La bandeja no expone acción primaria")

    parsed = XiaomiE10Live.parse_trajectory([10, 0.0, 0.0, 0.0, 1, 1.0, 2.0, 0.25, 1])
    check(len(parsed) == 2, "El parser de trayectoria no interpretó dos poses")
    check(parsed[-1]["x"] == 1.0 and parsed[-1]["y"] == 2.0, "Coordenadas de trayectoria incorrectas")

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        maps = LocalMapStore(folder)
        first_id = maps.active_map_id
        maps.merge_trajectory([
            {"id": 1, "x": 0.0, "y": 0.0, "phi": 0.0, "update": 1},
            {"id": 2, "x": 1.0, "y": 0.0, "phi": 0.0, "update": 1},
        ], phase=1)
        check(len(maps.snapshot()["points"]) == 2, "No se persistió la trayectoria")

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
        plan.add_schedule({
            "name": "Mañana",
            "days": [0, 2, 4],
            "hour": 9,
            "minute": 0,
            "mode": "vacuum",
            "target": "zones",
            "zone_ids": [zone1["id"]],
        })
        check(len(plan.snapshot(first_id)["zones"]) == 1, "La zona no quedó asociada al primer mapa")

        second_id = next(item["id"] for item in maps.list_maps() if item["id"] != first_id)
        plan.set_active_map(second_id)
        plan.add_zone("Dormitorio", 5, 5, 6, 6)
        check(len(plan.snapshot(second_id)["zones"]) == 1, "La zona del segundo mapa no se guardó")
        check(len(plan.snapshot(first_id)["zones"]) == 1, "Los mapas mezclaron sus zonas")

        backup = folder / "prueba.xvac"
        write_bundle(backup, maps.library_snapshot(), plan.snapshot_all())
        restored = read_bundle(backup)
        check(len(restored["maps"]["maps"]) == 4, "El backup no conserva los cuatro mapas")
        check(restored["cleaning_plan"]["schedules"], "El backup perdió programaciones")

        maps_restored = LocalMapStore(folder / "restored")
        maps_restored.replace_library(restored["maps"])
        check(len(maps_restored.list_maps()) == 4, "La importación no restauró los mapas")

    print("SMOKE TEST OK: imports, EDGE+live, trayectoria, 4 mapas, planes y .xvac")


if __name__ == "__main__":
    main()

import ctypes
import os
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from cleaning_plan import CleaningPlanStore
from robot_plans import (
    start_whole_clean,
    start_zone_clean,
    sync_virtual_walls,
    wait_for_cleaning_cycle,
)
from settings_store import SettingsStore
from xiaomi_e10 import XiaomiE10

APP_FOLDER = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
LOG_PATH = APP_FOLDER / "scheduler.log"


def log(message):
    try:
        APP_FOLDER.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def acquire_single_instance():
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\AspiradoraXiaomiScheduler")
    if not handle:
        return False
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return False
    acquire_single_instance._handle = handle
    return True


def schedule_due(schedule, now):
    if not schedule.get("enabled", True):
        return False, None
    days = {int(x) for x in schedule.get("days", [])}
    if now.weekday() not in days:
        return False, None
    try:
        hour = int(schedule.get("hour", 0))
        minute = int(schedule.get("minute", 0))
    except Exception:
        return False, None
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = now - scheduled
    if timedelta(0) <= delta <= timedelta(minutes=20):
        return True, scheduled.strftime("%Y-%m-%dT%H:%M")
    return False, None


def connect_robot():
    settings = SettingsStore().load()
    ip = str(settings.get("ip", "")).strip()
    token = str(settings.get("token", "")).strip()
    if not ip or not token:
        raise RuntimeError("No hay IP/token guardados para ejecutar la programación.")
    vacuum = XiaomiE10(ip, token)
    vacuum.info()
    return vacuum


def execute_schedule(schedule, plan):
    vacuum = connect_robot()
    sync_virtual_walls(vacuum, plan)

    mode = str(schedule.get("mode", "vacuum"))
    passes = ["vacuum", "mop"] if mode == "vacuum_then_mop" else [mode]
    suction = int(schedule.get("suction", 1) or 1)
    water = int(schedule.get("water", 1) or 1)
    target = str(schedule.get("target", "all"))

    zones_by_id = {z.get("id"): z for z in plan.get("zones", [])}
    chosen_zones = [zones_by_id[zid] for zid in schedule.get("zone_ids", []) if zid in zones_by_id]
    if target == "zones" and not chosen_zones:
        raise RuntimeError("La programación no tiene zonas válidas seleccionadas.")

    for clean_mode in passes:
        if target == "all":
            start_whole_clean(vacuum, clean_mode, suction, water)
            wait_for_cleaning_cycle(vacuum)
        else:
            for zone in chosen_zones:
                start_zone_clean(vacuum, zone, plan, clean_mode, suction, water)
                wait_for_cleaning_cycle(vacuum)
                time.sleep(1.2)


def main():
    if not acquire_single_instance():
        return

    store = CleaningPlanStore(APP_FOLDER)
    log("Programador iniciado.")

    while True:
        try:
            now = datetime.now()
            all_plan = store.snapshot_all()
            schedules = list(all_plan.get("schedules", []) or [])
            last_runs = dict(all_plan.get("last_runs", {}) or {})

            for schedule in schedules:
                due, run_key = schedule_due(schedule, now)
                if not due:
                    continue
                schedule_id = str(schedule.get("id", ""))
                if not schedule_id:
                    continue
                previous = last_runs.get(schedule_id) or {}
                if previous.get("key") == run_key:
                    continue

                name = schedule.get("name") or "Programación"
                map_id = str(schedule.get("map_id") or all_plan.get("active_map_id") or "legacy")
                store.mark_run(schedule_id, run_key, "started")
                log(f"Ejecutando {name} ({schedule_id}) en mapa {map_id}")
                try:
                    # Releemos el mapa específico justo antes de limpiar.
                    fresh_plan = store.snapshot(map_id)
                    execute_schedule(schedule, fresh_plan)
                    store.mark_run(schedule_id, run_key, "success")
                    log(f"Completada {name}")
                except Exception as exc:
                    store.mark_run(schedule_id, run_key, "error: " + str(exc)[:180])
                    log(f"ERROR en {name}: {traceback.format_exc()}")

        except Exception:
            log("ERROR general: " + traceback.format_exc())

        time.sleep(20)


if __name__ == "__main__":
    main()

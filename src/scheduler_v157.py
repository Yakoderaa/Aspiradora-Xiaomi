import ctypes
import os
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from cleaning_plan import CleaningPlanStore
from local_mapping import LocalMapStore
from native_start_core import NativeStartCore
from robot_plans import local_rect_to_device
from route_learning_v157 import RouteLearningStoreV157, TrajectorySamplerV157
from settings_store import SettingsStore
from target_geometry_v157 import room_local_rects
from targeted_v157 import TargetedRunnerV157
from whole_home_v157 import WholeHomeRunnerV157
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
    handle = kernel32.CreateMutexW(None, False, "Local\\AspiradoraXiaomiSchedulerV157")
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
    if timedelta(0) <= delta <= timedelta(minutes=15):
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


def rooms_for_map(map_id):
    library = LocalMapStore(APP_FOLDER).library_snapshot()
    for item in list(library.get("maps") or []):
        if str(item.get("id")) == str(map_id):
            return list(item.get("rooms") or [])
    return []


def run_whole(vacuum, source):
    core = NativeStartCore(vacuum, source=source)
    before = core._read()
    sampler = TrajectorySamplerV157(
        vacuum,
        sample_m=0.25,
        prestart_robot=before.get("robot"),
    )
    diag = WholeHomeRunnerV157(core, source=source).run(
        on_state=sampler.note_state,
    )
    learned = False
    if (
        not diag.get("error")
        and diag.get("finish_reason") in ("dock", "dock_requested")
    ):
        learned, _stats = RouteLearningStoreV157(APP_FOLDER).merge_primary(
            sampler.points,
            source=source,
        )
    diag["learning_primary"] = bool(learned)
    diag["learned_points"] = len(sampler.points)
    return diag


def run_target(vacuum, rects, schedule, learn_key, label, source):
    plan_store = CleaningPlanStore(APP_FOLDER)
    plan = plan_store.snapshot(schedule.get("map_id"))
    raw = [local_rect_to_device(rect, plan) for rect in list(rects or [])]
    core = NativeStartCore(vacuum, source=source)
    before = core._read()
    sampler = TrajectorySamplerV157(
        vacuum,
        sample_m=0.20,
        prestart_robot=before.get("robot"),
    )
    mode = str(schedule.get("mode", "vacuum"))
    passes = ["vacuum", "mop"] if mode == "vacuum_then_mop" else [mode]
    last = {}
    for clean_mode in passes:
        last = TargetedRunnerV157(core, source=source).run(
            raw,
            mode=clean_mode,
            suction=int(schedule.get("suction", 2) or 2),
            water=int(schedule.get("water", 0) or 0),
            on_state=sampler.note_state,
        )
        if last.get("error"):
            break
    if not last.get("error"):
        learned, _stats = RouteLearningStoreV157(APP_FOLDER).merge_target(
            learn_key,
            sampler.points,
            label=label,
            source=source,
        )
        last["learning_secondary"] = bool(learned)
    last["learned_points"] = len(sampler.points)
    return last


def execute_schedule(schedule, plan):
    vacuum = connect_robot()
    target = str(schedule.get("target", "all"))
    source = "scheduler-v157"

    # La vivienda programada usa EXACTAMENTE el mismo runner 2/1 que la GUI.
    if target == "all":
        return run_whole(vacuum, source)

    if target == "rooms":
        map_id = str(schedule.get("map_id") or plan.get("active_map_id") or "legacy")
        by_id = {
            str(room.get("id")): room
            for room in rooms_for_map(map_id)
        }
        selected = [
            by_id[str(room_id)]
            for room_id in schedule.get("room_ids", [])
            if str(room_id) in by_id
        ]
        if not selected:
            raise RuntimeError("La programación no tiene habitaciones válidas.")

        rects = []
        names = []
        for room in selected:
            rects.extend(
                room_local_rects(
                    room,
                    no_go=plan.get("no_go") or [],
                )
            )
            names.append(str(room.get("name") or "Habitación"))
        return run_target(
            vacuum,
            rects,
            schedule,
            "rooms:" + ",".join(sorted(str(r.get("id")) for r in selected)),
            "Habitaciones: " + ", ".join(names),
            source,
        )

    zones_by_id = {
        str(zone.get("id")): zone
        for zone in plan.get("zones", [])
        if isinstance(zone, dict)
    }
    selected = [
        zones_by_id[str(zone_id)]
        for zone_id in schedule.get("zone_ids", [])
        if str(zone_id) in zones_by_id
    ]
    if not selected:
        raise RuntimeError("La programación no tiene zonas válidas.")
    return run_target(
        vacuum,
        selected,
        schedule,
        "zones:" + ",".join(sorted(str(z.get("id")) for z in selected)),
        "Zonas programadas",
        source,
    )


def main():
    import sys
    if "--smoke-test" in sys.argv:
        # El smoke de empaquetado sólo valida imports/arranque. No conecta,
        # no crea timers y no ejecuta ninguna limpieza.
        return 0

    if not acquire_single_instance():
        return 0

    store = CleaningPlanStore(APP_FOLDER)
    log("Programador V157 iniciado · ciclo liviano 60 s.")

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

                name = str(schedule.get("name") or "Programación")
                map_id = str(
                    schedule.get("map_id")
                    or all_plan.get("active_map_id")
                    or "legacy"
                )
                store.mark_run(schedule_id, run_key, "started")
                log(f"Ejecutando {name} ({schedule_id}) · target={schedule.get('target','all')}")
                try:
                    fresh_plan = store.snapshot(map_id)
                    diag = execute_schedule(schedule, fresh_plan)
                    if diag.get("error"):
                        raise RuntimeError(str(diag.get("error")))
                    store.mark_run(schedule_id, run_key, "success")
                    log(f"Completada {name} · {diag.get('finish_reason','ok')}")
                except Exception as exc:
                    store.mark_run(
                        schedule_id,
                        run_key,
                        "error: " + str(exc)[:180],
                    )
                    log(f"ERROR {name}: {traceback.format_exc()}")

        except Exception:
            log("ERROR general: " + traceback.format_exc())

        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())

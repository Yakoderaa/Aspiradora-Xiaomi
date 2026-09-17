import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "aspiradora-xiaomi-backup"
VERSION = 1


def make_payload(maps_library, cleaning_plan):
    return {
        "format": FORMAT,
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "maps": maps_library,
        "cleaning_plan": cleaning_plan,
    }


def write_bundle(path, maps_library, cleaning_plan):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = make_payload(maps_library, cleaning_plan)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read_bundle(path):
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("El archivo no es un respaldo válido de Aspiradora Xiaomi.")
    if int(payload.get("version", 0) or 0) > VERSION:
        raise ValueError("El respaldo fue creado por una versión más nueva de la aplicación.")
    maps = payload.get("maps")
    plan = payload.get("cleaning_plan")
    if not isinstance(maps, dict) or not isinstance(maps.get("maps"), list):
        raise ValueError("El respaldo no contiene mapas válidos.")
    if not isinstance(plan, dict):
        raise ValueError("El respaldo no contiene programaciones válidas.")
    if not 1 <= len(maps.get("maps") or []) <= 4:
        raise ValueError("El respaldo debe contener entre uno y cuatro mapas.")
    return payload


def auto_backup(app_folder, maps_library, cleaning_plan, prefix="automatico", keep=8):
    folder = Path(app_folder) / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"{prefix}-{stamp}.xvac"
    write_bundle(target, maps_library, cleaning_plan)
    files = sorted(folder.glob("*.xvac"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max(1, int(keep)):]:
        try:
            old.unlink()
        except Exception:
            pass
    return target

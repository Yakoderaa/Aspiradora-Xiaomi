import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class CleaningPlanStore:
    """Zonas, bloqueos y programaciones compartidas entre la UI y el agente."""

    def __init__(self, app_folder: Path):
        self.folder = Path(app_folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "cleaning_plan.json"
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(self._defaults())

    @staticmethod
    def _defaults():
        return {
            "version": 1,
            "zones": [],
            "no_go": [],
            "points": [],
            "schedules": [],
            "device_origin": None,
            "last_runs": {},
            "updated_at": None,
        }

    def _read(self):
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Formato inválido")
            except Exception:
                data = self._defaults()
            defaults = self._defaults()
            defaults.update(data)
            return defaults

    def _write(self, data):
        with self._lock:
            data = dict(data)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def snapshot(self):
        return self._read()

    @staticmethod
    def _rect(x0, y0, x1, y1):
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        return {"x0": left, "y0": bottom, "x1": right, "y1": top}

    def add_zone(self, name, x0, y0, x1, y1):
        data = self._read()
        zone = {
            "id": uuid.uuid4().hex[:10],
            "name": (str(name).strip() or "Zona"),
            **self._rect(x0, y0, x1, y1),
        }
        data["zones"].append(zone)
        self._write(data)
        return zone

    def delete_zone(self, zone_id):
        data = self._read()
        data["zones"] = [z for z in data["zones"] if z.get("id") != zone_id]
        for schedule in data["schedules"]:
            schedule["zone_ids"] = [z for z in schedule.get("zone_ids", []) if z != zone_id]
        self._write(data)

    def add_no_go(self, name, x0, y0, x1, y1):
        data = self._read()
        wall = {
            "id": uuid.uuid4().hex[:10],
            "name": (str(name).strip() or "Zona bloqueada"),
            **self._rect(x0, y0, x1, y1),
        }
        data["no_go"].append(wall)
        self._write(data)
        return wall

    def delete_no_go(self, wall_id):
        data = self._read()
        data["no_go"] = [w for w in data["no_go"] if w.get("id") != wall_id]
        self._write(data)

    def add_point(self, name, x, y):
        data = self._read()
        point = {
            "id": uuid.uuid4().hex[:10],
            "name": (str(name).strip() or "Punto"),
            "x": float(x),
            "y": float(y),
        }
        data["points"].append(point)
        self._write(data)
        return point

    def delete_point(self, point_id):
        data = self._read()
        data["points"] = [p for p in data["points"] if p.get("id") != point_id]
        self._write(data)

    def set_device_origin(self, x, y):
        data = self._read()
        data["device_origin"] = {"x": float(x), "y": float(y)}
        self._write(data)

    def add_schedule(self, schedule):
        data = self._read()
        item = dict(schedule)
        item["id"] = uuid.uuid4().hex[:10]
        item.setdefault("enabled", True)
        item.setdefault("zone_ids", [])
        item.setdefault("days", [])
        data["schedules"].append(item)
        self._write(data)
        return item

    def update_schedule(self, schedule_id, updates):
        data = self._read()
        for schedule in data["schedules"]:
            if schedule.get("id") == schedule_id:
                schedule.update(dict(updates))
                break
        self._write(data)

    def delete_schedule(self, schedule_id):
        data = self._read()
        data["schedules"] = [s for s in data["schedules"] if s.get("id") != schedule_id]
        data["last_runs"].pop(schedule_id, None)
        self._write(data)

    def mark_run(self, schedule_id, run_key, result="started"):
        data = self._read()
        data["last_runs"][str(schedule_id)] = {
            "key": str(run_key),
            "result": str(result),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(data)

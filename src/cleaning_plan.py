import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class CleaningPlanStore:
    """Zonas, bloqueos, puntos y programaciones por mapa.

    snapshot() mantiene la API anterior y devuelve solamente el mapa activo.
    snapshot_all() se usa para backups y para el agente de programaciones.
    """

    VERSION = 3

    def __init__(self, app_folder: Path):
        self.folder = Path(app_folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "cleaning_plan.json"
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(self._defaults())
        else:
            # Fuerza una lectura/escritura de migración una sola vez.
            self._write(self._read())

    @staticmethod
    def _defaults():
        return {
            "version": CleaningPlanStore.VERSION,
            "active_map_id": "legacy",
            "zones": [],
            "no_go": [],
            "points": [],
            "schedules": [],
            "device_origins": {},
            "virtual_walls_managed_maps": {},
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

            # Migraciones transparentes.
            version = int(data.get("version", 1) or 1)
            if version < 2:
                active = str(data.get("active_map_id") or "legacy")
                for key in ("zones", "no_go", "points", "schedules"):
                    for item in data.get(key, []) or []:
                        if isinstance(item, dict):
                            item.setdefault("map_id", active)
                origin = data.get("device_origin")
                origins = dict(data.get("device_origins") or {})
                if isinstance(origin, dict):
                    origins.setdefault(active, origin)
                managed = dict(data.get("virtual_walls_managed_maps") or {})
                if "virtual_walls_managed" in data:
                    managed.setdefault(active, bool(data.get("virtual_walls_managed")))
                data["device_origins"] = origins
                data["virtual_walls_managed_maps"] = managed
                data["active_map_id"] = active
                data.pop("device_origin", None)
                data.pop("virtual_walls_managed", None)

            if version < 3:
                # V110: las zonas pasan a pertenecer a una habitación concreta.
                # La asignación geométrica de elementos legacy se hace desde la
                # app, porque CleaningPlanStore no conoce los rectángulos de
                # LocalMapStore. Mientras tanto quedan marcados como huérfanos.
                for key in ("zones", "no_go"):
                    for item in data.get(key, []) or []:
                        if isinstance(item, dict):
                            item.setdefault("room_id", None)
                data["version"] = 3

            defaults = self._defaults()
            defaults.update(data)
            defaults["version"] = self.VERSION
            defaults["active_map_id"] = str(defaults.get("active_map_id") or "legacy")
            for key in ("zones", "no_go", "points", "schedules"):
                defaults[key] = list(defaults.get(key) or [])
                for item in defaults[key]:
                    if isinstance(item, dict):
                        item.setdefault("map_id", defaults["active_map_id"])
                        if key in ("zones", "no_go"):
                            item.setdefault("room_id", None)
            defaults["device_origins"] = dict(defaults.get("device_origins") or {})
            defaults["virtual_walls_managed_maps"] = dict(defaults.get("virtual_walls_managed_maps") or {})
            defaults["last_runs"] = dict(defaults.get("last_runs") or {})
            return defaults

    def _write(self, data):
        with self._lock:
            data = dict(data)
            data["version"] = self.VERSION
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def active_map_id(self):
        return str(self._read().get("active_map_id") or "legacy")

    def set_active_map(self, map_id):
        data = self._read()
        data["active_map_id"] = str(map_id)
        self._write(data)

    def snapshot_all(self):
        return self._read()

    def snapshot(self, map_id=None):
        data = self._read()
        map_id = str(map_id or data.get("active_map_id") or "legacy")
        schedules = [dict(x) for x in data.get("schedules", []) if str(x.get("map_id")) == map_id]
        schedule_ids = {str(x.get("id")) for x in schedules}
        return {
            "version": self.VERSION,
            "active_map_id": map_id,
            "zones": [dict(x) for x in data.get("zones", []) if str(x.get("map_id")) == map_id],
            "no_go": [dict(x) for x in data.get("no_go", []) if str(x.get("map_id")) == map_id],
            "points": [dict(x) for x in data.get("points", []) if str(x.get("map_id")) == map_id],
            "schedules": schedules,
            "device_origin": data.get("device_origins", {}).get(map_id),
            "virtual_walls_managed": bool(data.get("virtual_walls_managed_maps", {}).get(map_id, False)),
            "last_runs": {k: v for k, v in data.get("last_runs", {}).items() if str(k) in schedule_ids},
            "updated_at": data.get("updated_at"),
        }

    def replace_all(self, imported):
        if not isinstance(imported, dict):
            raise ValueError("El backup de zonas y programaciones no es válido.")
        data = self._defaults()
        data.update(imported)
        data["version"] = self.VERSION
        self._write(data)

    def delete_map_data(self, map_id):
        map_id = str(map_id)
        data = self._read()
        removed_schedule_ids = {
            str(item.get("id")) for item in data.get("schedules", []) if str(item.get("map_id")) == map_id
        }
        for key in ("zones", "no_go", "points", "schedules"):
            data[key] = [item for item in data.get(key, []) if str(item.get("map_id")) != map_id]
        data.get("device_origins", {}).pop(map_id, None)
        data.get("virtual_walls_managed_maps", {}).pop(map_id, None)
        for sid in removed_schedule_ids:
            data.get("last_runs", {}).pop(sid, None)
        if data.get("active_map_id") == map_id:
            data["active_map_id"] = "legacy"
        self._write(data)

    @staticmethod
    def _rect(x0, y0, x1, y1):
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        return {"x0": left, "y0": bottom, "x1": right, "y1": top}

    def add_zone(self, name, x0, y0, x1, y1, room_id=None):
        data = self._read()
        map_id = str(data.get("active_map_id") or "legacy")
        zone = {
            "id": uuid.uuid4().hex[:10],
            "map_id": map_id,
            "room_id": None if room_id is None else str(room_id),
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

    def add_no_go(self, name, x0, y0, x1, y1, room_id=None):
        data = self._read()
        map_id = str(data.get("active_map_id") or "legacy")
        wall = {
            "id": uuid.uuid4().hex[:10],
            "map_id": map_id,
            "room_id": None if room_id is None else str(room_id),
            "name": (str(name).strip() or "Zona bloqueada"),
            **self._rect(x0, y0, x1, y1),
        }
        data["no_go"].append(wall)
        data["virtual_walls_managed_maps"][map_id] = True
        self._write(data)
        return wall

    def delete_no_go(self, wall_id):
        data = self._read()
        target = next((w for w in data["no_go"] if w.get("id") == wall_id), None)
        map_id = str((target or {}).get("map_id") or data.get("active_map_id") or "legacy")
        data["no_go"] = [w for w in data["no_go"] if w.get("id") != wall_id]
        # True se conserva para poder enviar explícitamente cero bloqueos.
        data["virtual_walls_managed_maps"][map_id] = True
        self._write(data)

    def set_item_room(self, kind, item_id, room_id):
        """Asocia una zona/bloqueo existente a una habitación."""
        key = "zones" if str(kind) == "zone" else "no_go"
        data = self._read()
        changed = False
        for item in data.get(key, []):
            if str(item.get("id")) == str(item_id):
                item["room_id"] = None if room_id is None else str(room_id)
                changed = True
                break
        if changed:
            self._write(data)
        return changed

    def room_items(self, room_id, map_id=None):
        """Devuelve zonas de limpieza y bloqueos ligados a una habitación."""
        data = self._read()
        map_id = str(map_id or data.get("active_map_id") or "legacy")
        room_id = str(room_id)
        return {
            "zones": [
                dict(item)
                for item in data.get("zones", [])
                if str(item.get("map_id")) == map_id
                and str(item.get("room_id")) == room_id
            ],
            "no_go": [
                dict(item)
                for item in data.get("no_go", [])
                if str(item.get("map_id")) == map_id
                and str(item.get("room_id")) == room_id
            ],
        }

    def delete_room_items(self, room_id, map_id=None):
        """Borra en cascada todo lo asociado a una habitación.

        También elimina las referencias a zonas de limpieza desde las
        programaciones del mismo mapa.
        """
        data = self._read()
        map_id = str(map_id or data.get("active_map_id") or "legacy")
        room_id = str(room_id)

        removed_zone_ids = {
            str(item.get("id"))
            for item in data.get("zones", [])
            if str(item.get("map_id")) == map_id
            and str(item.get("room_id")) == room_id
        }
        removed_no_go_ids = {
            str(item.get("id"))
            for item in data.get("no_go", [])
            if str(item.get("map_id")) == map_id
            and str(item.get("room_id")) == room_id
        }

        data["zones"] = [
            item for item in data.get("zones", [])
            if not (
                str(item.get("map_id")) == map_id
                and str(item.get("room_id")) == room_id
            )
        ]
        data["no_go"] = [
            item for item in data.get("no_go", [])
            if not (
                str(item.get("map_id")) == map_id
                and str(item.get("room_id")) == room_id
            )
        ]

        if removed_zone_ids:
            for schedule in data.get("schedules", []):
                if str(schedule.get("map_id")) != map_id:
                    continue
                schedule["zone_ids"] = [
                    zone_id
                    for zone_id in schedule.get("zone_ids", [])
                    if str(zone_id) not in removed_zone_ids
                ]

        if removed_no_go_ids:
            data["virtual_walls_managed_maps"][map_id] = True

        self._write(data)
        return {
            "zones": len(removed_zone_ids),
            "no_go": len(removed_no_go_ids),
        }

    def add_point(self, name, x, y):
        data = self._read()
        point = {
            "id": uuid.uuid4().hex[:10],
            "map_id": str(data.get("active_map_id") or "legacy"),
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

    def set_device_origin(self, x, y, map_id=None):
        data = self._read()
        map_id = str(map_id or data.get("active_map_id") or "legacy")
        data["device_origins"][map_id] = {"x": float(x), "y": float(y)}
        self._write(data)

    def add_schedule(self, schedule):
        data = self._read()
        item = dict(schedule)
        item["id"] = uuid.uuid4().hex[:10]
        item.setdefault("map_id", str(data.get("active_map_id") or "legacy"))
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
        data["last_runs"].pop(str(schedule_id), None)
        self._write(data)

    def mark_run(self, schedule_id, run_key, result="started"):
        data = self._read()
        data["last_runs"][str(schedule_id)] = {
            "key": str(run_key),
            "result": str(result),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(data)

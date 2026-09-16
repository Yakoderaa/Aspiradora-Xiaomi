import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LocalMapStore:
    """Mapa persistente generado en la PC a partir de la telemetría LAN del E10."""

    def __init__(self, app_folder: Path):
        self.path = Path(app_folder) / "local_map.json"
        self._lock = threading.RLock()
        self._data = self._defaults()
        self._load()

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "version": 1,
            "name": "Mi casa",
            "created_at": None,
            "updated_at": None,
            "points": [],
            "robot": None,
            "charging_base": None,
            "rooms": [],
        }

    def _load(self):
        with self._lock:
            if not self.path.exists():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._data.update(data)
            except Exception:
                self._data = self._defaults()

    def _save_locked(self):
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def clear_map(self, keep_rooms: bool = False):
        with self._lock:
            rooms = self._data.get("rooms", []) if keep_rooms else []
            self._data = self._defaults()
            self._data["created_at"] = datetime.now(timezone.utc).isoformat()
            self._data["rooms"] = rooms
            self._save_locked()

    def merge_trajectory(self, points: list[dict[str, Any]]) -> int:
        if not points:
            return 0
        with self._lock:
            current = self._data.setdefault("points", [])
            by_id = {int(p.get("id", i)): p for i, p in enumerate(current)}
            before = len(by_id)
            for i, point in enumerate(points):
                try:
                    pid = int(point.get("id", i))
                    x = float(point["x"])
                    y = float(point["y"])
                    phi = float(point.get("phi", 0) or 0)
                    update = int(point.get("update", 1) or 0)
                except Exception:
                    continue
                by_id[pid] = {"id": pid, "x": x, "y": y, "phi": phi, "update": update}
            self._data["points"] = [by_id[key] for key in sorted(by_id)]
            if not self._data.get("created_at"):
                self._data["created_at"] = datetime.now(timezone.utc).isoformat()
            self._save_locked()
            return len(by_id) - before

    def set_robot(self, point: dict[str, Any] | None):
        if not point:
            return
        with self._lock:
            self._data["robot"] = {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "angle": float(point.get("angle", 0) or 0),
            }
            self._save_locked()

    def set_charging_base(self, point: dict[str, Any] | None):
        if not point:
            return
        with self._lock:
            self._data["charging_base"] = {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "angle": float(point.get("angle", 0) or 0),
            }
            self._save_locked()

    def add_room(self, name: str, x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        with self._lock:
            rooms = self._data.setdefault("rooms", [])
            next_id = max([int(r.get("id", 0)) for r in rooms] + [0]) + 1
            room = {
                "id": next_id,
                "name": name.strip() or f"Habitación {next_id}",
                "x0": left,
                "y0": bottom,
                "x1": right,
                "y1": top,
            }
            rooms.append(room)
            self._save_locked()
            return dict(room)

    def delete_room(self, room_id: int):
        with self._lock:
            room_id = int(room_id)
            self._data["rooms"] = [r for r in self._data.get("rooms", []) if int(r.get("id", -1)) != room_id]
            self._save_locked()

    def rename_room(self, room_id: int, name: str):
        with self._lock:
            for room in self._data.get("rooms", []):
                if int(room.get("id", -1)) == int(room_id):
                    room["name"] = name.strip() or room.get("name") or f"Habitación {room_id}"
                    break
            self._save_locked()

import json
import math
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LocalMapStore:
    """Biblioteca persistente de mapas locales.

    Mantiene la misma interfaz histórica (snapshot/merge_trajectory/etc.) sobre el
    mapa activo, pero guarda hasta cuatro mapas independientes. Si existe el viejo
    local_map.json se migra automáticamente sin modificarlo.
    """

    MAX_MAPS = 4
    LIBRARY_VERSION = 6

    def __init__(self, app_folder: Path):
        self.folder = Path(app_folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "maps.json"
        self.legacy_path = self.folder / "local_map.json"
        self._lock = threading.RLock()
        self._data = self._library_defaults()
        self._load()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_id():
        return uuid.uuid4().hex[:10]

    @classmethod
    def _blank_map(cls, name="Mi casa", map_id=None) -> dict[str, Any]:
        return {
            "id": str(map_id or cls._new_id()),
            "name": str(name).strip() or "Mapa",
            "created_at": cls._now(),
            "updated_at": None,
            "points": [],
            "mapped_walls": [],
            "robot": None,
            "charging_base": None,
            "rooms": [],
            "native_grid": None,
        }

    @classmethod
    def _library_defaults(cls):
        first = cls._blank_map("Mi casa")
        return {
            "version": cls.LIBRARY_VERSION,
            "active_map_id": first["id"],
            "maps": [first],
            "updated_at": cls._now(),
        }

    @classmethod
    def _normalize_wall(cls, wall):
        if not isinstance(wall, dict):
            return None
        clean = []
        for point in wall.get("points", []) or []:
            try:
                x = float(point["x"])
                y = float(point["y"])
                if math.isfinite(x) and math.isfinite(y):
                    clean.append({"x": x, "y": y})
            except Exception:
                continue
        if len(clean) < 2:
            return None
        return {"points": clean, "estimated": bool(wall.get("estimated", True))}

    @classmethod
    def _normalize_native_grid(cls, grid):
        if grid is None:
            return None
        if not isinstance(grid, dict):
            return None
        try:
            side = int(grid.get("side", 0) or 0)
            resolution = float(grid.get("resolution", 0.0) or 0.0)
            base_cell = list(grid.get("base_cell") or [])
            cells = list(grid.get("cells") or [])
        except Exception:
            return None
        if side <= 0 or side > 512:
            return None
        if not math.isfinite(resolution) or resolution <= 0.0 or resolution > 2.0:
            return None
        if len(base_cell) < 2 or len(cells) != side * side:
            return None
        try:
            bx = float(base_cell[0])
            by = float(base_cell[1])
        except Exception:
            return None
        if not (math.isfinite(bx) and math.isfinite(by)):
            return None

        normalized_cells = []
        for value in cells:
            try:
                cell = int(value)
            except Exception:
                return None
            if cell < 0 or cell > 3:
                return None
            normalized_cells.append(cell)

        result = {
            "side": side,
            "resolution": resolution,
            "base_cell": [bx, by],
            "cells": normalized_cells,
            "source": str(grid.get("source") or "xiaomi-grid"),
            "blob_sha12": str(grid.get("blob_sha12") or ""),
            "timestamp": grid.get("timestamp"),
        }
        metrics = grid.get("metrics")
        if isinstance(metrics, dict):
            result["metrics"] = dict(metrics)
        return result

    @classmethod
    def _normalize_map(cls, source, fallback_name="Mapa"):
        source = dict(source or {})
        result = cls._blank_map(source.get("name") or fallback_name, source.get("id") or cls._new_id())
        result["created_at"] = source.get("created_at") or result["created_at"]
        result["updated_at"] = source.get("updated_at")
        result["robot"] = source.get("robot") if isinstance(source.get("robot"), dict) else None
        result["charging_base"] = source.get("charging_base") if isinstance(source.get("charging_base"), dict) else None
        result["rooms"] = []
        for room in list(source.get("rooms") or []):
            if not isinstance(room, dict):
                continue
            clone = dict(room)
            polygon = []
            for point in list(clone.get("polygon") or []):
                try:
                    x = float(point["x"])
                    y = float(point["y"])
                    if math.isfinite(x) and math.isfinite(y):
                        polygon.append({"x": x, "y": y})
                except Exception:
                    continue
            if len(polygon) >= 3:
                clone["shape"] = "polygon"
                clone["polygon"] = polygon
                xs = [point["x"] for point in polygon]
                ys = [point["y"] for point in polygon]
                clone["x0"] = min(xs)
                clone["y0"] = min(ys)
                clone["x1"] = max(xs)
                clone["y1"] = max(ys)
            result["rooms"].append(clone)
        result["points"] = list(source.get("points") or [])
        result["native_grid"] = cls._normalize_native_grid(source.get("native_grid"))
        for point in result["points"]:
            if isinstance(point, dict):
                point.setdefault("phase", 0)
        result["mapped_walls"] = []
        for wall in source.get("mapped_walls", []) or []:
            normalized = cls._normalize_wall(wall)
            if normalized:
                result["mapped_walls"].append(normalized)
        return result

    def _load(self):
        with self._lock:
            loaded = None
            if self.path.exists():
                try:
                    candidate = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(candidate, dict) and isinstance(candidate.get("maps"), list):
                        loaded = candidate
                except Exception:
                    loaded = None

            if loaded is None and self.legacy_path.exists():
                try:
                    legacy = json.loads(self.legacy_path.read_text(encoding="utf-8"))
                    if isinstance(legacy, dict):
                        migrated = self._normalize_map(legacy, legacy.get("name") or "Mi casa")
                        loaded = {
                            "version": self.LIBRARY_VERSION,
                            "active_map_id": migrated["id"],
                            "maps": [migrated],
                            "updated_at": self._now(),
                        }
                except Exception:
                    loaded = None

            if loaded is None:
                loaded = self._library_defaults()

            maps = []
            seen = set()
            for index, item in enumerate(list(loaded.get("maps") or [])[: self.MAX_MAPS], start=1):
                normalized = self._normalize_map(item, f"Mapa {index}")
                if normalized["id"] in seen:
                    normalized["id"] = self._new_id()
                seen.add(normalized["id"])
                maps.append(normalized)
            if not maps:
                maps = [self._blank_map("Mi casa")]

            active = str(loaded.get("active_map_id") or "")
            if active not in {item["id"] for item in maps}:
                active = maps[0]["id"]

            self._data = {
                "version": self.LIBRARY_VERSION,
                "active_map_id": active,
                "maps": maps,
                "updated_at": loaded.get("updated_at") or self._now(),
            }
            self._save_locked()

    def _save_locked(self):
        self._data["version"] = self.LIBRARY_VERSION
        self._data["updated_at"] = self._now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _active_locked(self):
        active_id = self._data.get("active_map_id")
        for item in self._data.get("maps", []):
            if item.get("id") == active_id:
                return item
        first = self._data["maps"][0]
        self._data["active_map_id"] = first["id"]
        return first

    @property
    def active_map_id(self):
        with self._lock:
            return str(self._active_locked()["id"])

    def list_maps(self):
        with self._lock:
            active = self._data.get("active_map_id")
            result = []
            for item in self._data.get("maps", []):
                result.append({
                    "id": item["id"],
                    "name": item.get("name") or "Mapa",
                    "active": item["id"] == active,
                    "points": len(item.get("points") or []),
                    "walls": len(item.get("mapped_walls") or []),
                    "rooms": len(item.get("rooms") or []),
                    "native_grid": bool(item.get("native_grid")),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                })
            return json.loads(json.dumps(result))

    def select_map(self, map_id: str):
        map_id = str(map_id)
        with self._lock:
            if map_id not in {item.get("id") for item in self._data.get("maps", [])}:
                raise KeyError("El mapa seleccionado no existe.")
            self._data["active_map_id"] = map_id
            self._save_locked()
            return self.snapshot()

    def create_map(self, name="Mapa"):
        with self._lock:
            if len(self._data.get("maps", [])) >= self.MAX_MAPS:
                raise RuntimeError("Ya hay cuatro mapas guardados. Eliminá uno para crear otro.")
            item = self._blank_map(name or f"Mapa {len(self._data['maps']) + 1}")
            self._data["maps"].append(item)
            self._data["active_map_id"] = item["id"]
            self._save_locked()
            return json.loads(json.dumps(item))

    def rename_map(self, map_id: str, name: str):
        with self._lock:
            for item in self._data.get("maps", []):
                if item.get("id") == str(map_id):
                    item["name"] = str(name).strip() or item.get("name") or "Mapa"
                    item["updated_at"] = self._now()
                    self._save_locked()
                    return
            raise KeyError("El mapa no existe.")

    def delete_map(self, map_id: str):
        with self._lock:
            maps = self._data.get("maps", [])
            if len(maps) <= 1:
                raise RuntimeError("Debe quedar al menos un mapa en la aplicación.")
            before = len(maps)
            maps[:] = [item for item in maps if item.get("id") != str(map_id)]
            if len(maps) == before:
                raise KeyError("El mapa no existe.")
            if self._data.get("active_map_id") == str(map_id):
                self._data["active_map_id"] = maps[0]["id"]
            self._save_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._active_locked()))

    def library_snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self._data))

    def replace_library(self, library):
        if not isinstance(library, dict) or not isinstance(library.get("maps"), list):
            raise ValueError("El archivo no contiene una biblioteca de mapas válida.")
        if not library.get("maps"):
            raise ValueError("El archivo no contiene ningún mapa.")
        if len(library["maps"]) > self.MAX_MAPS:
            raise ValueError("El archivo contiene más de cuatro mapas.")
        with self._lock:
            maps = [self._normalize_map(item, f"Mapa {i + 1}") for i, item in enumerate(library["maps"])]
            ids = set()
            for item in maps:
                if item["id"] in ids:
                    item["id"] = self._new_id()
                ids.add(item["id"])
            active = str(library.get("active_map_id") or "")
            if active not in ids:
                active = maps[0]["id"]
            self._data = {
                "version": self.LIBRARY_VERSION,
                "active_map_id": active,
                "maps": maps,
                "updated_at": self._now(),
            }
            self._save_locked()

    def clear_map(self, keep_rooms: bool = False):
        with self._lock:
            item = self._active_locked()
            rooms = item.get("rooms", []) if keep_rooms else []
            name = item.get("name") or "Mapa"
            map_id = item["id"]
            created_at = self._now()
            replacement = self._blank_map(name, map_id)
            replacement["created_at"] = created_at
            replacement["rooms"] = rooms
            index = self._data["maps"].index(item)
            self._data["maps"][index] = replacement
            self._save_locked()

    def _touch_active_locked(self):
        self._active_locked()["updated_at"] = self._now()

    def merge_trajectory(self, points: list[dict[str, Any]], phase: int = 0) -> int:
        if not points:
            return 0
        phase = int(phase or 0)
        with self._lock:
            item = self._active_locked()
            current = item.setdefault("points", [])
            by_id = {}
            for i, point in enumerate(current):
                p_phase = int(point.get("phase", 0) or 0)
                p_id = int(point.get("id", i))
                by_id[(p_phase, p_id)] = point
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
                by_id[(phase, pid)] = {
                    "id": pid,
                    "phase": phase,
                    "x": x,
                    "y": y,
                    "phi": phi,
                    "update": update,
                }

            item["points"] = [by_id[key] for key in sorted(by_id, key=lambda value: (value[0], value[1]))]
            if not item.get("created_at"):
                item["created_at"] = self._now()
            self._touch_active_locked()
            self._save_locked()
            return len(by_id) - before

    def set_native_grid(self, grid):
        normalized = self._normalize_native_grid(grid)
        if grid is not None and normalized is None:
            raise ValueError("La geometría nativa del mapa no es válida.")
        with self._lock:
            item = self._active_locked()
            item["native_grid"] = normalized
            self._touch_active_locked()
            self._save_locked()

    def set_mapped_walls(self, walls):
        clean = []
        for wall in walls or []:
            normalized = self._normalize_wall(wall)
            if normalized:
                clean.append(normalized)
        with self._lock:
            item = self._active_locked()
            item["mapped_walls"] = clean
            self._touch_active_locked()
            self._save_locked()

    def set_robot(self, point: dict[str, Any] | None):
        if not point:
            return
        with self._lock:
            item = self._active_locked()
            item["robot"] = {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "angle": float(point.get("angle", 0) or 0),
            }
            self._touch_active_locked()
            self._save_locked()

    def set_charging_base(self, point: dict[str, Any] | None):
        if not point:
            return
        with self._lock:
            item = self._active_locked()
            item["charging_base"] = {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "angle": float(point.get("angle", 0) or 0),
            }
            self._touch_active_locked()
            self._save_locked()

    def add_room(self, name: str, x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        with self._lock:
            item = self._active_locked()
            rooms = item.setdefault("rooms", [])
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
            self._touch_active_locked()
            self._save_locked()
            return dict(room)

    def add_polygon_room(self, name: str, points) -> dict[str, Any]:
        polygon = []
        for point in list(points or []):
            try:
                if isinstance(point, dict):
                    x = float(point["x"])
                    y = float(point["y"])
                else:
                    x = float(point[0])
                    y = float(point[1])
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                polygon.append({"x": x, "y": y})

        if len(polygon) < 3:
            raise ValueError("Una habitación por puntos necesita al menos 3 vértices.")

        xs = [point["x"] for point in polygon]
        ys = [point["y"] for point in polygon]
        with self._lock:
            item = self._active_locked()
            rooms = item.setdefault("rooms", [])
            next_id = max([int(r.get("id", 0)) for r in rooms] + [0]) + 1
            room = {
                "id": next_id,
                "name": str(name).strip() or f"Habitación {next_id}",
                "shape": "polygon",
                "polygon": polygon,
                "x0": min(xs),
                "y0": min(ys),
                "x1": max(xs),
                "y1": max(ys),
            }
            rooms.append(room)
            self._touch_active_locked()
            self._save_locked()
            return json.loads(json.dumps(room))

    def delete_room(self, room_id: int):
        with self._lock:
            item = self._active_locked()
            room_id = int(room_id)
            item["rooms"] = [r for r in item.get("rooms", []) if int(r.get("id", -1)) != room_id]
            self._touch_active_locked()
            self._save_locked()

    def rename_room(self, room_id: int, name: str):
        with self._lock:
            item = self._active_locked()
            for room in item.get("rooms", []):
                if int(room.get("id", -1)) == int(room_id):
                    room["name"] = name.strip() or room.get("name") or f"Habitación {room_id}"
                    break
            self._touch_active_locked()
            self._save_locked()

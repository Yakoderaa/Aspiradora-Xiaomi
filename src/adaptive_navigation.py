import json
import math
import threading
from pathlib import Path


class AdaptiveNavigationMemory:
    """Memoria local y persistente de navegación/limpieza por habitación.

    No es un modelo generativo: aprende de resultados observados y conserva
    estrategias que históricamente dieron mejor cobertura con menos fallos.
    """

    VERSION = 1
    STRATEGIES = ("single", "verified_double", "verified_triple")

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "ai_navigation_memory.json"
        self._lock = threading.RLock()
        self._data = {
            "version": self.VERSION,
            "rooms": {},
            "mapping": {"sessions": [], "patterns": {}},
        }
        self._load()

    def _load(self):
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data.update(raw)
            except Exception:
                pass
            self._data.setdefault("rooms", {})
            self._data.setdefault("mapping", {"sessions": [], "patterns": {}})
            self._save()

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def room_key(room):
        room = dict(room or {})
        rid = str(room.get("id") or "").strip()
        if rid:
            return "id:" + rid
        name = str(room.get("name") or "Habitación").strip()
        poly = list(room.get("polygon") or [])
        if poly:
            coords = []
            for p in poly:
                try:
                    coords.append(
                        f"{float(p['x']):.2f},{float(p['y']):.2f}"
                    )
                except Exception:
                    continue
            return "poly:" + name + ":" + "|".join(coords)
        vals = []
        for key in ("x0", "y0", "x1", "y1"):
            try:
                vals.append(f"{float(room.get(key, 0.0)):.2f}")
            except Exception:
                vals.append("0")
        return "rect:" + name + ":" + ",".join(vals)

    @staticmethod
    def room_area(room):
        room = dict(room or {})
        poly = list(room.get("polygon") or [])
        if len(poly) >= 3:
            pts = []
            for p in poly:
                try:
                    pts.append((float(p["x"]), float(p["y"])))
                except Exception:
                    pass
            if len(pts) >= 3:
                area = 0.0
                for i, (x1, y1) in enumerate(pts):
                    x2, y2 = pts[(i + 1) % len(pts)]
                    area += x1 * y2 - x2 * y1
                return max(0.1, abs(area) * 0.5)
        try:
            return max(
                0.1,
                abs(float(room["x1"]) - float(room["x0"]))
                * abs(float(room["y1"]) - float(room["y0"])),
            )
        except Exception:
            return 1.0

    def choose_room_strategy(self, room):
        key = self.room_key(room)
        with self._lock:
            profile = dict(self._data["rooms"].get(key) or {})
        recommended = str(profile.get("recommended") or "")
        if recommended in self.STRATEGIES:
            return recommended
        attempts = list(profile.get("attempts") or [])
        if not attempts:
            return "single"
        best = max(attempts, key=lambda x: float(x.get("score", 0.0) or 0.0))
        if float(best.get("score", 0.0) or 0.0) >= 88.0:
            return str(best.get("strategy") or "single")
        if len(attempts) < 3:
            return "verified_double"
        return "verified_triple"

    def record_room_attempt(self, room, strategy, metrics):
        key = self.room_key(room)
        score = float(metrics.get("score", 0.0) or 0.0)
        with self._lock:
            profile = dict(self._data["rooms"].get(key) or {})
            attempts = list(profile.get("attempts") or [])
            attempts.append({
                "strategy": str(strategy),
                **dict(metrics),
            })
            attempts = attempts[-30:]
            best = max(attempts, key=lambda x: float(x.get("score", 0.0) or 0.0))
            failures = int(profile.get("failures", 0) or 0)
            if not bool(metrics.get("completed", False)):
                failures += 1

            previous = float(profile.get("last_score", score) or score)
            worse = int(profile.get("consecutive_worse", 0) or 0)
            if score + 2.0 < previous:
                worse += 1
            else:
                worse = 0

            if float(best.get("score", 0.0) or 0.0) >= 90.0:
                recommended = str(best.get("strategy") or "single")
            elif score < 72.0:
                recommended = "verified_triple"
            elif score < 86.0:
                recommended = "verified_double"
            else:
                recommended = str(strategy)

            self._data["rooms"][key] = {
                "name": str((room or {}).get("name") or "Habitación"),
                "area_m2": round(self.room_area(room), 3),
                "attempts": attempts,
                "best_score": round(float(best.get("score", 0.0) or 0.0), 2),
                "best_strategy": str(best.get("strategy") or strategy),
                "recommended": recommended,
                "last_score": round(score, 2),
                "failures": failures,
                "consecutive_worse": worse,
            }
            self._save()
            return dict(self._data["rooms"][key])

    def room_profile(self, room):
        key = self.room_key(room)
        with self._lock:
            return json.loads(json.dumps(self._data["rooms"].get(key) or {}))

    def should_retry_room(self, room, score, completed, pass_index):
        profile = self.room_profile(room)
        if not completed:
            return pass_index < 2
        if int(profile.get("consecutive_worse", 0) or 0) >= 2:
            return False
        recommended = str(profile.get("recommended") or "single")
        max_passes = {
            "single": 1,
            "verified_double": 2,
            "verified_triple": 3,
        }.get(recommended, 1)
        if float(score) >= 88.0:
            return False
        return int(pass_index) < max_passes

    def record_mapping_pattern(self, metrics):
        metrics = dict(metrics or {})
        with self._lock:
            sessions = list(self._data["mapping"].get("sessions") or [])
            sessions.append(metrics)
            self._data["mapping"]["sessions"] = sessions[-40:]
            pattern = str(metrics.get("pattern") or "unknown")
            stats = dict(
                (self._data["mapping"].get("patterns") or {}).get(pattern) or {}
            )
            stats["count"] = int(stats.get("count", 0) or 0) + 1
            stats["last_confidence"] = float(
                metrics.get("confidence", 0.0) or 0.0
            )
            patterns = dict(self._data["mapping"].get("patterns") or {})
            patterns[pattern] = stats
            self._data["mapping"]["patterns"] = patterns
            self._save()

    def summary(self):
        with self._lock:
            rooms = self._data.get("rooms") or {}
            learned = sum(
                1 for v in rooms.values() if list((v or {}).get("attempts") or [])
            )
            strong = sum(
                1 for v in rooms.values()
                if float((v or {}).get("best_score", 0.0) or 0.0) >= 88.0
            )
            return {
                "learned_rooms": learned,
                "strong_rooms": strong,
                "mapping_sessions": len(
                    (self._data.get("mapping") or {}).get("sessions") or []
                ),
            }

    def reset_learning(self):
        with self._lock:
            self._data = {
                "version": self.VERSION,
                "rooms": {},
                "mapping": {"sessions": [], "patterns": {}},
            }
            self._save()

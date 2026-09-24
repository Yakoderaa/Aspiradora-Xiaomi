import json
import math
import threading
import time
from pathlib import Path


class TrajectorySamplerV157:
    """Convierte 10/24 del B112 en una trayectoria local estable y liviana."""

    WRAP_UNITS = 256.0
    RAW_TO_METERS = 0.10

    def __init__(self, vacuum, sample_m=0.25, prestart_robot=None):
        self.vacuum = vacuum
        self.sample_m = max(0.10, float(sample_m))
        self.prestart = self._parse(prestart_robot)
        self.base = None
        self.previous_unwrapped = None
        self.last_saved = None
        self.points = []
        self.rejected = 0
        self.wrap_x = 0
        self.wrap_y = 0
        self._departed = False

    def _parse(self, value):
        try:
            parsed = self.vacuum.parse_position(value)
        except Exception:
            parsed = None
        if not parsed:
            return None
        try:
            return (
                float(parsed["x"]),
                float(parsed["y"]),
                float(parsed.get("angle", 0.0) or 0.0),
            )
        except Exception:
            return None

    @staticmethod
    def _same_xy(a, b, eps=1e-6):
        if a is None or b is None:
            return False
        return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps

    def _unwrap(self, raw, previous, base, axis):
        raw = float(raw)
        if previous is None:
            value = raw + round((float(base) - raw) / self.WRAP_UNITS) * self.WRAP_UNITS
        else:
            value = raw + round((float(previous) - raw) / self.WRAP_UNITS) * self.WRAP_UNITS
        shift = int(round((value - raw) / self.WRAP_UNITS))
        if axis == "x":
            self.wrap_x = shift
        else:
            self.wrap_y = shift
        return value

    def note_state(self, state):
        state = dict(state or {})
        robot = self._parse(state.get("robot"))
        base = self._parse(state.get("base"))
        if base is not None:
            self.base = (base[0], base[1])
        if self.base is None:
            self.base = (60.0, 60.0)
        if robot is None:
            return None

        if not self._departed and self.prestart is not None:
            if self._same_xy(robot, self.prestart):
                return None
            self._departed = True
        elif not self._departed:
            self._departed = True

        prev = self.previous_unwrapped
        ux = self._unwrap(
            robot[0],
            prev[0] if prev is not None else None,
            self.base[0],
            "x",
        )
        uy = self._unwrap(
            robot[1],
            prev[1] if prev is not None else None,
            self.base[1],
            "y",
        )

        x = (ux - self.base[0]) * self.RAW_TO_METERS
        y = (uy - self.base[1]) * self.RAW_TO_METERS
        angle = robot[2]

        if prev is None and math.hypot(x, y) > 15.0:
            self.rejected += 1
            return None

        if prev is not None:
            step = math.hypot(ux - prev[0], uy - prev[1]) * self.RAW_TO_METERS
            if step > 4.0:
                self.rejected += 1
                return None

        self.previous_unwrapped = (ux, uy)
        if self.last_saved is not None:
            if math.hypot(x - self.last_saved[0], y - self.last_saved[1]) < self.sample_m:
                return None

        point = {
            "id": len(self.points) + 1,
            "x": round(float(x), 4),
            "y": round(float(y), 4),
            "phi": round(float(angle), 6),
        }
        self.points.append(point)
        self.last_saved = (x, y)
        return point

    def stats(self):
        return RouteLearningStoreV157.stats(self.points)


class RouteLearningStoreV157:
    """Memoria local: vivienda completa = primaria; habitaciones/zonas = secundaria."""

    SCHEMA = 1
    CELL_M = 0.40
    MAX_POINTS = 6000

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "route_learning_v157.json"
        self._lock = threading.RLock()

    @staticmethod
    def stats(points):
        clean = []
        total = 0.0
        previous = None
        for point in list(points or []):
            try:
                x = float(point["x"])
                y = float(point["y"])
            except Exception:
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            clean.append((x, y))
            if previous is not None:
                total += math.hypot(x - previous[0], y - previous[1])
            previous = (x, y)
        if not clean:
            return {"points": 0, "span_x": 0.0, "span_y": 0.0, "path_m": 0.0}
        xs = [p[0] for p in clean]
        ys = [p[1] for p in clean]
        return {
            "points": len(clean),
            "span_x": round(max(xs) - min(xs), 3),
            "span_y": round(max(ys) - min(ys), 3),
            "path_m": round(total, 2),
        }

    def _defaults(self):
        return {
            "schema": self.SCHEMA,
            "primary": None,
            "targets": {},
            "updated_epoch": None,
        }

    def load(self):
        with self._lock:
            if not self.path.exists():
                return self._defaults()
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                return self._defaults()
            result = self._defaults()
            result.update(data)
            result["targets"] = dict(result.get("targets") or {})
            return result

    def _write(self, data):
        data = dict(data)
        data["schema"] = self.SCHEMA
        data["updated_epoch"] = time.time()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @classmethod
    def _merge_points(cls, old, new):
        cell_m = float(cls.CELL_M)
        merged = {}
        order = []
        for point in list(old or []) + list(new or []):
            try:
                x = float(point["x"])
                y = float(point["y"])
                phi = float(point.get("phi", 0.0) or 0.0)
            except Exception:
                continue
            key = (int(round(x / cell_m)), int(round(y / cell_m)))
            if key not in merged:
                order.append(key)
            merged[key] = {"x": round(x, 4), "y": round(y, 4), "phi": round(phi, 6)}
        if len(order) > cls.MAX_POINTS:
            stride = max(1, int(math.ceil(len(order) / float(cls.MAX_POINTS))))
            order = order[::stride][: cls.MAX_POINTS]
        return [
            {"id": index + 1, **merged[key]}
            for index, key in enumerate(order)
        ]

    @staticmethod
    def plausible(points, minimum=12, max_span=25.0):
        stats = RouteLearningStoreV157.stats(points)
        return (
            stats["points"] >= int(minimum)
            and max(stats["span_x"], stats["span_y"]) <= float(max_span)
        ), stats

    def primary(self):
        data = self.load()
        value = data.get("primary")
        return dict(value) if isinstance(value, dict) else None

    def merge_primary(self, points, source="whole-home"):
        ok, run_stats = self.plausible(points, minimum=20)
        if not ok:
            return False, run_stats
        with self._lock:
            data = self.load()
            old = list((data.get("primary") or {}).get("points") or [])
            merged = self._merge_points(old, points)
            data["primary"] = {
                "kind": "whole-home",
                "source": str(source),
                "points": merged,
                "stats": self.stats(merged),
                "last_run_stats": run_stats,
                "runs": int((data.get("primary") or {}).get("runs", 0) or 0) + 1,
                "updated_epoch": time.time(),
            }
            self._write(data)
            return True, dict(data["primary"]["stats"])

    def merge_target(self, key, points, label="", source="target"):
        key = str(key or "").strip()
        if not key:
            return False, self.stats(points)
        ok, run_stats = self.plausible(points, minimum=3)
        if not ok:
            return False, run_stats
        with self._lock:
            data = self.load()
            targets = dict(data.get("targets") or {})
            old_item = dict(targets.get(key) or {})
            merged = self._merge_points(old_item.get("points") or [], points)
            targets[key] = {
                "kind": "target",
                "key": key,
                "label": str(label or key),
                "source": str(source),
                "points": merged,
                "stats": self.stats(merged),
                "last_run_stats": run_stats,
                "runs": int(old_item.get("runs", 0) or 0) + 1,
                "updated_epoch": time.time(),
            }
            data["targets"] = targets
            self._write(data)
            return True, dict(targets[key]["stats"])

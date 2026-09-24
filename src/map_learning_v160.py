import json
import math
import threading
import time
from pathlib import Path


class MapLearningStoreV160:
    """Aprendizaje persistente de geometría Xiaomi por consenso entre sesiones.

    No controla el robot. Sólo recibe grids finales ya decodificados y construye
    una versión aprendida conservadora: el mapa actual siempre se conserva y la
    geometría histórica sólo vuelve a agregarse cuando fue observada de forma
    repetida en sesiones recientes.
    """

    SCHEMA = 1
    MAX_SESSIONS = 8
    MIN_HISTORY_SUPPORT = 2
    SUPPORT_RATIO = 0.35

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "map_learning_v160.json"
        self._lock = threading.RLock()

    def _defaults(self):
        return {"schema": self.SCHEMA, "maps": {}, "updated_epoch": None}

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
            result["maps"] = dict(result.get("maps") or {})
            return result

    def _write(self, data):
        payload = dict(data)
        payload["schema"] = self.SCHEMA
        payload["updated_epoch"] = time.time()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def _grid_shape(grid):
        try:
            side = int(grid.get("side", 0) or 0)
            resolution = float(grid.get("resolution", 0.0) or 0.0)
            base = list(grid.get("base_cell") or [])
            cells = [1 if int(v) else 0 for v in list(grid.get("cells") or [])]
            bx, by = float(base[0]), float(base[1])
        except Exception:
            return None
        if (
            side <= 0
            or side > 512
            or len(cells) != side * side
            or not math.isfinite(resolution)
            or resolution <= 0.0
            or len(base) < 2
            or not math.isfinite(bx)
            or not math.isfinite(by)
            or not any(cells)
        ):
            return None
        return side, resolution, (bx, by), cells

    @staticmethod
    def _compatible(item, side, resolution, base):
        try:
            old_side = int(item.get("side", 0) or 0)
            old_res = float(item.get("resolution", 0.0) or 0.0)
            old_base = list(item.get("base_cell") or [])
            return (
                old_side == side
                and abs(old_res - resolution) <= 1e-9
                and len(old_base) >= 2
                and abs(float(old_base[0]) - base[0]) <= 1e-6
                and abs(float(old_base[1]) - base[1]) <= 1e-6
            )
        except Exception:
            return False

    @staticmethod
    def _largest_component(cells, side):
        occupied = {i for i, value in enumerate(cells) if int(value)}
        if not occupied:
            return [0] * (side * side), 0, 0

        components = []
        while occupied:
            seed = occupied.pop()
            stack = [seed]
            component = {seed}
            while stack:
                idx = stack.pop()
                x, y = idx % side, idx // side
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if nx < 0 or ny < 0 or nx >= side or ny >= side:
                        continue
                    nidx = ny * side + nx
                    if nidx in occupied:
                        occupied.remove(nidx)
                        component.add(nidx)
                        stack.append(nidx)
            components.append(component)

        largest = max(components, key=len)
        out = [0] * (side * side)
        for idx in largest:
            out[idx] = 1
        removed = sum(len(c) for c in components) - len(largest)
        return out, len(components), removed

    @staticmethod
    def _metrics(cells, side):
        occupied = [i for i, value in enumerate(cells) if int(value)]
        nonzero = len(occupied)
        if nonzero <= 0:
            return {
                "valid": False,
                "nonzero": 0,
                "components": 0,
                "largest": 0,
                "largest_ratio": 0.0,
                "adjacency_ratio": 0.0,
            }

        occupied_set = set(occupied)
        remaining = set(occupied)
        components = []
        adjacency = 0
        for idx in occupied:
            x, y = idx % side, idx // side
            if x + 1 < side and idx + 1 in occupied_set:
                adjacency += 1
            if y + 1 < side and idx + side in occupied_set:
                adjacency += 1
        while remaining:
            seed = remaining.pop()
            stack = [seed]
            count = 1
            while stack:
                idx = stack.pop()
                x, y = idx % side, idx // side
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < side and 0 <= ny < side:
                        nidx = ny * side + nx
                        if nidx in remaining:
                            remaining.remove(nidx)
                            stack.append(nidx)
                            count += 1
            components.append(count)
        largest = max(components) if components else 0
        return {
            "valid": nonzero > 0,
            "nonzero": nonzero,
            "components": len(components),
            "largest": largest,
            "largest_ratio": round(float(largest) / float(nonzero), 4),
            "adjacency_ratio": round(float(adjacency) / float(nonzero), 4),
        }

    def merge(self, map_id, session_key, grid, reason="physical-session"):
        """Devuelve (grid_aprendido, diagnóstico).

        Repetir la misma session_key reemplaza esa muestra. Esto permite que los
        reintentos finales V158 maduren la sesión sin contarla varias veces.
        """
        shape = self._grid_shape(grid)
        if shape is None:
            return None, {"accepted": False, "reason": "grid inválido"}
        side, resolution, base, current_cells = shape
        map_id = str(map_id or "default")
        session_key = str(session_key or "").strip()
        if not session_key:
            return dict(grid), {"accepted": False, "reason": "sin sesión física"}

        current_occupied = [i for i, value in enumerate(current_cells) if value]
        if len(current_occupied) < 20:
            return dict(grid), {
                "accepted": False,
                "reason": "geometría demasiado pequeña para aprender",
                "current_cells": len(current_occupied),
            }

        with self._lock:
            data = self.load()
            maps = dict(data.get("maps") or {})
            item = dict(maps.get(map_id) or {})
            reset = not item or not self._compatible(item, side, resolution, base)
            if reset:
                item = {
                    "side": side,
                    "resolution": resolution,
                    "base_cell": [base[0], base[1]],
                    "sessions": [],
                    "resets": int(item.get("resets", 0) or 0) + (1 if item else 0),
                }

            sessions = [
                dict(s) for s in list(item.get("sessions") or [])
                if isinstance(s, dict) and str(s.get("key") or "") != session_key
            ]
            sessions.append({
                "key": session_key,
                "reason": str(reason or "physical-session"),
                "blob_sha12": str(grid.get("blob_sha12") or ""),
                "timestamp": grid.get("timestamp"),
                "occupied": current_occupied,
                "saved_epoch": time.time(),
            })
            sessions = sessions[-int(self.MAX_SESSIONS):]

            counts = {}
            for sample in sessions:
                for idx in list(sample.get("occupied") or []):
                    try:
                        idx = int(idx)
                    except Exception:
                        continue
                    if 0 <= idx < side * side:
                        counts[idx] = counts.get(idx, 0) + 1

            n = len(sessions)
            support_needed = max(
                int(self.MIN_HISTORY_SUPPORT),
                int(math.ceil(float(n) * float(self.SUPPORT_RATIO))),
            )
            stable = {idx for idx, count in counts.items() if count >= support_needed}
            current_set = set(current_occupied)
            combined = current_set | stable
            learned_cells = [1 if idx in combined else 0 for idx in range(side * side)]
            learned_cells, components_before, removed_detached = self._largest_component(
                learned_cells,
                side,
            )
            learned_set = {i for i, value in enumerate(learned_cells) if value}
            added_from_history = len(learned_set - current_set)

            item.update({
                "side": side,
                "resolution": resolution,
                "base_cell": [base[0], base[1]],
                "sessions": sessions,
                "last_session": session_key,
                "last_reason": str(reason or "physical-session"),
                "last_blob_sha12": str(grid.get("blob_sha12") or ""),
                "last_update_epoch": time.time(),
                "last_support_needed": support_needed,
                "last_current_cells": len(current_set),
                "last_learned_cells": len(learned_set),
                "last_added_from_history": added_from_history,
            })
            maps[map_id] = item
            data["maps"] = maps
            self._write(data)

        result = dict(grid)
        result["cells"] = learned_cells
        result["source"] = "xiaomi-v160-ai-consensus"
        base_metrics = dict(grid.get("metrics") or {})
        learned_metrics = self._metrics(learned_cells, side)
        diag = {
            "accepted": True,
            "map_id": map_id,
            "session_key": session_key,
            "sessions": len(sessions),
            "max_sessions": int(self.MAX_SESSIONS),
            "support_needed": support_needed,
            "current_cells": len(current_set),
            "stable_cells": len(stable),
            "learned_cells": len(learned_set),
            "added_from_history": added_from_history,
            "components_before_filter": int(components_before),
            "detached_removed": int(removed_detached),
            "reset_for_geometry_change": bool(reset),
            "metrics": learned_metrics,
        }
        base_metrics["v160_learning"] = dict(diag)
        result["metrics"] = base_metrics
        return result, diag

    def diagnostic(self, map_id=None):
        data = self.load()
        maps = dict(data.get("maps") or {})
        if map_id is None:
            return {
                "schema": data.get("schema"),
                "maps": len(maps),
                "updated_epoch": data.get("updated_epoch"),
            }
        item = dict(maps.get(str(map_id)) or {})
        sessions = list(item.get("sessions") or [])
        return {
            "map_id": str(map_id),
            "sessions": len(sessions),
            "max_sessions": int(self.MAX_SESSIONS),
            "support_needed": item.get("last_support_needed"),
            "current_cells": item.get("last_current_cells"),
            "learned_cells": item.get("last_learned_cells"),
            "added_from_history": item.get("last_added_from_history"),
            "last_reason": item.get("last_reason"),
            "last_blob_sha12": item.get("last_blob_sha12"),
            "resets": int(item.get("resets", 0) or 0),
        }

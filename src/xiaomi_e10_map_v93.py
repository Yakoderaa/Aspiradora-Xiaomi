import math
from collections import Counter, deque

from xiaomi_e10_map_v92 import XiaomiE10MapV92


class XiaomiE10MapV93(XiaomiE10MapV92):
    """V93: coherencia física/temporal para elegir el layout B112."""

    ROBOT_NEAR_CELLS = 2.5
    DELTA_NEAR_CELLS = 3.5
    CLEAN_MIN_CELLS = 150
    CLEAN_CORE_NEIGHBORS = 5
    CLEAN_RETAIN_RATIO = 0.68

    def __init__(self, *args, **kwargs):
        self._v93_prev_frame_cells = {}
        self._v93_temporal_stats = {}
        self._v93_selected_key = None
        self._v93_finalized = False
        self.last_v93_diagnostics = {}
        super().__init__(*args, **kwargs)

    def reset_v92_accumulator(self, reason="nueva sesión"):
        result = super().reset_v92_accumulator(reason)
        self._v93_prev_frame_cells.clear()
        self._v93_temporal_stats.clear()
        self._v93_selected_key = None
        self._v93_finalized = False
        self.last_v93_diagnostics = {
            "reset_reason": str(reason),
            "finalized": False,
        }
        return result

    @classmethod
    def _valid_robot_cell(cls, point):
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        if not (0.0 <= x < cls.GRID_SIDE and 0.0 <= y < cls.GRID_SIDE):
            return None
        if x >= 250.0 and y >= 250.0:
            return None
        return x, y

    @classmethod
    def _nearest_distance(cls, cells, point):
        if point is None:
            return None
        try:
            px, py = float(point[0]), float(point[1])
        except Exception:
            return None
        best = None
        side = cls.GRID_SIDE
        for idx, value in enumerate(cells or []):
            if not int(value):
                continue
            distance = math.hypot((idx % side) - px, (idx // side) - py)
            if best is None or distance < best:
                best = distance
                if best <= 0.05:
                    break
        return best

    @staticmethod
    def _candidate_key(item):
        layout = str(item.get("layout") or "")
        mask = str(item.get("mask") or "")
        if layout or mask:
            return f"{layout}|{mask}"
        label = str(item.get("label") or "")
        if label.startswith("acum[") and "|" in label:
            return label.split("|", 1)[1]
        return label

    @staticmethod
    def _changed_mask(previous, current):
        current = list(current or [])
        if previous is None or len(previous) != len(current):
            return [1 if int(value) else 0 for value in current]
        return [
            1 if int(now) and not int(old) else 0
            for old, now in zip(previous, current)
        ]

    def _v93_note_frame(self, options, robot_cell):
        for item in options or []:
            key = self._candidate_key(item)
            cells = list(item.get("cells") or [])
            if not key or len(cells) != self.GRID_SIDE * self.GRID_SIDE:
                continue

            previous = self._v93_prev_frame_cells.get(key)
            changed = self._changed_mask(previous, cells)
            robot_distance = self._nearest_distance(cells, robot_cell)
            delta_distance = self._nearest_distance(changed, robot_cell)
            changed_count = sum(1 for value in changed if int(value))

            stats = self._v93_temporal_stats.setdefault(
                key,
                {
                    "samples": 0,
                    "robot_sum": 0.0,
                    "robot_n": 0,
                    "robot_hits": 0,
                    "delta_sum": 0.0,
                    "delta_n": 0,
                    "delta_hits": 0,
                    "changed_cells": 0,
                },
            )
            stats["samples"] += 1
            if robot_distance is not None:
                stats["robot_sum"] += min(float(robot_distance), 20.0)
                stats["robot_n"] += 1
                if float(robot_distance) <= self.ROBOT_NEAR_CELLS:
                    stats["robot_hits"] += 1
            if delta_distance is not None and changed_count:
                stats["delta_sum"] += min(float(delta_distance), 20.0)
                stats["delta_n"] += 1
                stats["changed_cells"] += int(changed_count)
                if float(delta_distance) <= self.DELTA_NEAR_CELLS:
                    stats["delta_hits"] += 1
            self._v93_prev_frame_cells[key] = cells

    @staticmethod
    def _avg(stats, total_key, count_key):
        count = int((stats or {}).get(count_key, 0) or 0)
        if count <= 0:
            return None
        return float((stats or {}).get(total_key, 0.0) or 0.0) / count

    @classmethod
    def _shape_stats(cls, cells):
        side = cls.GRID_SIDE
        occupied = [idx for idx, value in enumerate(cells or []) if int(value)]
        if not occupied:
            return {"area": 0, "perimeter": 0, "density": 0.0, "bbox": None}

        xs = [idx % side for idx in occupied]
        ys = [idx // side for idx in occupied]
        bbox_area = max(
            1,
            (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1),
        )
        occupied_set = set(occupied)
        perimeter = 0
        for idx in occupied:
            x, y = idx % side, idx // side
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (
                    nx < 0
                    or ny < 0
                    or nx >= side
                    or ny >= side
                    or ny * side + nx not in occupied_set
                ):
                    perimeter += 1
        return {
            "area": len(occupied),
            "perimeter": perimeter,
            "density": len(occupied) / float(bbox_area),
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
        }

    def _v93_score(self, item, base_cell, robot_cell):
        cells = list(item.get("cells") or [])
        metrics = dict(item.get("metrics") or self._grid_metrics(cells))
        key = self._candidate_key(item)
        stats = dict(self._v93_temporal_stats.get(key) or {})
        base_distance = self._base_distance(cells, base_cell)
        robot_distance = self._nearest_distance(cells, robot_cell)
        robot_avg = self._avg(stats, "robot_sum", "robot_n")
        delta_avg = self._avg(stats, "delta_sum", "delta_n")
        robot_n = max(1, int(stats.get("robot_n", 0) or 0))
        delta_n = max(1, int(stats.get("delta_n", 0) or 0))
        robot_hit_rate = float(stats.get("robot_hits", 0) or 0) / robot_n
        delta_hit_rate = float(stats.get("delta_hits", 0) or 0) / delta_n
        shape = self._shape_stats(cells)

        score = 0.0
        if metrics.get("valid"):
            score += 1_000_000_000_000.0
        score += float(metrics.get("largest", 0) or 0) * 1_000_000.0
        score += float(metrics.get("largest_ratio", 0.0) or 0.0) * 8_000_000.0
        score += float(metrics.get("adjacency_ratio", 0.0) or 0.0) * 1_000_000.0
        score -= float(metrics.get("components", 0) or 0) * 500_000.0

        if base_distance is not None:
            score -= min(float(base_distance), 30.0) * 50_000.0
        if robot_distance is not None:
            score -= min(float(robot_distance), 30.0) * 180_000.0
            if float(robot_distance) <= 1.5:
                score += 1_500_000.0
        if robot_avg is not None:
            score -= min(robot_avg, 20.0) * 120_000.0
            score += robot_hit_rate * 2_000_000.0
        if delta_avg is not None:
            score -= min(delta_avg, 20.0) * 160_000.0
            score += delta_hit_rate * 2_500_000.0

        # Tie-break visual: entre opciones igual de coherentes, evita contornos
        # dentados y favorece una planta compacta. Nunca saltea V57.
        score += float(shape["density"]) * 500_000.0
        score -= float(shape["perimeter"]) * 2_500.0

        return score, {
            "key": key,
            "base_distance": base_distance,
            "robot_distance": robot_distance,
            "robot_avg": robot_avg,
            "delta_avg": delta_avg,
            "robot_hit_rate": robot_hit_rate,
            "delta_hit_rate": delta_hit_rate,
            "shape": shape,
        }

    @classmethod
    def _components(cls, cells):
        side = cls.GRID_SIDE
        occupied = {idx for idx, value in enumerate(cells or []) if int(value)}
        unseen = set(occupied)
        result = []
        while unseen:
            start = unseen.pop()
            queue = deque([start])
            component = {start}
            while queue:
                idx = queue.popleft()
                x, y = idx % side, idx // side
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < side and 0 <= ny < side):
                        continue
                    nxt = ny * side + nx
                    if nxt in unseen:
                        unseen.remove(nxt)
                        component.add(nxt)
                        queue.append(nxt)
            result.append(component)
        result.sort(key=len, reverse=True)
        return result

    @classmethod
    def _keep_main_component(cls, cells, base_cell=None):
        raw = [1 if int(value) else 0 for value in (cells or [])]
        components = cls._components(raw)
        if not components:
            return raw, 0

        chosen = components[0]
        if base_cell is not None:
            try:
                bx, by = float(base_cell[0]), float(base_cell[1])
                largest = len(components[0])
                best = None
                for component in components:
                    if len(component) < max(8, int(largest * 0.25)):
                        continue
                    distance = min(
                        math.hypot((idx % cls.GRID_SIDE) - bx, (idx // cls.GRID_SIDE) - by)
                        for idx in component
                    )
                    candidate = (distance, -len(component), component)
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
                if best is not None and best[0] <= 4.0:
                    chosen = best[2]
            except Exception:
                pass

        out = [0] * len(raw)
        for idx in chosen:
            out[idx] = 1
        return out, max(0, sum(raw) - len(chosen))

    @classmethod
    def _fill_enclosed_holes(cls, cells):
        side = cls.GRID_SIDE
        raw = [1 if int(value) else 0 for value in (cells or [])]
        occupied = [idx for idx, value in enumerate(raw) if value]
        if not occupied:
            return raw, 0

        xs = [idx % side for idx in occupied]
        ys = [idx // side for idx in occupied]
        min_x, max_x = max(0, min(xs) - 1), min(side - 1, max(xs) + 1)
        min_y, max_y = max(0, min(ys) - 1), min(side - 1, max(ys) + 1)
        outside = set()
        queue = deque()

        for x in range(min_x, max_x + 1):
            for y in (min_y, max_y):
                idx = y * side + x
                if not raw[idx] and idx not in outside:
                    outside.add(idx)
                    queue.append(idx)
        for y in range(min_y, max_y + 1):
            for x in (min_x, max_x):
                idx = y * side + x
                if not raw[idx] and idx not in outside:
                    outside.add(idx)
                    queue.append(idx)

        while queue:
            idx = queue.popleft()
            x, y = idx % side, idx // side
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                    continue
                nxt = ny * side + nx
                if raw[nxt] or nxt in outside:
                    continue
                outside.add(nxt)
                queue.append(nxt)

        filled = 0
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                idx = y * side + x
                if not raw[idx] and idx not in outside:
                    raw[idx] = 1
                    filled += 1
        return raw, filled

    @classmethod
    def _prune_thin_spurs(cls, cells, protected_points=()):
        side = cls.GRID_SIDE
        raw = [1 if int(value) else 0 for value in (cells or [])]
        occupied = {idx for idx, value in enumerate(raw) if value}
        if len(occupied) < cls.CLEAN_MIN_CELLS:
            return raw, 0, False

        protected = set()
        for point in protected_points or ():
            if point is None:
                continue
            try:
                px, py = int(round(float(point[0]))), int(round(float(point[1])))
            except Exception:
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    x, y = px + dx, py + dy
                    if 0 <= x < side and 0 <= y < side:
                        protected.add(y * side + x)

        core = set()
        for idx in occupied:
            x, y = idx % side, idx // side
            neighbors = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < side and 0 <= ny < side and ny * side + nx in occupied:
                        neighbors += 1
            if neighbors >= cls.CLEAN_CORE_NEIGHBORS:
                core.add(idx)

        if len(core) < max(20, int(len(occupied) * 0.25)):
            return raw, 0, False

        keep = set(core) | protected
        for idx in occupied:
            if idx in protected:
                continue
            x, y = idx % side, idx // side
            for dy in (-1, 0, 1):
                found = False
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < side and 0 <= ny < side and ny * side + nx in core:
                        keep.add(idx)
                        found = True
                        break
                if found:
                    break

        keep &= occupied
        if len(keep) < int(len(occupied) * cls.CLEAN_RETAIN_RATIO):
            return raw, 0, False

        out = [0] * len(raw)
        for idx in keep:
            out[idx] = 1
        return out, len(occupied) - len(keep), True

    @classmethod
    def _clean_cells(cls, cells, base_cell=None, robot_cell=None):
        original = [1 if int(value) else 0 for value in (cells or [])]
        stage1, detached = cls._keep_main_component(original, base_cell)
        stage2, pruned, applied = cls._prune_thin_spurs(
            stage1,
            protected_points=(base_cell, robot_cell),
        )
        stage3, filled = cls._fill_enclosed_holes(stage2)
        stage4, detached_after = cls._keep_main_component(stage3, base_cell)
        return stage4, {
            "before": sum(original),
            "after": sum(stage4),
            "detached_removed": int(detached + detached_after),
            "spurs_removed": int(pruned),
            "spur_filter_applied": bool(applied),
            "holes_filled": int(filled),
        }

    def mark_v93_finalized(self):
        self._v93_finalized = True

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        snapshot = super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        payload = bytes(decoded.get("payload") or b"")
        header = self._parse_header(payload) or {}
        offset = int(header.get("grid_offset", 0) or 0)
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        _current, current_options = self._decode_grid(grid_raw)

        base_grid, robot_grid = self._device_pose_grid()
        base_cell, base_fallback = self._valid_device_base_cell(base_grid)
        robot_cell = self._valid_robot_cell(robot_grid)
        self._v93_note_frame(current_options, robot_cell)

        candidates = list(current_options)
        for label, cells in self._v92_union_cells.items():
            candidates.append({
                "label": f"acum[{self._v92_frame_count}]|{label}",
                "layout": label.split("|", 1)[0],
                "mask": label.split("|", 1)[1] if "|" in label else "",
                "cells": list(cells),
                "metrics": dict(self._grid_metrics(cells)),
                "counts": dict(Counter(cells)),
                "source": "acumulado",
            })

        ranked = []
        for item in candidates:
            clone = dict(item)
            cells = list(clone.get("cells") or [])
            clone["metrics"] = dict(clone.get("metrics") or self._grid_metrics(cells))
            score, physics = self._v93_score(clone, base_cell, robot_cell)
            clone["v93_score"] = float(score)
            clone["v93_physics"] = physics
            ranked.append(clone)

        ranked.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                float(item.get("v93_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        selected = ranked[0] if ranked else {
            "label": getattr(snapshot, "grid_order", "—"),
            "cells": list(getattr(snapshot, "grid_cells", []) or []),
            "metrics": dict(self._grid_metrics(getattr(snapshot, "grid_cells", []) or [])),
            "source": "V92",
            "v93_score": 0.0,
            "v93_physics": {},
        }

        raw_cells = list(selected.get("cells") or [])
        cleaned, clean_diag = self._clean_cells(
            raw_cells,
            base_cell=base_cell,
            robot_cell=robot_cell,
        )
        selected_metrics = dict(selected.get("metrics") or self._grid_metrics(raw_cells))
        clean_metrics = dict(self._grid_metrics(cleaned))
        if selected_metrics.get("valid") and not clean_metrics.get("valid"):
            cleaned = raw_cells
            clean_metrics = selected_metrics
            clean_diag["reverted"] = True
        else:
            clean_diag["reverted"] = False

        snapshot.grid_cells = list(cleaned)
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = self._grid_walls(cleaned, base_cell=base_cell)
        snapshot.grid_counts = dict(Counter(cleaned))
        snapshot.grid_order = str(selected.get("label") or "")
        snapshot.grid_score = int(float(selected.get("v93_score", 0.0) or 0.0))
        snapshot.v92_grid_metrics = dict(clean_metrics)
        snapshot.v93_grid_metrics = dict(clean_metrics)
        snapshot.v93_source = str(selected.get("source") or "frame")
        snapshot.v93_robot_cell = tuple(robot_cell) if robot_cell is not None else None
        snapshot.v93_physics = dict(selected.get("v93_physics") or {})
        snapshot.v93_clean = dict(clean_diag)
        snapshot.v92_base_fallback = bool(base_fallback)

        if base_fallback:
            snapshot.raw_base = (
                float(base_cell[0]) * self.GRID_RESOLUTION_M,
                float(base_cell[1]) * self.GRID_RESOLUTION_M,
            )

        selected_key = self._candidate_key(selected)
        self._v93_selected_key = selected_key

        def brief(item):
            metrics = dict(item.get("metrics") or {})
            physics = dict(item.get("v93_physics") or {})
            shape = dict(physics.get("shape") or {})
            return {
                "label": item.get("label"),
                "key": self._candidate_key(item),
                "source": item.get("source"),
                "valid": bool(metrics.get("valid")),
                "nonzero": metrics.get("nonzero"),
                "components": metrics.get("components"),
                "largest": metrics.get("largest"),
                "largest_ratio": metrics.get("largest_ratio"),
                "adjacency_ratio": metrics.get("adjacency_ratio"),
                "score": round(float(item.get("v93_score", 0.0) or 0.0), 1),
                "base_distance": (
                    round(float(physics.get("base_distance")), 2)
                    if physics.get("base_distance") is not None else None
                ),
                "robot_distance": (
                    round(float(physics.get("robot_distance")), 2)
                    if physics.get("robot_distance") is not None else None
                ),
                "robot_avg": (
                    round(float(physics.get("robot_avg")), 2)
                    if physics.get("robot_avg") is not None else None
                ),
                "delta_avg": (
                    round(float(physics.get("delta_avg")), 2)
                    if physics.get("delta_avg") is not None else None
                ),
                "robot_hit_rate": round(float(physics.get("robot_hit_rate", 0.0) or 0.0), 3),
                "delta_hit_rate": round(float(physics.get("delta_hit_rate", 0.0) or 0.0), 3),
                "density": round(float(shape.get("density", 0.0) or 0.0), 3),
                "perimeter": shape.get("perimeter"),
            }

        self.last_v93_diagnostics = {
            "base_cell": tuple(base_cell),
            "base_fallback": bool(base_fallback),
            "robot_cell": tuple(robot_cell) if robot_cell is not None else None,
            "candidate_count": len(ranked),
            "selected": brief(selected),
            "selected_key": selected_key,
            "clean": dict(clean_diag),
            "clean_metrics": dict(clean_metrics),
            "temporal": dict(self._v93_temporal_stats.get(selected_key) or {}),
            "top": [brief(item) for item in ranked[:8]],
            "finalized": bool(self._v93_finalized),
        }
        return snapshot

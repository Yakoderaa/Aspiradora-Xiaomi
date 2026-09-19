import math

from xiaomi_e10_map_v100 import XiaomiE10MapV100
from xiaomi_e10_map_v107 import XiaomiE10MapV107


class XiaomiE10MapV109(XiaomiE10MapV107):
    """V109: el layout final se decide contra la trayectoria física real."""

    ORIENTATIONS = (
        "identity",
        "mirror_x",
        "mirror_y",
        "rotate_180",
        "swap_xy",
        "swap_neg_x",
        "swap_neg_y",
        "swap_both",
    )

    def __init__(self, *args, **kwargs):
        self._v109_reference_path = []
        self.last_v109_diagnostics = {}
        super().__init__(*args, **kwargs)

    def set_v109_reference_path(self, points):
        cleaned = []
        for point in list(points or []):
            if not isinstance(point, dict):
                continue
            try:
                x = float(point.get("x"))
                y = float(point.get("y"))
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                cleaned.append((x, y))
        # Hasta 220 muestras repartidas por toda la trayectoria: suficiente
        # para puntuar el grid sin hacer un trabajo excesivo en el worker final.
        if len(cleaned) > 220:
            step = max(1, len(cleaned) // 220)
            cleaned = cleaned[::step][-220:]
        self._v109_reference_path = cleaned

    @staticmethod
    def _v109_orient(name, x, y):
        x = float(x)
        y = float(y)
        if name == "identity":
            return x, y
        if name == "mirror_x":
            return -x, y
        if name == "mirror_y":
            return x, -y
        if name == "rotate_180":
            return -x, -y
        if name == "swap_xy":
            return y, x
        if name == "swap_neg_x":
            return -y, x
        if name == "swap_neg_y":
            return y, -x
        if name == "swap_both":
            return -y, -x
        return x, y

    @classmethod
    def _v109_oriented_centers(cls, cells, side, base_cell, resolution, orientation):
        try:
            bx, by = float(base_cell[0]), float(base_cell[1])
        except Exception:
            bx = by = float(side) / 2.0
        points = []
        for idx, value in enumerate(cells or []):
            if not int(value):
                continue
            gx = idx % int(side)
            gy = idx // int(side)
            x = (float(gx) + 0.5 - bx) * float(resolution)
            y = (by - (float(gy) + 0.5)) * float(resolution)
            points.append(cls._v109_orient(orientation, x, y))
        return points

    @staticmethod
    def _v109_bucket(points, size):
        buckets = {}
        size = max(0.05, float(size))
        for x, y in points:
            key = (math.floor(x / size), math.floor(y / size))
            buckets.setdefault(key, []).append((x, y))
        return buckets

    @staticmethod
    def _v109_nearest_distance(x, y, buckets, bucket_size, max_radius=3):
        if not buckets:
            return 9.0
        bx = math.floor(float(x) / bucket_size)
        by = math.floor(float(y) / bucket_size)
        best = None
        for radius in range(max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if radius and max(abs(dx), abs(dy)) != radius:
                        continue
                    for px, py in buckets.get((bx + dx, by + dy), ()):
                        distance = math.hypot(float(x) - px, float(y) - py)
                        if best is None or distance < best:
                            best = distance
            if best is not None and best <= (radius + 1) * bucket_size:
                break
        return float(best if best is not None else 1.8)

    @classmethod
    def _v109_path_score(
        cls,
        cells,
        side,
        base_cell,
        resolution,
        path,
        orientation,
        metrics,
    ):
        centers = cls._v109_oriented_centers(
            cells, side, base_cell, resolution, orientation
        )
        if not centers or not path:
            return -1e9, {}

        buckets = cls._v109_bucket(centers, resolution)
        distances = []
        covered = 0
        for x, y in path:
            distance = cls._v109_nearest_distance(
                x, y, buckets, float(resolution), max_radius=4
            )
            distances.append(min(distance, 1.8))
            if distance <= 0.36:
                covered += 1

        coverage = covered / float(max(1, len(path)))
        mean_distance = sum(distances) / float(max(1, len(distances)))
        sorted_distances = sorted(distances)
        p90 = sorted_distances[
            min(len(sorted_distances) - 1, int(len(sorted_distances) * 0.90))
        ]

        path_x = [p[0] for p in path]
        path_y = [p[1] for p in path]
        floor_x = [p[0] for p in centers]
        floor_y = [p[1] for p in centers]
        path_span_x = max(path_x) - min(path_x) if len(path_x) > 1 else 0.0
        path_span_y = max(path_y) - min(path_y) if len(path_y) > 1 else 0.0
        floor_span_x = max(floor_x) - min(floor_x) if len(floor_x) > 1 else 0.0
        floor_span_y = max(floor_y) - min(floor_y) if len(floor_y) > 1 else 0.0

        # Una habitación completa puede exceder algo la trayectoria del centro
        # del robot, pero no varios metros sin que el robot se acerque.
        excess_x = max(0.0, floor_span_x - path_span_x - 0.9)
        excess_y = max(0.0, floor_span_y - path_span_y - 0.9)
        excess = excess_x + excess_y

        components = int((metrics or {}).get("components", 0) or 0)
        largest_ratio = float((metrics or {}).get("largest_ratio", 0.0) or 0.0)
        adjacency = float((metrics or {}).get("adjacency_ratio", 0.0) or 0.0)

        score = (
            coverage * 2600.0
            - mean_distance * 700.0
            - p90 * 240.0
            - excess * 220.0
            + largest_ratio * 140.0
            + min(adjacency, 2.5) * 35.0
            - max(0, components - 1) * 80.0
        )
        return score, {
            "coverage": coverage,
            "mean_distance": mean_distance,
            "p90": p90,
            "excess": excess,
            "path_span": (path_span_x, path_span_y),
            "floor_span": (floor_span_x, floor_span_y),
        }

    @classmethod
    def _v109_transform_cells(
        cls,
        cells,
        side,
        base_cell,
        resolution,
        orientation,
    ):
        try:
            bx, by = float(base_cell[0]), float(base_cell[1])
        except Exception:
            bx = by = float(side) / 2.0
        out = [0] * (int(side) * int(side))
        for idx, value in enumerate(cells or []):
            if not int(value):
                continue
            gx = idx % int(side)
            gy = idx // int(side)
            x = (float(gx) + 0.5 - bx) * float(resolution)
            y = (by - (float(gy) + 0.5)) * float(resolution)
            ox, oy = cls._v109_orient(orientation, x, y)
            ngx = int(round(bx + ox / float(resolution) - 0.5))
            ngy = int(round(by - oy / float(resolution) - 0.5))
            if 0 <= ngx < int(side) and 0 <= ngy < int(side):
                out[ngy * int(side) + ngx] = 1
        return out

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        if not self._v107_final_mode or len(self._v109_reference_path) < 8:
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        # Evitamos la selección fija de V107 y partimos del snapshot normal.
        snapshot = XiaomiE10MapV100._snapshot_from_grid(
            self, slot, endpoint, raw, decoded
        )

        payload = bytes(decoded.get("payload") or b"")
        header = self._parse_header(payload) or {}
        offset = int(header.get("grid_offset", 0) or 0)
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        _current, current_options = self._decode_grid(grid_raw)

        base_grid, robot_grid = self._device_pose_grid()
        base_cell, base_fallback = self._valid_device_base_cell(base_grid)

        ranked = []
        for item in list(current_options or []):
            cells = [1 if int(v) else 0 for v in list(item.get("cells") or [])]
            if len(cells) != self.GRID_SIDE * self.GRID_SIDE:
                continue
            metrics = dict(item.get("metrics") or self._grid_metrics(cells))
            nonzero = int(metrics.get("nonzero", 0) or 0)
            if nonzero < 4:
                continue

            literal, detached = self._keep_main_component(cells, base_cell)
            literal_metrics = dict(self._grid_metrics(literal))
            for orientation in self.ORIENTATIONS:
                score, physics = self._v109_path_score(
                    literal,
                    self.GRID_SIDE,
                    base_cell,
                    self.GRID_RESOLUTION_M,
                    self._v109_reference_path,
                    orientation,
                    literal_metrics,
                )
                ranked.append({
                    "score": float(score),
                    "item": item,
                    "cells": literal,
                    "orientation": orientation,
                    "physics": physics,
                    "metrics": literal_metrics,
                    "detached": int(detached),
                })

        ranked.sort(key=lambda row: row["score"], reverse=True)
        best = ranked[0] if ranked else None

        if not best:
            self.last_v109_diagnostics = {
                "source": "fallback-v107",
                "reason": "sin layout puntuable contra trayectoria",
                "path_points": len(self._v109_reference_path),
            }
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        final_cells = self._v109_transform_cells(
            best["cells"],
            self.GRID_SIDE,
            base_cell,
            self.GRID_RESOLUTION_M,
            best["orientation"],
        )
        final_metrics = dict(self._grid_metrics(final_cells))
        selected = best["item"]

        snapshot.grid_cells = list(final_cells)
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = self._grid_walls(
            final_cells,
            base_cell=base_cell,
        )
        snapshot.grid_counts = {
            0: len(final_cells) - sum(final_cells),
            1: sum(final_cells),
        }
        snapshot.grid_order = (
            "v109-physical|"
            + str(selected.get("label") or self._candidate_key(selected))
            + "|"
            + str(best["orientation"])
        )
        snapshot.v92_grid_metrics = dict(final_metrics)
        snapshot.v93_grid_metrics = dict(final_metrics)
        snapshot.v93_source = "v109-path-fit-final"
        snapshot.v107_final_current = True
        snapshot.v107_mirrored_y = best["orientation"] == "mirror_y"
        snapshot.v109_orientation = str(best["orientation"])
        snapshot.v109_path_fit = dict(best["physics"])
        snapshot.v109_path_score = float(best["score"])
        snapshot.v109_selected_key = self._candidate_key(selected)
        snapshot.v109_detached_removed = int(best["detached"])
        snapshot.v92_base_fallback = bool(base_fallback)

        top = []
        for row in ranked[:8]:
            top.append({
                "key": self._candidate_key(row["item"]),
                "orientation": row["orientation"],
                "score": round(float(row["score"]), 3),
                "coverage": round(float(row["physics"].get("coverage", 0.0)), 4),
                "mean_distance": round(
                    float(row["physics"].get("mean_distance", 0.0)), 4
                ),
                "p90": round(float(row["physics"].get("p90", 0.0)), 4),
                "nonzero": int(
                    (row.get("metrics") or {}).get("nonzero", 0) or 0
                ),
            })

        self.last_v109_diagnostics = {
            "source": "path-fit-current-frame",
            "path_points": len(self._v109_reference_path),
            "selected_key": self._candidate_key(selected),
            "selected_label": selected.get("label"),
            "orientation": best["orientation"],
            "score": float(best["score"]),
            "physics": dict(best["physics"]),
            "cells": int(sum(final_cells)),
            "detached_removed": int(best["detached"]),
            "base_cell": tuple(base_cell),
            "top": top,
        }
        return snapshot

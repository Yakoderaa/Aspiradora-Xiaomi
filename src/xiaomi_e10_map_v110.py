import math

from xiaomi_e10_map_v100 import XiaomiE10MapV100
from xiaomi_e10_map_v109 import XiaomiE10MapV109


class XiaomiE10MapV110(XiaomiE10MapV109):
    """V110: layout final guiado por trayectoria + área física + topología."""

    AREA_MIN_M2 = 0.2
    AREA_REL_TOLERANCE = 0.35

    def __init__(self, *args, **kwargs):
        self._v110_target_area_m2 = None
        self.last_v110_diagnostics = {}
        super().__init__(*args, **kwargs)

    def set_v110_target_area(self, area_m2):
        try:
            value = float(area_m2)
        except Exception:
            value = 0.0
        self._v110_target_area_m2 = (
            value if math.isfinite(value) and value >= self.AREA_MIN_M2 else None
        )

    @classmethod
    def _v110_perimeter_edges(cls, cells, side):
        side = int(side)
        occupied = {
            idx for idx, value in enumerate(cells or []) if int(value)
        }
        perimeter = 0
        for idx in occupied:
            x, y = idx % side, idx // side
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < side and 0 <= ny < side):
                    perimeter += 1
                    continue
                if ny * side + nx not in occupied:
                    perimeter += 1
        return perimeter

    @classmethod
    def _v110_hole_count(cls, cells, side):
        side = int(side)
        raw = [1 if int(v) else 0 for v in (cells or [])]
        occupied = [idx for idx, value in enumerate(raw) if value]
        if not occupied:
            return 0

        xs = [idx % side for idx in occupied]
        ys = [idx // side for idx in occupied]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        outside = set()
        stack = []
        for x in range(min_x, max_x + 1):
            for y in (min_y, max_y):
                idx = y * side + x
                if not raw[idx] and idx not in outside:
                    outside.add(idx)
                    stack.append(idx)
        for y in range(min_y, max_y + 1):
            for x in (min_x, max_x):
                idx = y * side + x
                if not raw[idx] and idx not in outside:
                    outside.add(idx)
                    stack.append(idx)

        while stack:
            idx = stack.pop()
            x, y = idx % side, idx // side
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                    continue
                nxt = ny * side + nx
                if raw[nxt] or nxt in outside:
                    continue
                outside.add(nxt)
                stack.append(nxt)

        holes = 0
        seen = set(outside)
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                idx = y * side + x
                if raw[idx] or idx in seen:
                    continue
                holes += 1
                queue = [idx]
                seen.add(idx)
                while queue:
                    cur = queue.pop()
                    cx, cy = cur % side, cur // side
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                            continue
                        nxt = ny * side + nx
                        if raw[nxt] or nxt in seen:
                            continue
                        seen.add(nxt)
                        queue.append(nxt)
        return holes

    @classmethod
    def _v110_topology(cls, cells, side):
        nonzero = sum(1 for value in cells or [] if int(value))
        perimeter = cls._v110_perimeter_edges(cells, side)
        holes = cls._v110_hole_count(cells, side)
        compactness = (
            float(perimeter) / math.sqrt(float(nonzero))
            if nonzero > 0 else 999.0
        )
        return {
            "nonzero": nonzero,
            "perimeter": perimeter,
            "holes": holes,
            "compactness": compactness,
        }

    def _v110_area_score(self, nonzero):
        target = self._v110_target_area_m2
        area = float(nonzero) * float(self.GRID_RESOLUTION_M) ** 2
        if target is None or target <= 0:
            return 0.0, {
                "target_m2": None,
                "grid_m2": area,
                "relative_error": None,
            }

        rel_error = abs(area - target) / max(target, 0.01)
        # Error de área tiene peso alto, porque el E10/Mi Home conoce el área
        # física recorrida y evita elegir máscaras demasiado ralas.
        penalty = rel_error * 2300.0
        if rel_error <= 0.12:
            bonus = 420.0
        elif rel_error <= 0.25:
            bonus = 180.0
        else:
            bonus = 0.0
        return bonus - penalty, {
            "target_m2": target,
            "grid_m2": area,
            "relative_error": rel_error,
        }

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        if not self._v107_final_mode or len(self._v109_reference_path) < 8:
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

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

            literal, detached = self._keep_main_component(cells, base_cell)
            metrics = dict(self._grid_metrics(literal))
            topology = self._v110_topology(literal, self.GRID_SIDE)
            area_score, area_diag = self._v110_area_score(
                topology["nonzero"]
            )

            # Dientes repetitivos y huecos internos disparan perímetro/compactness.
            topology_penalty = (
                max(0.0, topology["compactness"] - 7.0) * 120.0
                + float(topology["holes"]) * 170.0
            )

            for orientation in self.ORIENTATIONS:
                path_score, physics = self._v109_path_score(
                    literal,
                    self.GRID_SIDE,
                    base_cell,
                    self.GRID_RESOLUTION_M,
                    self._v109_reference_path,
                    orientation,
                    metrics,
                )
                total = float(path_score) + float(area_score) - topology_penalty
                ranked.append({
                    "score": total,
                    "path_score": float(path_score),
                    "area_score": float(area_score),
                    "item": item,
                    "cells": literal,
                    "orientation": orientation,
                    "physics": physics,
                    "metrics": metrics,
                    "detached": int(detached),
                    "topology": dict(topology),
                    "area": dict(area_diag),
                })

        ranked.sort(key=lambda row: row["score"], reverse=True)
        best = ranked[0] if ranked else None
        if not best:
            self.last_v110_diagnostics = {
                "source": "fallback-v109",
                "reason": "sin candidato final puntuable",
                "target_area_m2": self._v110_target_area_m2,
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
            "v110-area-physical|"
            + str(selected.get("label") or self._candidate_key(selected))
            + "|"
            + str(best["orientation"])
        )
        snapshot.v92_grid_metrics = dict(final_metrics)
        snapshot.v93_grid_metrics = dict(final_metrics)
        snapshot.v93_source = "v110-path-area-topology-final"
        snapshot.v107_final_current = True
        snapshot.v109_orientation = str(best["orientation"])
        snapshot.v109_path_fit = dict(best["physics"])
        snapshot.v109_path_score = float(best["path_score"])
        snapshot.v109_selected_key = self._candidate_key(selected)
        snapshot.v110_area_fit = dict(best["area"])
        snapshot.v110_topology = dict(best["topology"])
        snapshot.v110_total_score = float(best["score"])
        snapshot.v92_base_fallback = bool(base_fallback)

        top = []
        for row in ranked[:12]:
            top.append({
                "key": self._candidate_key(row["item"]),
                "mask": row["item"].get("mask"),
                "orientation": row["orientation"],
                "score": round(float(row["score"]), 2),
                "path_score": round(float(row["path_score"]), 2),
                "area_score": round(float(row["area_score"]), 2),
                "grid_m2": round(float(row["area"].get("grid_m2", 0.0)), 3),
                "target_m2": row["area"].get("target_m2"),
                "area_error": (
                    round(float(row["area"]["relative_error"]), 4)
                    if row["area"].get("relative_error") is not None else None
                ),
                "holes": int(row["topology"].get("holes", 0)),
                "perimeter": int(row["topology"].get("perimeter", 0)),
                "compactness": round(
                    float(row["topology"].get("compactness", 0.0)), 3
                ),
                "coverage": round(
                    float(row["physics"].get("coverage", 0.0)), 4
                ),
                "nonzero": int(row["topology"].get("nonzero", 0)),
            })

        self.last_v110_diagnostics = {
            "source": "path+area+topology-current-frame",
            "target_area_m2": self._v110_target_area_m2,
            "selected_key": self._candidate_key(selected),
            "selected_label": selected.get("label"),
            "selected_mask": selected.get("mask"),
            "orientation": best["orientation"],
            "score": float(best["score"]),
            "path_score": float(best["path_score"]),
            "area_score": float(best["area_score"]),
            "area": dict(best["area"]),
            "topology": dict(best["topology"]),
            "physics": dict(best["physics"]),
            "cells": int(sum(final_cells)),
            "top": top,
        }
        return snapshot

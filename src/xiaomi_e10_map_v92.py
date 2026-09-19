import itertools
import math
from collections import Counter

from xiaomi_e10_map_v91 import XiaomiE10MapV91


class XiaomiE10MapV92(XiaomiE10MapV91):
    """V92: busca la disposición espacial real del grid B112 y acumula frames.

    V91 ya abrió correctamente el payload 3628 B. V92 deja de asumir que los
    cuatro valores 2bpp de cada byte son cuatro píxeles horizontales. Se prueban
    tres familias físicas de empaquetado:
      - 4 celdas horizontales por byte (30 x 120 bytes)
      - 4 celdas verticales por byte (120 x 30 bytes)
      - bloque 2x2 por byte (60 x 60 bytes), con las 24 permutaciones locales

    Cada disposición se prueba con las siete máscaras de valores de V91. Además
    se conserva una unión temporal por candidato, porque los blobs observados
    cambian durante la limpieza y pueden ser frames/deltas del mapa.
    """

    ACCUM_MAX_UNIQUE_FRAMES = 48
    ACCUM_RESET_GAP_SECONDS = 45 * 60
    BASE_FALLBACK_CELL = (60.0, 60.0)

    MASKS = (
        ("nonzero", {1, 2, 3}),
        ("v1", {1}),
        ("v2", {2}),
        ("v3", {3}),
        ("v12", {1, 2}),
        ("v13", {1, 3}),
        ("v23", {2, 3}),
    )

    TILE_POSITIONS = ((0, 0), (1, 0), (0, 1), (1, 1))

    def __init__(self, *args, **kwargs):
        self._v92_seen_blobs = set()
        self._v92_union_cells = {}
        self._v92_frame_count = 0
        self._v92_last_timestamp = None
        self._v92_reset_count = 0
        self.last_v92_diagnostics = {}
        super().__init__(*args, **kwargs)

    def reset_v92_accumulator(self, reason="nueva sesión"):
        self._v92_seen_blobs.clear()
        self._v92_union_cells.clear()
        self._v92_frame_count = 0
        self._v92_last_timestamp = None
        self._v92_reset_count += 1
        self.last_v92_diagnostics = {
            "reset_reason": str(reason),
            "reset_count": self._v92_reset_count,
        }

    # ------------------------------------------------------ layouts físicos
    @staticmethod
    def _quad_values(byte, msb_first=True):
        shifts = (6, 4, 2, 0) if msb_first else (0, 2, 4, 6)
        return [((int(byte) >> shift) & 0x03) for shift in shifts]

    @classmethod
    def _layout_horizontal4(cls, grid_raw, msb_first):
        cells = [0] * (cls.GRID_SIDE * cls.GRID_SIDE)
        for byte_index, byte in enumerate(bytes(grid_raw)):
            y = byte_index // 30
            bx = byte_index % 30
            values = cls._quad_values(byte, msb_first)
            for local_x, value in enumerate(values):
                x = bx * 4 + local_x
                cells[y * cls.GRID_SIDE + x] = value
        return cells

    @classmethod
    def _layout_vertical4(cls, grid_raw, msb_first):
        cells = [0] * (cls.GRID_SIDE * cls.GRID_SIDE)
        for byte_index, byte in enumerate(bytes(grid_raw)):
            by = byte_index // cls.GRID_SIDE
            x = byte_index % cls.GRID_SIDE
            values = cls._quad_values(byte, msb_first)
            for local_y, value in enumerate(values):
                y = by * 4 + local_y
                cells[y * cls.GRID_SIDE + x] = value
        return cells

    @classmethod
    def _layout_tile2(cls, grid_raw, permutation):
        cells = [0] * (cls.GRID_SIDE * cls.GRID_SIDE)
        for byte_index, byte in enumerate(bytes(grid_raw)):
            by = byte_index // 60
            bx = byte_index % 60
            values = cls._quad_values(byte, True)
            for value_index, pos_index in enumerate(permutation):
                dx, dy = cls.TILE_POSITIONS[pos_index]
                x = bx * 2 + dx
                y = by * 2 + dy
                cells[y * cls.GRID_SIDE + x] = values[value_index]
        return cells

    @classmethod
    def _raw_layouts(cls, grid_raw):
        raw = bytes(grid_raw or b"")
        if len(raw) != cls.GRID_BYTES:
            return []

        layouts = [
            ("h4-msb", cls._layout_horizontal4(raw, True)),
            ("h4-lsb", cls._layout_horizontal4(raw, False)),
            ("v4-msb", cls._layout_vertical4(raw, True)),
            ("v4-lsb", cls._layout_vertical4(raw, False)),
        ]
        for perm in itertools.permutations(range(4)):
            label = "tile2-" + "".join(str(x) for x in perm)
            layouts.append((label, cls._layout_tile2(raw, perm)))
        return layouts

    @classmethod
    def _base_distance(cls, cells, base_cell):
        try:
            bx, by = float(base_cell[0]), float(base_cell[1])
        except Exception:
            bx, by = cls.BASE_FALLBACK_CELL
        best = None
        side = cls.GRID_SIDE
        for idx, value in enumerate(cells or []):
            if not int(value):
                continue
            x, y = idx % side, idx // side
            distance = math.hypot(float(x) - bx, float(y) - by)
            if best is None or distance < best:
                best = distance
        return best

    @classmethod
    def _candidate_score(cls, cells, metrics, base_cell=BASE_FALLBACK_CELL):
        base_distance = cls._base_distance(cells, base_cell)
        if base_distance is None:
            base_distance = 999.0
        return (
            (1_000_000_000 if metrics.get("valid") else 0)
            + int(metrics.get("largest", 0) or 0) * 10000
            + int(float(metrics.get("largest_ratio", 0.0) or 0.0) * 100000)
            + int(float(metrics.get("adjacency_ratio", 0.0) or 0.0) * 10000)
            + int(metrics.get("nonzero", 0) or 0) * 10
            - int(metrics.get("components", 0) or 0) * 100
            - int(float(base_distance) * 20)
        )

    @classmethod
    def _decode_grid(cls, grid_raw: bytes):
        """Prueba disposición física + máscara; V57 sigue siendo el gate."""
        options = []
        for layout_name, raw_cells in cls._raw_layouts(grid_raw):
            raw_counts = dict(Counter(raw_cells))
            for mask_name, allowed in cls.MASKS:
                cells = [1 if int(value) in allowed else 0 for value in raw_cells]
                metrics = cls._grid_metrics(cells)
                base_distance = cls._base_distance(cells, cls.BASE_FALLBACK_CELL)
                score = cls._candidate_score(
                    cells,
                    metrics,
                    cls.BASE_FALLBACK_CELL,
                )
                options.append({
                    "label": f"{layout_name}|{mask_name}",
                    "layout": layout_name,
                    "mask": mask_name,
                    "cells": cells,
                    "score": score,
                    "counts": dict(Counter(cells)),
                    "raw_counts": raw_counts,
                    "metrics": dict(metrics),
                    "base_distance": base_distance,
                    "source": "frame",
                })

        options.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                int(item.get("score", 0) or 0),
            ),
            reverse=True,
        )
        return options[0], options

    # ------------------------------------------------------- unión temporal
    @staticmethod
    def _merge_binary_cells(previous, current):
        if previous is None:
            return list(current or [])
        if len(previous) != len(current or []):
            return list(current or [])
        return [
            1 if int(a) or int(b) else 0
            for a, b in zip(previous, current)
        ]

    def _v92_maybe_reset_for_timestamp(self, timestamp):
        try:
            current = float(timestamp)
        except Exception:
            return
        previous = self._v92_last_timestamp
        if previous is not None:
            gap = current - float(previous)
            if gap < -60 or gap > self.ACCUM_RESET_GAP_SECONDS:
                self.reset_v92_accumulator(
                    f"salto timestamp {gap:.0f}s"
                )
        self._v92_last_timestamp = current

    def _v92_accumulate(self, options, blob_sha12, timestamp):
        self._v92_maybe_reset_for_timestamp(timestamp)
        signature = str(blob_sha12 or "")
        is_new = bool(signature) and signature not in self._v92_seen_blobs
        if is_new and len(self._v92_seen_blobs) < self.ACCUM_MAX_UNIQUE_FRAMES:
            self._v92_seen_blobs.add(signature)
            self._v92_frame_count += 1
            for option in options:
                label = str(option.get("label") or "")
                self._v92_union_cells[label] = self._merge_binary_cells(
                    self._v92_union_cells.get(label),
                    option.get("cells") or [],
                )

        accumulated = []
        for label, cells in self._v92_union_cells.items():
            metrics = self._grid_metrics(cells)
            base_distance = self._base_distance(cells, self.BASE_FALLBACK_CELL)
            accumulated.append({
                "label": f"acum[{self._v92_frame_count}]|{label}",
                "layout": label.split("|", 1)[0],
                "mask": label.split("|", 1)[1] if "|" in label else "",
                "cells": list(cells),
                "score": self._candidate_score(
                    cells,
                    metrics,
                    self.BASE_FALLBACK_CELL,
                ),
                "counts": dict(Counter(cells)),
                "raw_counts": {},
                "metrics": dict(metrics),
                "base_distance": base_distance,
                "source": "acumulado",
            })
        accumulated.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                int(item.get("score", 0) or 0),
            ),
            reverse=True,
        )
        return accumulated, is_new

    @classmethod
    def _valid_device_base_cell(cls, base_grid):
        if isinstance(base_grid, dict):
            try:
                x = float(base_grid.get("x"))
                y = float(base_grid.get("y"))
                if (
                    math.isfinite(x) and math.isfinite(y)
                    and 0.0 <= x < cls.GRID_SIDE
                    and 0.0 <= y < cls.GRID_SIDE
                    and not (x >= 250.0 and y >= 250.0)
                ):
                    return (x, y), False
            except Exception:
                pass
        return tuple(cls.BASE_FALLBACK_CELL), True

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        # Parent construye toda la telemetría y track temporal; V92 reemplaza
        # únicamente la interpretación geométrica por el mejor candidato.
        snapshot = super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        payload = bytes(decoded.get("payload") or b"")
        header = self._parse_header(payload) or {}
        offset = int(header.get("grid_offset", 0) or 0)
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        current_selected, current_options = self._decode_grid(grid_raw)

        blob_sha12 = self._sha12(raw)
        accumulated, is_new = self._v92_accumulate(
            current_options,
            blob_sha12,
            header.get("timestamp"),
        )

        all_candidates = list(current_options) + list(accumulated)
        all_candidates.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                int(item.get("score", 0) or 0),
            ),
            reverse=True,
        )
        selected = all_candidates[0] if all_candidates else current_selected

        base_grid, _robot_grid = self._device_pose_grid()
        base_cell, base_fallback = self._valid_device_base_cell(base_grid)

        # Recalcula el tie-break con la base real/corregida para los candidatos
        # más prometedores. La validez espacial de V57 sigue mandando.
        shortlist = all_candidates[:24]
        for item in shortlist:
            metrics = dict(item.get("metrics") or {})
            item["base_distance"] = self._base_distance(
                item.get("cells") or [],
                base_cell,
            )
            item["score"] = self._candidate_score(
                item.get("cells") or [],
                metrics,
                base_cell,
            )
        shortlist.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                int(item.get("score", 0) or 0),
            ),
            reverse=True,
        )
        if shortlist:
            selected = shortlist[0]

        cells = list(selected.get("cells") or [])
        metrics = self._grid_metrics(cells)
        snapshot.grid_cells = cells
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = self._grid_walls(cells, base_cell=base_cell)
        snapshot.grid_counts = dict(selected.get("counts") or Counter(cells))
        snapshot.grid_order = str(selected.get("label") or "")
        snapshot.grid_score = int(selected.get("score", 0) or 0)
        snapshot.v92_grid_metrics = dict(metrics)
        snapshot.v92_source = str(selected.get("source") or "frame")
        snapshot.v92_base_fallback = bool(base_fallback)

        # 255_255 no vuelve a contaminar la base absoluta del mapa.
        if base_fallback:
            snapshot.raw_base = (
                float(base_cell[0]) * self.GRID_RESOLUTION_M,
                float(base_cell[1]) * self.GRID_RESOLUTION_M,
            )

        def brief(item):
            metrics = dict(item.get("metrics") or {})
            return {
                "label": item.get("label"),
                "source": item.get("source"),
                "valid": bool(metrics.get("valid")),
                "nonzero": metrics.get("nonzero"),
                "components": metrics.get("components"),
                "largest": metrics.get("largest"),
                "largest_ratio": metrics.get("largest_ratio"),
                "adjacency_ratio": metrics.get("adjacency_ratio"),
                "base_distance": (
                    round(float(item.get("base_distance")), 2)
                    if item.get("base_distance") is not None else None
                ),
                "score": item.get("score"),
            }

        self.last_v92_diagnostics = {
            "unique_frames": self._v92_frame_count,
            "unique_hashes": len(self._v92_seen_blobs),
            "new_frame": bool(is_new),
            "reset_count": self._v92_reset_count,
            "base_cell": tuple(base_cell),
            "base_fallback": bool(base_fallback),
            "current_best": brief(current_options[0]) if current_options else None,
            "accum_best": brief(accumulated[0]) if accumulated else None,
            "selected": brief(selected),
            "selected_valid": bool(metrics.get("valid")),
            "layout_count": 28,
            "candidate_count": len(current_options),
            "accum_candidate_count": len(accumulated),
            "top": [brief(item) for item in shortlist[:8]],
        }
        return snapshot

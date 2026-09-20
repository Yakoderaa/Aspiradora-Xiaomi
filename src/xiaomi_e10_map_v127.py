from xiaomi_e10_map_v126 import XiaomiE10MapV126


class XiaomiE10MapV127(XiaomiE10MapV126):
    """V127: convierte carriles nativos densos en superficie continua prudente."""

    SURFACE_CLOSE_RADIUS = 2
    SURFACE_MAX_GROWTH_RATIO = 2.80

    def __init__(self, *args, **kwargs):
        self.last_v127_diagnostics = {}
        super().__init__(*args, **kwargs)

    @staticmethod
    def _v127_dilate(cells, side, radius):
        occupied = {
            idx for idx, value in enumerate(cells or []) if int(value)
        }
        out = [0] * (int(side) * int(side))
        radius = max(0, int(radius))
        for idx in occupied:
            x, y = idx % side, idx // side
            for dy in range(-radius, radius + 1):
                ny = y + dy
                if ny < 0 or ny >= side:
                    continue
                for dx in range(-radius, radius + 1):
                    nx = x + dx
                    if 0 <= nx < side:
                        out[ny * side + nx] = 1
        return out

    @staticmethod
    def _v127_erode(cells, side, radius):
        raw = [1 if int(value) else 0 for value in (cells or [])]
        out = [0] * (int(side) * int(side))
        radius = max(0, int(radius))
        for y in range(side):
            for x in range(side):
                keep = True
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if ny < 0 or ny >= side:
                        keep = False
                        break
                    for dx in range(-radius, radius + 1):
                        nx = x + dx
                        if (
                            nx < 0
                            or nx >= side
                            or not raw[ny * side + nx]
                        ):
                            keep = False
                            break
                    if not keep:
                        break
                if keep:
                    out[y * side + x] = 1
        return out

    def _v127_solidify(self, cells, base_cell):
        original = [1 if int(value) else 0 for value in (cells or [])]
        before = int(sum(original))
        if before <= 0:
            return original, {
                "accepted": False,
                "reason": "grid vacío",
                "before": before,
                "after": before,
            }

        radius = int(self.SURFACE_CLOSE_RADIUS)
        dilated = self._v127_dilate(original, self.GRID_SIDE, radius)
        closed = self._v127_erode(dilated, self.GRID_SIDE, radius)

        merged = [
            1 if int(a) or int(b) else 0
            for a, b in zip(original, closed)
        ]
        filled, holes = self._fill_enclosed_holes(merged)
        main, detached = self._keep_main_component(filled, base_cell)

        after = int(sum(main))
        metrics = dict(self._grid_metrics(main))
        growth = float(after) / float(max(1, before))

        accepted = bool(
            metrics.get("valid")
            and after >= before
            and growth <= float(self.SURFACE_MAX_GROWTH_RATIO)
        )
        if not accepted:
            main = original
            after = before
            growth = 1.0
            metrics = dict(self._grid_metrics(original))

        return main, {
            "accepted": bool(accepted),
            "before": before,
            "after": after,
            "added": max(0, after - before),
            "growth_ratio": round(growth, 4),
            "radius_cells": radius,
            "radius_m": round(radius * float(self.GRID_RESOLUTION_M), 3),
            "holes_filled": int(holes),
            "detached_removed": int(detached),
            "metrics": dict(metrics),
        }

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        snapshot = super()._snapshot_from_grid(
            slot,
            endpoint,
            raw,
            decoded,
        )
        if not self._v107_final_mode:
            return snapshot

        cells = list(getattr(snapshot, "grid_cells", []) or [])
        side = int(getattr(snapshot, "grid_side", 0) or 0)
        base = getattr(snapshot, "grid_base_cell", None)
        if side != self.GRID_SIDE or len(cells) != side * side:
            self.last_v127_diagnostics = {
                "accepted": False,
                "reason": "tamaño de grid inesperado",
            }
            return snapshot

        surface, diag = self._v127_solidify(cells, base)
        self.last_v127_diagnostics = dict(diag)
        if not bool(diag.get("accepted")):
            return snapshot

        metrics = dict(diag.get("metrics") or self._grid_metrics(surface))
        snapshot.grid_cells = list(surface)
        snapshot.grid_walls = self._grid_walls(
            surface,
            base_cell=base,
        )
        snapshot.grid_counts = {
            0: len(surface) - sum(surface),
            1: sum(surface),
        }
        snapshot.grid_order = (
            str(getattr(snapshot, "grid_order", "") or "")
            + "|v127-solid"
        )
        snapshot.v92_grid_metrics = dict(metrics)
        snapshot.v93_grid_metrics = dict(metrics)
        snapshot.v93_source = "v127-solidified-final"
        snapshot.v127_surface = dict(diag)
        return snapshot

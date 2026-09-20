from xiaomi_e10_map_v127 import XiaomiE10MapV127


class XiaomiE10MapV128(XiaomiE10MapV127):
    """V128: pulido leve del contorno, sin inventar superficie extensa."""

    POLISH_MAX_GROWTH_RATIO = 1.12
    POLISH_PASSES = 2

    def __init__(self, *args, **kwargs):
        self.last_v128_diagnostics = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def _v128_polish_once(cls, cells, side):
        raw = [1 if int(value) else 0 for value in (cells or [])]
        out = list(raw)
        added = 0

        for y in range(1, side - 1):
            for x in range(1, side - 1):
                idx = y * side + x
                if raw[idx]:
                    continue

                orthogonal = (
                    raw[(y - 1) * side + x]
                    + raw[(y + 1) * side + x]
                    + raw[y * side + x - 1]
                    + raw[y * side + x + 1]
                )

                around = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        around += raw[(y + dy) * side + (x + dx)]

                # Sólo concavidades muy pequeñas: hueco encerrado por al menos
                # tres lados o rodeado por seis de sus ocho vecinos.
                if orthogonal >= 3 or around >= 6:
                    out[idx] = 1
                    added += 1

        return out, added

    def _v128_polish_surface(self, cells, base_cell):
        original = [1 if int(value) else 0 for value in (cells or [])]
        before = int(sum(original))
        current = list(original)
        total_added = 0

        for _ in range(int(self.POLISH_PASSES)):
            candidate, added = self._v128_polish_once(
                current,
                self.GRID_SIDE,
            )
            if added <= 0:
                break

            after = int(sum(candidate))
            growth = float(after) / float(max(1, before))
            if growth > float(self.POLISH_MAX_GROWTH_RATIO):
                break

            current = candidate
            total_added += int(added)

        current, detached = self._keep_main_component(
            current,
            base_cell,
        )
        after = int(sum(current))
        growth = float(after) / float(max(1, before))
        metrics = dict(self._grid_metrics(current))

        accepted = bool(
            metrics.get("valid")
            and after >= before
            and growth <= float(self.POLISH_MAX_GROWTH_RATIO)
        )
        if not accepted:
            current = original
            after = before
            growth = 1.0
            metrics = dict(self._grid_metrics(original))
            total_added = 0
            detached = 0

        return current, {
            "accepted": bool(accepted),
            "before": before,
            "after": after,
            "added": int(max(0, after - before)),
            "candidate_added": int(total_added),
            "growth_ratio": round(growth, 4),
            "passes": int(self.POLISH_PASSES),
            "max_growth_ratio": float(self.POLISH_MAX_GROWTH_RATIO),
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
            self.last_v128_diagnostics = {
                "accepted": False,
                "reason": "tamaño de grid inesperado",
            }
            return snapshot

        polished, diag = self._v128_polish_surface(cells, base)
        self.last_v128_diagnostics = dict(diag)
        if not bool(diag.get("accepted")):
            return snapshot

        metrics = dict(diag.get("metrics") or self._grid_metrics(polished))
        snapshot.grid_cells = list(polished)
        snapshot.grid_walls = self._grid_walls(
            polished,
            base_cell=base,
        )
        snapshot.grid_counts = {
            0: len(polished) - sum(polished),
            1: sum(polished),
        }
        snapshot.grid_order = (
            str(getattr(snapshot, "grid_order", "") or "")
            + "|v128-polish"
        )
        snapshot.v92_grid_metrics = dict(metrics)
        snapshot.v93_grid_metrics = dict(metrics)
        snapshot.v93_source = "v128-polished-final"
        snapshot.v128_polish = dict(diag)
        return snapshot

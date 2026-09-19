import math
from collections import deque

import app_v90
from xiaomi_e10_map_v91 import XiaomiE10MapV91


class App(app_v90.App):
    """V91: decoder B112 corregido + fallback de superficie física mejorado."""

    FALLBACK_ROBOT_RADIUS_M = 0.18
    FALLBACK_CLOSE_GAP_CELLS = 3

    def __init__(self):
        self._v91_diag = {}
        super().__init__()

    # ======================================================== cliente mapa
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV91(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # ==================================================== fallback estimado
    @classmethod
    def _v91_seed_floor_cells(cls, snapshot):
        points = [
            p for p in list((snapshot or {}).get("points") or [])
            if isinstance(p, dict)
        ]
        size = float(cls.MAP_CELL)
        radius_cells = max(
            1,
            int(math.ceil(float(cls.FALLBACK_ROBOT_RADIUS_M) / size)),
        )
        cells = set()
        previous = None

        def stamp(x, y):
            cx = int(math.floor(float(x) / size))
            cy = int(math.floor(float(y) / size))
            limit = radius_cells + 0.35
            for dx in range(-radius_cells, radius_cells + 1):
                for dy in range(-radius_cells, radius_cells + 1):
                    if math.hypot(dx, dy) <= limit:
                        cells.add((cx + dx, cy + dy))

        for point in points:
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if not all(math.isfinite(v) for v in current):
                continue

            if previous is not None:
                distance = math.hypot(
                    current[0] - previous[0],
                    current[1] - previous[1],
                )
                steps = max(1, int(math.ceil(distance / max(size * 0.5, 0.02))))
                for index in range(1, steps):
                    t = index / float(steps)
                    stamp(
                        previous[0] + (current[0] - previous[0]) * t,
                        previous[1] + (current[1] - previous[1]) * t,
                    )
            stamp(*current)
            previous = current
        return cells

    @classmethod
    def _v91_close_small_gaps(cls, cells):
        result = set(cells or set())
        gap = int(cls.FALLBACK_CLOSE_GAP_CELLS)

        # Dos pasadas ortogonales reconstruyen huecos entre carriles paralelos
        # sin inventar grandes extensiones fuera del recorrido observado.
        for _ in range(2):
            additions = set()
            by_y = {}
            by_x = {}
            for x, y in result:
                by_y.setdefault(y, []).append(x)
                by_x.setdefault(x, []).append(y)

            for y, xs in by_y.items():
                xs = sorted(set(xs))
                for a, b in zip(xs, xs[1:]):
                    if 1 < b - a <= gap + 1:
                        for x in range(a + 1, b):
                            additions.add((x, y))

            for x, ys in by_x.items():
                ys = sorted(set(ys))
                for a, b in zip(ys, ys[1:]):
                    if 1 < b - a <= gap + 1:
                        for y in range(a + 1, b):
                            additions.add((x, y))
            result.update(additions)
        return result

    @staticmethod
    def _v91_fill_enclosed_holes(cells):
        cells = set(cells or set())
        if not cells:
            return cells

        xs = [p[0] for p in cells]
        ys = [p[1] for p in cells]
        min_x, max_x = min(xs) - 1, max(xs) + 1
        min_y, max_y = min(ys) - 1, max(ys) + 1

        outside = set()
        queue = deque([(min_x, min_y)])
        outside.add((min_x, min_y))
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if nx < min_x or nx > max_x or ny < min_y or ny > max_y:
                    continue
                if (nx, ny) in cells or (nx, ny) in outside:
                    continue
                outside.add((nx, ny))
                queue.append((nx, ny))

        # Sólo rellenamos huecos realmente encerrados por la superficie
        # observada; el exterior completo permanece intacto.
        for x in range(min_x + 1, max_x):
            for y in range(min_y + 1, max_y):
                if (x, y) not in cells and (x, y) not in outside:
                    cells.add((x, y))
        return cells

    @classmethod
    def _v87_floor_cells(cls, snapshot):
        cells = cls._v91_seed_floor_cells(snapshot)
        cells = cls._v91_close_small_gaps(cells)
        return cls._v91_fill_enclosed_holes(cells)

    @classmethod
    def _v91_floor_bounds(cls, snapshot):
        cells = cls._v87_floor_cells(snapshot)
        if not cells:
            return None
        size = float(cls.MAP_CELL)
        xs = [x for x, _y in cells]
        ys = [y for _x, y in cells]
        return (
            min(xs) * size,
            min(ys) * size,
            (max(xs) + 1) * size,
            (max(ys) + 1) * size,
        )

    def _v72_bounds(self, snapshot):
        inherited = super()._v72_bounds(snapshot)
        if self._v88_native_grid(snapshot) is not None:
            return inherited
        return self._v88_union_bounds(
            inherited,
            self._v91_floor_bounds(snapshot),
        )

    def _v70_collect_bounds(self, snapshot, plan):
        inherited = super()._v70_collect_bounds(snapshot, plan)
        if self._v88_native_grid(snapshot) is not None:
            return inherited
        return self._v88_union_bounds(
            inherited,
            self._v91_floor_bounds(snapshot),
        )

    # ============================================================ eventos
    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            if client is not None:
                self._v91_diag = dict(
                    getattr(client, "last_v91_diagnostics", {}) or {}
                )
        return result

    # ========================================================= diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}

        native = self._v88_native_grid(snapshot)
        fallback = self._v87_floor_cells(snapshot)
        legacy = app_v90.App._v87_floor_cells(snapshot)
        cell_area = float(self.MAP_CELL) ** 2
        bounds = self._v91_floor_bounds(snapshot)
        bbox = None
        density = None
        if bounds:
            width = max(0.0, float(bounds[2]) - float(bounds[0]))
            height = max(0.0, float(bounds[3]) - float(bounds[1]))
            bbox = (round(width, 2), round(height, 2))
            box_area = width * height
            if box_area > 1e-9:
                density = round((len(fallback) * cell_area) / box_area, 3)

        client = getattr(self, "_v40_client", None)
        diag = dict(
            getattr(client, "last_v91_diagnostics", {}) or self._v91_diag or {}
        )
        header = dict(diag.get("last_header") or {})
        selected = dict(diag.get("selected_grid") or {})
        metrics = dict(selected.get("metrics") or {})

        lines = [
            "DIAGNÓSTICO V91 ACTIVO · cabecera B112 real + superficie reconstruida",
            "======================================================================",
            (
                "cabecera post-hex: "
                f"aceptada={bool(header.get('accepted'))} · "
                f"bytes={header.get('payload_bytes', '—')} · "
                f"tipo={header.get('type', '—')} · versión={header.get('version', '—')} · "
                f"header={header.get('length', '—')} · offset={header.get('grid_offset', '—')}"
            ),
            (
                "grid candidato: "
                f"orden/capa={selected.get('order') or '—'} · "
                f"res={selected.get('resolution', '—')} m · "
                f"válido={bool(metrics.get('valid'))} · "
                f"nonzero={metrics.get('nonzero', '—')} · "
                f"componentes={metrics.get('components', '—')} · "
                f"mayor={metrics.get('largest', '—')} · "
                f"ratio={metrics.get('largest_ratio', '—')} · "
                f"adyacencia={metrics.get('adjacency_ratio', '—')}"
            ),
            (
                "fuente final V91: "
                + ("GRID XIAOMI" if native is not None else "fallback reconstruido")
            ),
            (
                "fallback superficie: "
                f"legacy={len(legacy)} celdas/{len(legacy)*cell_area:.2f} m² · "
                f"V91={len(fallback)} celdas/{len(fallback)*cell_area:.2f} m² · "
                f"bbox={bbox or '—'} m · densidad={density if density is not None else '—'}"
            ),
            "fallback V91: radio físico 0.18 m + cierre de huecos cortos + relleno sólo de huecos encerrados",
            "decoder V91: type8 + version8 + len16be; 3628 B = 28 B cabecera + 3600 B grid",
            "decoder V91: prueba bit-order y capas 2bpp por separado; V57 sigue siendo el validador final",
            "resolución candidata del grid V91: 0.20 m; no cambia todavía RAW_TO_METERS de la lógica física V77/V85",
            "",
            "",
        ]
        return "\n".join(lines) + inherited

import math
import tkinter as tk

import app_v87


class App(app_v87.App):
    """V88: geometría visual Xiaomi validada, persistente y alineada al dock.

    V85/V86 siguen siendo dueños de la trayectoria física, continuidad, dock y
    ETA. V88 sólo cambia la fuente geométrica del renderer: cuando V57 valida
    una rejilla 120x120 real de Xiaomi, se guarda por mapa y se usa como planta.
    Si Xiaomi no entrega una rejilla coherente, se conserva el fallback V87.
    """

    # El fallback de trayectoria usa la misma resolución física del grid B112.
    # Con huella 3x3 equivale a ~30 cm, mucho más cercano al diámetro del E10
    # que los 48 cm visuales de V87.
    MAP_CELL = 0.10
    ROBOT_FOOTPRINT_CELLS = 1

    def __init__(self):
        self._v88_native_updates = 0
        self._v88_native_reuses = 0
        self._v88_base_fallbacks = 0
        self._v88_last_native_source = "—"
        self._v88_last_native_metrics = {}
        self._v88_last_base_raw = None
        self._v88_last_base_cell = None
        self._v88_legend_source = None
        super().__init__()
        self._v88_install_legend()
        # El primer render heredado ocurre antes de reemplazar la leyenda V72.
        # Redibujamos una vez para restaurar inmediatamente el grid persistido.
        try:
            self._render_maps()
        except Exception:
            pass

    # ===================================================== grid persistente
    @staticmethod
    def _v88_correct_base_cell(base_cell, side):
        side = int(side or 0)
        fallback = (float(side) / 2.0, float(side) / 2.0)
        try:
            bx = float(base_cell[0])
            by = float(base_cell[1])
        except Exception:
            return fallback, True

        # 255_255 es el sentinela observado del B112. Cualquier coordenada que
        # cae fuera de la rejilla tampoco puede ser una base visual válida.
        valid = (
            math.isfinite(bx)
            and math.isfinite(by)
            and 0.0 <= bx < float(side)
            and 0.0 <= by < float(side)
        )
        return ((bx, by), False) if valid else (fallback, True)

    @staticmethod
    def _v88_native_grid(snapshot):
        grid = (snapshot or {}).get("native_grid")
        if not isinstance(grid, dict):
            return None
        try:
            side = int(grid.get("side", 0) or 0)
            resolution = float(grid.get("resolution", 0.0) or 0.0)
            base = list(grid.get("base_cell") or [])
            cells = list(grid.get("cells") or [])
        except Exception:
            return None
        if (
            side <= 0
            or side > 512
            or not math.isfinite(resolution)
            or resolution <= 0.0
            or len(base) < 2
            or len(cells) != side * side
        ):
            return None
        try:
            bx = float(base[0])
            by = float(base[1])
        except Exception:
            return None
        if not (math.isfinite(bx) and math.isfinite(by)):
            return None
        if not any(int(value) != 0 for value in cells):
            return None
        return {
            "side": side,
            "resolution": resolution,
            "base_cell": (bx, by),
            "cells": cells,
            "source": str(grid.get("source") or "xiaomi-grid"),
            "blob_sha12": str(grid.get("blob_sha12") or ""),
            "timestamp": grid.get("timestamp"),
            "metrics": dict(grid.get("metrics") or {}),
        }

    def _v88_prepare_live_grid(self, snapshot):
        if snapshot is None or not hasattr(snapshot, "grid_cells"):
            return None
        try:
            cells = list(getattr(snapshot, "grid_cells", []) or [])
            side = int(getattr(snapshot, "grid_side", 0) or 0)
            resolution = float(getattr(snapshot, "grid_resolution", 0.0) or 0.0)
        except Exception:
            return None
        if side <= 0 or len(cells) != side * side or resolution <= 0.0:
            return None

        # No alcanza con que tenga 14.400 celdas: V57 ya demostró que blobs
        # viejos pueden descifrarse en islotes falsos. Exigimos el mismo
        # validador espacial antes de persistir o dibujar.
        metrics = {}
        client = getattr(self, "_v40_client", None)
        validator = getattr(client, "_grid_metrics", None)
        if callable(validator):
            try:
                metrics = dict(validator(cells) or {})
            except Exception:
                metrics = {}
        if not metrics.get("valid"):
            return None

        raw_base = tuple(
            getattr(snapshot, "grid_base_cell", (side / 2.0, side / 2.0))
            or (side / 2.0, side / 2.0)
        )
        base_cell, used_fallback = self._v88_correct_base_cell(raw_base, side)
        self._v88_last_base_raw = raw_base
        self._v88_last_base_cell = base_cell
        if used_fallback:
            self._v88_base_fallbacks += 1

        diag = dict(getattr(self, "_v57_diag", {}) or {})
        source = str(diag.get("source") or "xiaomi-grid-2bpp")
        self._v88_last_native_source = source
        self._v88_last_native_metrics = dict(metrics)

        return {
            "side": side,
            "resolution": resolution,
            "base_cell": [float(base_cell[0]), float(base_cell[1])],
            "cells": [int(value) for value in cells],
            "source": source,
            "blob_sha12": str(getattr(snapshot, "grid_blob_sha12", "") or ""),
            "timestamp": getattr(snapshot, "upload_date", None),
            "metrics": metrics,
        }

    @staticmethod
    def _v88_grid_signature(grid):
        if not isinstance(grid, dict):
            return None
        return (
            str(grid.get("blob_sha12") or ""),
            grid.get("timestamp"),
            tuple(grid.get("base_cell") or ()),
            int(grid.get("side", 0) or 0),
            str(grid.get("source") or ""),
        )

    def _handle_ui_event(self, kind, payload):
        snapshot_obj = (
            payload[0]
            if kind == "cloud_ijai_map_state_v40" and payload
            else None
        )
        result = super()._handle_ui_event(kind, payload)

        if kind == "cloud_ijai_map_state_v40" and snapshot_obj is not None:
            native = self._v88_prepare_live_grid(snapshot_obj)
            if native is not None and getattr(self, "local_map", None):
                try:
                    current = self.local_map.snapshot().get("native_grid")
                except Exception:
                    current = None
                if self._v88_grid_signature(current) != self._v88_grid_signature(native):
                    try:
                        self.local_map.set_native_grid(native)
                        self._v88_native_updates += 1
                    except Exception:
                        pass
                else:
                    self._v88_native_reuses += 1
                try:
                    self._render_maps()
                except Exception:
                    pass
        return result

    # ========================================================== geometría
    @classmethod
    def _v88_grid_bounds(cls, grid):
        if not isinstance(grid, dict):
            return None
        try:
            side = int(grid["side"])
            resolution = float(grid["resolution"])
            bx, by = grid["base_cell"]
            cells = grid["cells"]
        except Exception:
            return None

        occupied = [
            index for index, value in enumerate(cells)
            if int(value) != 0
        ]
        if not occupied:
            return None
        min_gx = min(index % side for index in occupied)
        max_gx = max(index % side for index in occupied)
        min_gy = min(index // side for index in occupied)
        max_gy = max(index // side for index in occupied)

        x0 = (float(min_gx) - float(bx)) * resolution
        x1 = (float(max_gx + 1) - float(bx)) * resolution
        y_top = (float(by) - float(min_gy)) * resolution
        y_bottom = (float(by) - float(max_gy + 1)) * resolution
        return (
            min(x0, x1),
            min(y_bottom, y_top),
            max(x0, x1),
            max(y_bottom, y_top),
        )

    @staticmethod
    def _v88_union_bounds(first, second):
        if first is None:
            return second
        if second is None:
            return first
        return (
            min(float(first[0]), float(second[0])),
            min(float(first[1]), float(second[1])),
            max(float(first[2]), float(second[2])),
            max(float(first[3]), float(second[3])),
        )

    def _v72_bounds(self, snapshot):
        inherited = super()._v72_bounds(snapshot)
        grid = self._v88_native_grid(snapshot)
        return self._v88_union_bounds(
            inherited,
            self._v88_grid_bounds(grid),
        )

    def _v88_draw_native_floor(
        self,
        canvas,
        grid,
        xy,
        outline_width=2.0,
    ):
        side = int(grid["side"])
        res = float(grid["resolution"])
        bx, by = grid["base_cell"]
        cells = grid["cells"]

        # Superficie: runs horizontales sin bordes entre celdas. La rejilla
        # existe internamente, pero visualmente se percibe como una sola planta.
        for gy in range(side):
            gx = 0
            while gx < side:
                if int(cells[gy * side + gx]) == 0:
                    gx += 1
                    continue
                end = gx + 1
                while end < side and int(cells[gy * side + end]) != 0:
                    end += 1

                x0 = (float(gx) - float(bx)) * res
                x1 = (float(end) - float(bx)) * res
                y0 = (float(by) - float(gy)) * res
                y1 = (float(by) - float(gy + 1)) * res
                sx0, sy0 = xy(x0, y0)
                sx1, sy1 = xy(x1, y1)
                canvas.create_rectangle(
                    min(sx0, sx1),
                    min(sy0, sy1),
                    max(sx0, sx1),
                    max(sy0, sy1),
                    fill=self.MAP_FLOOR,
                    outline="",
                    tags=("v88_xiaomi_floor",),
                )
                gx = end

        occupied = {
            index for index, value in enumerate(cells)
            if int(value) != 0
        }

        def has(gx, gy):
            return (
                0 <= gx < side
                and 0 <= gy < side
                and (gy * side + gx) in occupied
            )

        # Contorno exacto de las celdas conocidas; no hay cuadrícula interior.
        for index in occupied:
            gx = index % side
            gy = index // side
            x0 = (float(gx) - float(bx)) * res
            x1 = (float(gx + 1) - float(bx)) * res
            y0 = (float(by) - float(gy)) * res
            y1 = (float(by) - float(gy + 1)) * res
            if not has(gx - 1, gy):
                canvas.create_line(
                    *xy(x0, y0), *xy(x0, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v88_xiaomi_outline",),
                )
            if not has(gx + 1, gy):
                canvas.create_line(
                    *xy(x1, y0), *xy(x1, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v88_xiaomi_outline",),
                )
            if not has(gx, gy - 1):
                canvas.create_line(
                    *xy(x0, y0), *xy(x1, y0),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v88_xiaomi_outline",),
                )
            if not has(gx, gy + 1):
                canvas.create_line(
                    *xy(x0, y1), *xy(x1, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v88_xiaomi_outline",),
                )

    # ============================================================= leyenda
    def _v88_install_legend(self):
        canvas = getattr(self, "map_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return

        old = getattr(self, "_v72_legend", None)
        try:
            if old is not None:
                old.destroy()
        except Exception:
            pass

        legend = tk.Frame(
            canvas,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#d8e3ec",
        )
        legend.place(x=14, y=14)

        row = tk.Frame(legend, bg="#ffffff")
        row.pack(padx=9, pady=6)

        swatch = tk.Canvas(
            row,
            width=18,
            height=11,
            bg="#ffffff",
            highlightthickness=0,
        )
        swatch.pack(side="left")
        swatch.create_rectangle(
            1, 1, 17, 10,
            fill=self.MAP_FLOOR,
            outline=self.MAP_OUTLINE,
            width=1,
        )

        self._v88_legend_source = tk.Label(
            row,
            text="Mapa estimado",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 8, "bold"),
        )
        self._v88_legend_source.pack(side="left", padx=(4, 13))

        line = tk.Canvas(
            row,
            width=23,
            height=10,
            bg="#ffffff",
            highlightthickness=0,
        )
        line.pack(side="left")
        line.create_line(1, 5, 22, 5, fill=self.MAP_ROUTE, width=3)
        tk.Label(
            row,
            text="Recorrido",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(4, 0))

        self._v72_legend = legend
        legend.lift()

    def _v88_update_legend(self, native):
        label = getattr(self, "_v88_legend_source", None)
        if label is not None:
            try:
                label.configure(
                    text="Mapa Xiaomi" if native else "Mapa estimado"
                )
            except Exception:
                pass
        legend = getattr(self, "_v72_legend", None)
        if legend is not None:
            try:
                legend.lift()
            except Exception:
                pass

    # ============================================================ renderer
    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        grid = self._v88_native_grid(snapshot)

        if grid is None:
            if canvas is getattr(self, "map_canvas", None):
                self._v88_update_legend(False)
            return result

        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return result

        canvas.configure(bg=self.MAP_BG)
        canvas.delete("all")
        xy = self._v87_xy(canvas, transform)

        self._v88_draw_native_floor(
            canvas,
            grid,
            xy,
            outline_width=2.2,
        )
        self._v87_draw_route(canvas, snapshot, xy, width=2.2)
        self._v87_draw_rooms_and_plan(canvas, snapshot, xy, transform)
        self._v87_draw_base_and_robot(
            canvas,
            snapshot,
            xy,
            miniature=False,
        )

        if (
            self.map_selected_xy is not None
            and canvas is getattr(self, "map_canvas", None)
        ):
            sx, sy = xy(*self.map_selected_xy)
            canvas.create_oval(
                sx - 5,
                sy - 5,
                sx + 5,
                sy + 5,
                fill=self.MAP_OUTLINE,
                outline="#ffffff",
                width=2,
                tags=("v88_selected",),
            )

        if canvas is getattr(self, "map_canvas", None):
            self._v88_update_legend(True)
        return result

    def _v70_render_thumbnail(self, canvas, snapshot, plan=None, active=False):
        grid = self._v88_native_grid(snapshot)
        if grid is None:
            return super()._v70_render_thumbnail(
                canvas,
                snapshot,
                plan,
                active,
            )

        canvas.delete("all")
        canvas.configure(bg=self.MAP_BG)
        cw = max(80, int(canvas.winfo_width() or 175))
        ch = max(54, int(canvas.winfo_height() or 88))

        inherited_bounds = self._v70_collect_bounds(snapshot, plan)
        bounds = self._v88_union_bounds(
            inherited_bounds,
            self._v88_grid_bounds(grid),
        )
        if bounds is None:
            bounds = (-0.5, -0.5, 0.5, 0.5)
        min_x, min_y, max_x, max_y = bounds
        span_x = max(0.35, max_x - min_x)
        span_y = max(0.35, max_y - min_y)
        pad = 8
        scale = min(
            (cw - 2 * pad) / span_x,
            (ch - 2 * pad) / span_y,
        )

        def xy(x, y):
            return (
                pad + (float(x) - min_x) * scale,
                pad + (max_y - float(y)) * scale,
            )

        self._v88_draw_native_floor(
            canvas,
            grid,
            xy,
            outline_width=1.0,
        )
        self._v87_draw_route(canvas, snapshot, xy, width=1.1)
        self._v87_draw_base_and_robot(
            canvas,
            snapshot,
            xy,
            miniature=True,
        )

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot()
        except Exception:
            snapshot = {}
        grid = self._v88_native_grid(snapshot)
        metrics = dict(
            (grid or {}).get("metrics")
            or self._v88_last_native_metrics
            or {}
        )
        nonzero = 0
        if grid is not None:
            nonzero = sum(
                1 for value in grid["cells"]
                if int(value) != 0
            )

        lines = [
            "DIAGNÓSTICO V88 ACTIVO · geometría Xiaomi validada + base alineada",
            "====================================================================",
            (
                "fuente visual: "
                + (
                    f"grid Xiaomi validado · {grid.get('source')}"
                    if grid is not None
                    else "fallback V87 desde recorrido"
                )
            ),
            (
                "grid persistido: "
                f"{grid.get('side')}x{grid.get('side')} · "
                f"{nonzero} celdas · res={grid.get('resolution')} m"
                if grid is not None
                else "grid persistido: no"
            ),
            (
                "base grid raw/corregida: "
                f"{self._v88_last_base_raw!r} -> "
                f"{self._v88_last_base_cell!r} · "
                f"fallbacks={self._v88_base_fallbacks}"
            ),
            (
                "validación espacial: "
                f"válido={bool(metrics.get('valid'))} · "
                f"componentes={metrics.get('components', '—')} · "
                f"mayor={metrics.get('largest', '—')} · "
                f"ratio={metrics.get('largest_ratio', '—')} · "
                f"adyacencia={metrics.get('adjacency_ratio', '—')}"
            ),
            (
                "persistencia grid: "
                f"actualizaciones={self._v88_native_updates} · "
                f"reusos={self._v88_native_reuses}"
            ),
            "leyenda fija: Mapa Xiaomi/Mapa estimado + Recorrido",
            "viewport: rueda=zoom · doble clic rueda=Zoom Extents · inicio centrado en dock",
            "regla V88: sólo un grid aprobado por el validador espacial V57 puede reemplazar la superficie estimada",
            "regla V88: 255_255 o una base fuera del grid se corrige al centro físico 60_60 del B112",
            "regla V88: la geometría Xiaomi se guarda por mapa; cambiar de mapa no reutiliza el grid de otro",
            "regla V88: V85/V86 conservan trayectoria física, continuidad, retorno al dock y ETA sin cambios",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

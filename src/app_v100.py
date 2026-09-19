import math
import tkinter as tk

import app_v99
import app_v9


class App(app_v99.App):
    """V100: Xiaomi live-first + fondo de mapa estable sin flicker."""

    MAP_BG = "#dfe9f2"
    CLOUD_FILE_POLL_SECONDS = 6.0
    CLOUD_UPLOAD_INTERVAL_SECONDS = 6.0

    LIVE_MIN_NONZERO = 8
    LIVE_MAX_COMPONENTS = 3
    LIVE_MIN_LARGEST_RATIO = 0.82
    LIVE_MIN_ADJACENCY = 0.75
    LIVE_MAX_BASE_DISTANCE = 8.0

    def __init__(self):
        self._v100_live_grids = {}
        self._v100_live_accepts = 0
        self._v100_live_rejects = 0
        self._v100_live_promotions = 0
        self._v100_live_reuses = 0
        self._v100_last_live_metrics = {}
        self._v100_last_live_reason = "—"
        self._v100_map_bg_fixes = 0
        self._v100_thumbnail_bg_fixes = 0
        super().__init__()

    # ===================================================== fondo fijo sin flicker
    def _v100_is_map_canvas(self, widget):
        try:
            if widget is getattr(self, "map_canvas", None):
                return True
            if str(widget.winfo_class()) != "Canvas":
                return False
        except Exception:
            return False

        overview = getattr(self, "_v70_overview_frame", None)
        if overview is None:
            return False
        try:
            parent = widget.master
            while parent is not None:
                if parent is overview:
                    return True
                parent = getattr(parent, "master", None)
        except Exception:
            return False
        return False

    def _v98_theme_walk(self, widget, palette):
        if self._v100_is_map_canvas(widget):
            try:
                widget.configure(
                    bg=self.MAP_BG,
                    background=self.MAP_BG,
                    highlightbackground=self.MAP_BG,
                    highlightcolor=self.MAP_BG,
                )
                self._v100_map_bg_fixes += 1
            except Exception:
                pass
            try:
                children = widget.winfo_children()
            except Exception:
                children = []
            for child in children:
                super()._v98_theme_walk(child, palette)
            return
        return super()._v98_theme_walk(widget, palette)

    def _v100_force_canvas_bg(self, canvas, thumbnail=False):
        try:
            canvas.configure(
                bg=self.MAP_BG,
                background=self.MAP_BG,
                highlightbackground=self.MAP_BG,
                highlightcolor=self.MAP_BG,
            )
            if thumbnail:
                self._v100_thumbnail_bg_fixes += 1
            else:
                self._v100_map_bg_fixes += 1
        except Exception:
            pass

    # ============================================== Xiaomi parcial para mostrar
    def _v100_live_grid_from_snapshot(self, snapshot):
        if snapshot is None or not hasattr(snapshot, "grid_cells"):
            self._v100_last_live_reason = "snapshot sin grid_cells"
            return None
        try:
            cells = [int(v) for v in list(getattr(snapshot, "grid_cells", []) or [])]
            side = int(getattr(snapshot, "grid_side", 0) or 0)
            resolution = float(getattr(snapshot, "grid_resolution", 0.0) or 0.0)
        except Exception:
            self._v100_last_live_reason = "grid ilegible"
            return None

        if side <= 0 or len(cells) != side * side or resolution <= 0.0:
            self._v100_last_live_reason = "dimensiones/resolución inválidas"
            return None

        client = getattr(self, "_v40_client", None)
        validator = getattr(client, "_grid_metrics", None)
        try:
            metrics = dict(validator(cells) or {}) if callable(validator) else {}
        except Exception:
            metrics = {}

        nonzero = int(metrics.get("nonzero", 0) or 0)
        components = int(metrics.get("components", 999) or 999)
        ratio = float(metrics.get("largest_ratio", 0.0) or 0.0)
        adjacency = float(metrics.get("adjacency_ratio", 0.0) or 0.0)

        raw_base = tuple(
            getattr(snapshot, "grid_base_cell", (side / 2.0, side / 2.0))
            or (side / 2.0, side / 2.0)
        )
        base_cell, _fallback = self._v88_correct_base_cell(raw_base, side)

        # V92 ya calculó el candidato espacial ganador. Para live-view no
        # exigimos el umbral de mapa completo de V57; sí exigimos coherencia.
        base_distance = None
        try:
            diag = dict(
                getattr(client, "last_v92_diagnostics", {}) or {}
            )
            selected = dict(diag.get("selected") or {})
            if selected.get("base_distance") is not None:
                base_distance = float(selected.get("base_distance"))
        except Exception:
            base_distance = None

        coherent = (
            nonzero >= int(self.LIVE_MIN_NONZERO)
            and components <= int(self.LIVE_MAX_COMPONENTS)
            and ratio >= float(self.LIVE_MIN_LARGEST_RATIO)
            and adjacency >= float(self.LIVE_MIN_ADJACENCY)
            and (
                base_distance is None
                or base_distance <= float(self.LIVE_MAX_BASE_DISTANCE)
            )
        )
        self._v100_last_live_metrics = {
            **metrics,
            "base_distance": base_distance,
        }
        if not coherent:
            self._v100_live_rejects += 1
            self._v100_last_live_reason = (
                f"rechazado n={nonzero} comp={components} "
                f"ratio={ratio:.2f} ady={adjacency:.2f} baseΔ={base_distance}"
            )
            return None

        self._v100_live_accepts += 1
        self._v100_last_live_reason = (
            f"aceptado n={nonzero} comp={components} "
            f"ratio={ratio:.2f} ady={adjacency:.2f}"
        )
        return {
            "side": side,
            "resolution": resolution,
            "base_cell": [float(base_cell[0]), float(base_cell[1])],
            "cells": cells,
            "source": "xiaomi-live-partial",
            "blob_sha12": str(getattr(snapshot, "grid_blob_sha12", "") or ""),
            "timestamp": getattr(snapshot, "upload_date", None),
            "metrics": metrics,
            "preview": True,
        }

    @staticmethod
    def _v100_grid_signature(grid):
        if not isinstance(grid, dict):
            return None
        cells = list(grid.get("cells") or [])
        nonzero = tuple(i for i, value in enumerate(cells) if int(value))
        return (
            int(grid.get("side", 0) or 0),
            float(grid.get("resolution", 0.0) or 0.0),
            tuple(grid.get("base_cell") or ()),
            hash(nonzero),
        )

    def _v100_store_live_grid(self, grid):
        if not isinstance(grid, dict):
            return False
        map_id = self._v72_active_map_id() or "__default__"
        old = self._v100_live_grids.get(map_id)
        if self._v100_grid_signature(old) == self._v100_grid_signature(grid):
            self._v100_live_reuses += 1
            return False
        self._v100_live_grids[map_id] = dict(grid)
        self._v100_live_promotions += 1
        return True

    def _handle_ui_event(self, kind, payload):
        snapshot_obj = (
            payload[0]
            if kind == "cloud_ijai_map_state_v40" and payload
            else None
        )

        if kind == "cloud_ijai_map_state_v40" and snapshot_obj is not None:
            preview = self._v100_live_grid_from_snapshot(snapshot_obj)
            if preview is not None:
                self._v100_store_live_grid(preview)

        result = super()._handle_ui_event(kind, payload)

        if kind == "cloud_ijai_map_state_v40" and snapshot_obj is not None:
            # Si V88 pudo persistir un grid completo, la vista normal lo usará.
            # Si todavía no, el preview Xiaomi parcial ya queda disponible.
            try:
                self._render_maps()
            except Exception:
                pass
        return result

    def _v88_native_grid(self, snapshot):
        persisted = super()._v88_native_grid(snapshot)
        if persisted is not None:
            return persisted
        if bool(getattr(self, "mapping_active", False)):
            map_id = self._v72_active_map_id() or "__default__"
            preview = self._v100_live_grids.get(map_id)
            if isinstance(preview, dict):
                return dict(preview)
        return None

    def _v74_reset_session(self):
        result = super()._v74_reset_session()
        map_id = self._v72_active_map_id() or "__default__"
        self._v100_live_grids.pop(map_id, None)
        self._v100_last_live_reason = "nueva sesión"
        return result

    # ============================================================ renderer fijo
    def _render_map_canvas(self, canvas, snapshot):
        self._v100_force_canvas_bg(canvas, thumbnail=False)
        result = super()._render_map_canvas(canvas, snapshot)
        self._v100_force_canvas_bg(canvas, thumbnail=False)
        return result

    def _v70_render_thumbnail(self, canvas, snapshot, plan=None, active=False):
        self._v100_force_canvas_bg(canvas, thumbnail=True)
        result = super()._v70_render_thumbnail(canvas, snapshot, plan, active)
        self._v100_force_canvas_bg(canvas, thumbnail=True)
        return result

    def _v88_update_legend(self, native):
        result = super()._v88_update_legend(native)
        label = getattr(self, "_v88_legend_source", None)
        if label is not None and native:
            try:
                grid = self._v88_native_grid(
                    self.local_map.snapshot() if self.local_map else {}
                )
                if isinstance(grid, dict) and grid.get("preview"):
                    label.configure(text=self._v98_translate("Mapa Xiaomi"))
            except Exception:
                pass
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        grid = self._v88_native_grid(snapshot)
        preview = bool((grid or {}).get("preview"))
        nonzero = 0
        if isinstance(grid, dict):
            nonzero = sum(1 for value in list(grid.get("cells") or []) if int(value))
        metrics = dict(self._v100_last_live_metrics or {})
        lines = [
            "DIAGNÓSTICO V100 ACTIVO · Xiaomi live-first + canvas estable",
            "================================================================",
            (
                f"fuente visual: {'XIAOMI LIVE PARCIAL' if preview else ('XIAOMI VALIDADO' if grid else 'sin grid')} · "
                f"celdas={nonzero} · cloud={self.CLOUD_FILE_POLL_SECONDS:.1f}s"
            ),
            (
                f"live Xiaomi: aceptados={self._v100_live_accepts} · rechazados={self._v100_live_rejects} · "
                f"promociones={self._v100_live_promotions} · reusos={self._v100_live_reuses}"
            ),
            (
                "último candidato live: "
                f"n={metrics.get('nonzero','—')} · comp={metrics.get('components','—')} · "
                f"ratio={metrics.get('largest_ratio','—')} · ady={metrics.get('adjacency_ratio','—')} · "
                f"baseΔ={metrics.get('base_distance','—')} · {self._v100_last_live_reason}"
            ),
            (
                f"fondo fijo: grande/mini fixes={self._v100_map_bg_fixes}/"
                f"{self._v100_thumbnail_bg_fixes} · color={self.MAP_BG}"
            ),
            "regla V100: Xiaomi parcial coherente puede mostrarse antes del gate V57; V57 sigue mandando para persistencia definitiva",
            "regla V100: el tema nunca modifica el fondo de los canvases de mapa",
            "regla V100: no se vuelve al fallback si existe un grid Xiaomi live utilizable",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

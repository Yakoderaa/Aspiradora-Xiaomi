import math
import tkinter as tk

import app_v100
import app_v9


class App(app_v100.App):
    """V101: conecta el grid Xiaomi live con el renderer real."""

    def __init__(self):
        self._v101_render_errors = 0
        self._v101_last_render_error = None
        self._v101_main_native_objects = 0
        self._v101_thumb_native_objects = 0
        self._v101_forced_main_redraws = 0
        self._v101_forced_thumb_redraws = 0
        self._v101_transform_adapter_hits = 0
        self._v101_live_overview_forces = 0
        super().__init__()

    # ================================================== fix raíz V88/V87
    def _v87_xy(self, point_or_canvas, transform=None):
        """Compatibilidad doble para el renderer heredado.

        V87 usa _v87_xy(point) para extraer (x,y).
        V88 intentó usar _v87_xy(canvas, transform) como fábrica de world->canvas.
        V101 soporta ambos contratos explícitamente.
        """
        if transform is None:
            return super()._v87_xy(point_or_canvas)

        self._v101_transform_adapter_hits += 1
        scale = float(transform.get("scale", 1.0) or 1.0)
        min_x = float(transform.get("min_x", 0.0) or 0.0)
        max_y = float(transform.get("max_y", 0.0) or 0.0)
        pad = float(transform.get("pad", 28.0) or 28.0)
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)

        def xy(x, y):
            return (
                pad + (float(x) - min_x) * scale + pan_x,
                pad + (max_y - float(y)) * scale + pan_y,
            )

        return xy

    # ======================================================== render guard
    @staticmethod
    def _v101_tag_count(canvas, tag):
        try:
            return len(canvas.find_withtag(tag))
        except Exception:
            return 0

    def _v101_force_native_main(self, canvas, snapshot, grid):
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return 0

        xy = self._v87_xy(canvas, transform)
        try:
            canvas.delete("v88_xiaomi_floor")
            canvas.delete("v88_xiaomi_outline")
        except Exception:
            pass

        self._v88_draw_native_floor(
            canvas,
            grid,
            xy,
            outline_width=2.2,
        )

        # El piso se dibuja detrás de overlays existentes. Reponemos
        # base/robot al frente para que nunca queden tapados.
        try:
            canvas.tag_lower("v88_xiaomi_floor")
        except Exception:
            pass
        try:
            canvas.delete("v87_base")
            canvas.delete("v87_robot")
            self._v87_draw_base_and_robot(
                canvas,
                snapshot,
                xy,
                miniature=False,
            )
        except Exception:
            pass

        try:
            canvas.delete("v99_waiting")
        except Exception:
            pass
        try:
            self._v88_update_legend(True)
        except Exception:
            pass

        self._v101_forced_main_redraws += 1
        return self._v101_tag_count(canvas, "v88_xiaomi_floor")

    def _render_map_canvas(self, canvas, snapshot):
        try:
            result = super()._render_map_canvas(canvas, snapshot)
        except Exception as exc:
            self._v101_render_errors += 1
            self._v101_last_render_error = (
                str(exc).strip() or type(exc).__name__
            )
            result = None

        if canvas is not getattr(self, "map_canvas", None):
            return result

        self._v100_force_canvas_bg(canvas, thumbnail=False)
        grid = self._v88_native_grid(snapshot)
        count = self._v101_tag_count(canvas, "v88_xiaomi_floor")

        if grid is not None and count <= 0:
            count = self._v101_force_native_main(
                canvas,
                snapshot,
                grid,
            )

        self._v101_main_native_objects = int(count)
        if grid is not None and count > 0:
            self._v99_last_visual_mode = (
                "GRID XIAOMI LIVE dibujado"
                if bool(grid.get("preview"))
                else "GRID XIAOMI validado dibujado"
            )
        return result

    # ======================================================== miniatura guard
    def _v101_force_native_thumbnail(
        self,
        canvas,
        snapshot,
        plan,
        grid,
    ):
        canvas.delete("all")
        self._v100_force_canvas_bg(canvas, thumbnail=True)

        cw = max(80, int(canvas.winfo_width() or 175))
        ch = max(54, int(canvas.winfo_height() or 88))
        inherited = self._v70_collect_bounds(snapshot, plan or {})
        bounds = self._v88_union_bounds(
            inherited,
            self._v88_grid_bounds(grid),
        )
        if bounds is None:
            bounds = (-2.0, -2.0, 2.0, 2.0)

        min_x, min_y, max_x, max_y = bounds
        span_x = max(0.35, max_x - min_x)
        span_y = max(0.35, max_y - min_y)
        pad = 7.0
        scale = min(
            (float(cw) - 2.0 * pad) / span_x,
            (float(ch) - 2.0 * pad) / span_y,
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
        try:
            canvas.tag_lower("v88_xiaomi_floor")
        except Exception:
            pass

        self._v87_draw_base_and_robot(
            canvas,
            snapshot,
            xy,
            miniature=True,
        )
        self._v101_forced_thumb_redraws += 1
        return self._v101_tag_count(canvas, "v88_xiaomi_floor")

    def _v70_render_thumbnail(
        self,
        canvas,
        snapshot,
        plan=None,
        active=False,
    ):
        try:
            result = super()._v70_render_thumbnail(
                canvas,
                snapshot,
                plan,
                active,
            )
        except Exception as exc:
            self._v101_render_errors += 1
            self._v101_last_render_error = (
                str(exc).strip() or type(exc).__name__
            )
            result = None

        self._v100_force_canvas_bg(canvas, thumbnail=True)
        grid = self._v88_native_grid(snapshot)
        count = self._v101_tag_count(
            canvas,
            "v88_xiaomi_floor",
        )
        if grid is not None and count <= 0:
            count = self._v101_force_native_thumbnail(
                canvas,
                snapshot,
                plan or {},
                grid,
            )
        if active:
            self._v101_thumb_native_objects = int(count)
        return result

    # ================================================ refresh al frame Xiaomi
    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind == "cloud_ijai_map_state_v40":
            try:
                self._v70_refresh_map_overview(force=True)
                self._v101_live_overview_forces += 1
            except Exception:
                pass
            try:
                self._render_maps()
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
        nonzero = 0
        if isinstance(grid, dict):
            nonzero = sum(
                1
                for value in list(grid.get("cells") or [])
                if int(value)
            )

        lines = [
            "DIAGNÓSTICO V101 ACTIVO · grid Xiaomi → canvas verificado",
            "================================================================",
            (
                f"grid disponible={grid is not None} · celdas={nonzero} · "
                f"preview={bool((grid or {}).get('preview'))}"
            ),
            (
                f"objetos dibujados: mapa grande={self._v101_main_native_objects} · "
                f"miniatura activa={self._v101_thumb_native_objects}"
            ),
            (
                f"adapter V88→V87 hits={self._v101_transform_adapter_hits} · "
                f"redraw forzado grande/mini={self._v101_forced_main_redraws}/"
                f"{self._v101_forced_thumb_redraws}"
            ),
            (
                f"refresh miniatura por frame Xiaomi={self._v101_live_overview_forces} · "
                f"errores renderer={self._v101_render_errors} · "
                f"último={self._v101_last_render_error or '—'}"
            ),
            (
                "regla V101: si existe grid Xiaomi y el canvas termina con "
                "0 objetos v88_xiaomi_floor, se fuerza la capa nativa"
            ),
            (
                "regla V101: _v87_xy soporta tanto punto {x,y} como "
                "(canvas, transform), corrigiendo el contrato roto heredado V88"
            ),
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

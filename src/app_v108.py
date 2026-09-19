import math

import app_v97
import app_v107
import app_v9


class App(app_v107.App):
    """V108: pase visual moderno obligatorio, sin renderer viejo visible."""

    def __init__(self):
        self._v108_main_passes = 0
        self._v108_thumb_passes = 0
        self._v108_old_canvas_clears = 0
        self._v108_route_blocks = 0
        self._v108_estimated_renders = 0
        self._v108_native_renders = 0
        self._v108_waiting_renders = 0
        self._v108_last_mode = "—"
        super().__init__()

    # ===================================================== ruta nunca visible
    def _v87_draw_route(self, canvas, snapshot, xy, width=2):
        # V89 ya la oculta; V108 lo reafirma para que ninguna combinación de
        # herencia pueda volver a dibujar el recorrido interno.
        self._v108_route_blocks += 1
        return None

    # =============================================== helpers renderer moderno
    @staticmethod
    def _v108_valid_transform(transform):
        if not isinstance(transform, dict):
            return False
        try:
            scale = float(transform.get("scale", 0.0) or 0.0)
            float(transform.get("min_x", 0.0))
            float(transform.get("max_y", 0.0))
        except Exception:
            return False
        return math.isfinite(scale) and scale > 0.0

    def _v108_transform(self, canvas, snapshot):
        transform = dict(
            getattr(self, "_map_transforms", {}).get(canvas) or {}
        )
        if self._v108_valid_transform(transform):
            return transform

        try:
            bounds = self._v72_bounds(snapshot)
        except Exception:
            bounds = None
        if bounds is None:
            bounds = (-2.0, -2.0, 2.0, 2.0)

        min_x, min_y, max_x, max_y = [float(v) for v in bounds]
        cw = max(300.0, float(canvas.winfo_width() or 300))
        ch = max(250.0, float(canvas.winfo_height() or 250))
        pad = 28.0
        span_x = max(0.5, max_x - min_x)
        span_y = max(0.5, max_y - min_y)
        scale = min(
            max(20.0, cw - 2.0 * pad) / span_x,
            max(20.0, ch - 2.0 * pad) / span_y,
        )
        transform = {
            "scale": scale,
            "min_x": min_x,
            "max_y": max_y,
            "pad": pad,
            "pan_x": 0.0,
            "pan_y": 0.0,
        }
        try:
            self._map_transforms[canvas] = transform
        except Exception:
            pass
        return transform

    @staticmethod
    def _v108_xy_from_transform(transform):
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

    def _v108_estimated_cells(self, snapshot):
        # Para mapas viejos sin grid Xiaomi final reutilizamos únicamente la
        # superficie moderna prudente V97. Nunca reutilizamos su recorrido.
        try:
            return set(app_v97.App._v87_floor_cells(self, snapshot) or set())
        except Exception:
            return set()

    def _v108_draw_estimated_floor(
        self,
        canvas,
        snapshot,
        xy,
        outline_width=3,
    ):
        cells = self._v108_estimated_cells(snapshot)
        if not cells:
            return 0

        for cell in cells:
            x0, y0, x1, y1 = self._v87_cell_bounds(cell)
            a = xy(x0, y0)
            b = xy(x1, y1)
            canvas.create_rectangle(
                min(a[0], b[0]),
                min(a[1], b[1]),
                max(a[0], b[0]),
                max(a[1], b[1]),
                fill=self.MAP_FLOOR,
                outline="",
                width=0,
                tags=("v108_estimated_floor",),
            )

        for cx, cy in cells:
            x0, y0, x1, y1 = self._v87_cell_bounds((cx, cy))
            if (cx - 1, cy) not in cells:
                canvas.create_line(
                    *xy(x0, y0), *xy(x0, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v108_estimated_outline",),
                )
            if (cx + 1, cy) not in cells:
                canvas.create_line(
                    *xy(x1, y0), *xy(x1, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v108_estimated_outline",),
                )
            if (cx, cy - 1) not in cells:
                canvas.create_line(
                    *xy(x0, y0), *xy(x1, y0),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v108_estimated_outline",),
                )
            if (cx, cy + 1) not in cells:
                canvas.create_line(
                    *xy(x0, y1), *xy(x1, y1),
                    fill=self.MAP_OUTLINE,
                    width=outline_width,
                    tags=("v108_estimated_outline",),
                )
        return len(cells)

    def _v108_clear_canvas(self, canvas):
        try:
            canvas.delete("all")
            self._v108_old_canvas_clears += 1
        except Exception:
            pass
        try:
            current = str(canvas.cget("background")).lower()
        except Exception:
            current = ""
        if current != str(self.MAP_BG).lower():
            try:
                canvas.configure(
                    bg=self.MAP_BG,
                    highlightbackground=self.MAP_BG,
                )
            except Exception:
                pass

    def _v108_waiting_for_final(self):
        return bool(
            getattr(self, "mapping_active", False)
            and getattr(self, "_v107_hide_surface_until_final", False)
        )

    def _v108_draw_modern_scene(
        self,
        canvas,
        snapshot,
        xy,
        miniature=False,
        allow_estimated=True,
    ):
        grid = self._v88_native_grid(snapshot)
        waiting = self._v108_waiting_for_final()

        if isinstance(grid, dict):
            self._v88_draw_native_floor(
                canvas,
                grid,
                xy,
                outline_width=1.0 if miniature else 3.0,
            )
            self._v108_native_renders += 1
            self._v108_last_mode = "XIAOMI FINAL · moderno"
            self._v88_update_legend(True)
        elif allow_estimated and not waiting:
            count = self._v108_draw_estimated_floor(
                canvas,
                snapshot,
                xy,
                outline_width=1.0 if miniature else 3.0,
            )
            if count:
                self._v108_estimated_renders += 1
                self._v108_last_mode = "ESTIMADO · moderno"
            else:
                self._v108_last_mode = "VACÍO · moderno"
            self._v88_update_legend(False)
        else:
            self._v108_waiting_renders += 1
            self._v108_last_mode = "ESPERANDO FINAL · moderno"
            self._v88_update_legend(False)

        # Zonas y habitaciones pueden seguir mostrándose, pero el recorrido
        # físico interno no se dibuja.
        if not miniature:
            try:
                self._v87_draw_rooms_and_plan(
                    canvas,
                    snapshot,
                    xy,
                )
            except Exception:
                pass

        self._v87_draw_base_and_robot(
            canvas,
            snapshot,
            xy,
            miniature=miniature,
        )

        # Garantiza orden Z: piso debajo, pose encima.
        for tag in (
            "v88_xiaomi_floor",
            "v108_estimated_floor",
        ):
            try:
                canvas.tag_lower(tag)
            except Exception:
                pass
        for tag in ("v87_base", "v87_robot"):
            try:
                canvas.tag_raise(tag)
            except Exception:
                pass

    # ======================================================== mapa principal
    def _render_map_canvas(self, canvas, snapshot):
        # Dejamos que la cadena heredada mantenga transform/pan/zoom y todas las
        # estructuras internas. Después borramos SU dibujo y hacemos el pase
        # visual definitivo V108. Por eso el renderer viejo nunca queda visible.
        try:
            result = super()._render_map_canvas(canvas, snapshot)
        except Exception:
            result = None

        transform = self._v108_transform(canvas, snapshot)
        xy = self._v108_xy_from_transform(transform)

        self._v108_clear_canvas(canvas)
        self._v108_draw_modern_scene(
            canvas,
            snapshot,
            xy,
            miniature=False,
            allow_estimated=True,
        )

        selected = getattr(self, "selected_point", None)
        if canvas is getattr(self, "map_canvas", None) and selected:
            try:
                sx, sy = xy(selected[0], selected[1])
                canvas.create_oval(
                    sx - 7,
                    sy - 7,
                    sx + 7,
                    sy + 7,
                    outline="#2563eb",
                    width=2,
                    tags=("v108_selection",),
                )
            except Exception:
                pass

        # Durante un mapeo nuevo sin planta final, indicamos la espera sin
        # reintroducir ningún dibujo viejo.
        if self._v108_waiting_for_final():
            try:
                canvas.create_text(
                    max(1, canvas.winfo_width()) / 2.0,
                    max(1, canvas.winfo_height()) - 24,
                    text="La planta Xiaomi aparecerá al finalizar",
                    fill="#64748b",
                    font=("Segoe UI", 9, "bold"),
                    tags=("v108_waiting",),
                )
            except Exception:
                pass

        legend = getattr(self, "_v72_legend", None)
        if legend is not None:
            try:
                legend.lift()
            except Exception:
                pass

        self._v108_main_passes += 1
        return result

    # ============================================================ miniaturas
    def _v108_thumbnail_bounds(self, snapshot, plan, grid):
        if isinstance(grid, dict):
            bounds = self._v88_grid_bounds(grid)
            if bounds is not None:
                return bounds

        if self._v108_waiting_for_final():
            return (-2.0, -2.0, 2.0, 2.0)

        try:
            bounds = self._v70_collect_bounds(snapshot, plan or {})
        except Exception:
            bounds = None
        return bounds or (-2.0, -2.0, 2.0, 2.0)

    def _v70_render_thumbnail(
        self,
        canvas,
        snapshot,
        plan=None,
        active=False,
    ):
        # Igual que el mapa grande: cualquier thumbnail heredada se descarta.
        try:
            super()._v70_render_thumbnail(
                canvas,
                snapshot,
                plan,
                active,
            )
        except Exception:
            pass

        self._v108_clear_canvas(canvas)

        grid = self._v88_native_grid(snapshot)
        bounds = self._v108_thumbnail_bounds(
            snapshot,
            plan or {},
            grid,
        )
        left, bottom, right, top = [float(v) for v in bounds]
        width = max(80.0, float(canvas.winfo_width() or 175))
        height = max(54.0, float(canvas.winfo_height() or 88))
        margin = 7.0
        span_x = max(0.35, right - left)
        span_y = max(0.35, top - bottom)
        scale = min(
            (width - 2.0 * margin) / span_x,
            (height - 2.0 * margin) / span_y,
        )

        def xy(x, y):
            return (
                margin + (float(x) - left) * scale,
                height - margin - (float(y) - bottom) * scale,
            )

        self._v108_draw_modern_scene(
            canvas,
            snapshot,
            xy,
            miniature=True,
            allow_estimated=True,
        )
        self._v108_thumb_passes += 1
        return None

    # ============================================================= leyenda
    def _v88_update_legend(self, native):
        result = super()._v88_update_legend(native)
        label = getattr(self, "_v88_legend_source", None)
        if label is None:
            return result
        try:
            if self._v108_waiting_for_final():
                label.configure(text="Esperando mapa final Xiaomi")
            elif native:
                label.configure(text="Mapa Xiaomi final")
            else:
                label.configure(text="Mapa estimado")
        except Exception:
            pass
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V108 ACTIVO · renderer moderno obligatorio",
            "================================================================",
            (
                f"pases modernos: grande={self._v108_main_passes} · "
                f"miniatura={self._v108_thumb_passes} · "
                f"canvas heredado limpiado={self._v108_old_canvas_clears}"
            ),
            (
                f"modo visual actual={self._v108_last_mode} · "
                f"nativo={self._v108_native_renders} · "
                f"estimado={self._v108_estimated_renders} · "
                f"espera={self._v108_waiting_renders}"
            ),
            (
                f"recorrido interno bloqueado={self._v108_route_blocks} · "
                "ROUTE_VISIBLE=False"
            ),
            (
                "regla V108: el último pase del canvas siempre borra el dibujo "
                "heredado antes de presentar la interfaz"
            ),
            (
                "regla V108: jamás quedan visibles grilla antigua, base naranja, "
                "espiral/perímetro naranja ni recorrido azul interno"
            ),
            (
                "regla V108: esperando el mapa final se muestran fondo azul, "
                "base verde y robot; la planta no se inventa en vivo"
            ),
            (
                "regla V108: mapas viejos sin grid final usan el piso estimado "
                "moderno con relleno+contorno azul, pero sin recorrido"
            ),
            (
                "regla V108: un grid Xiaomi final usa el mismo renderer moderno "
                "en mapa grande y miniatura"
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

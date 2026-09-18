import math
import tkinter as tk

import app_v71


class App(app_v71.App):
    """V72: viewport tipo CAD para el mapa, sin tocar la geometría del mapeo."""

    ZOOM_STEP = 1.18
    MIN_SCALE = 4.0
    MAX_SCALE = 900.0

    def __init__(self):
        # Debe existir antes de que app_v6 dibuje la leyenda heredada.
        self._fixed_map_legend = True
        self._v72_views = {}
        self._v72_pan_start = None
        self._v72_pan_center_start = None
        self._v72_pan_last = None
        self._v72_legend = None
        self._v72_active_map_seen = None
        super().__init__()

        if hasattr(self, "map_canvas"):
            self._v72_install_map_controls()
            self.after(120, self._v72_sync_active_view)

    # ----------------------------------------------------------- view model
    def _v72_active_map_id(self):
        local_map = getattr(self, "local_map", None)
        if not local_map:
            return ""
        try:
            return str(local_map.active_map_id or "")
        except Exception:
            return ""

    def _v72_view(self):
        map_id = self._v72_active_map_id() or "__default__"
        view = self._v72_views.get(map_id)
        if view is None:
            view = {
                "mode": "base",
                "center": None,
                "scale": None,
            }
            self._v72_views[map_id] = view
        return view

    @staticmethod
    def _v72_xy(value):
        if not isinstance(value, dict):
            return None
        try:
            x = float(value.get("x"))
            y = float(value.get("y"))
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    def _v72_bounds(self, snapshot):
        coords = []

        def add_xy(x, y):
            try:
                x = float(x)
                y = float(y)
            except Exception:
                return
            if math.isfinite(x) and math.isfinite(y):
                coords.append((x, y))

        for point in list((snapshot or {}).get("points") or []):
            if isinstance(point, dict):
                add_xy(point.get("x"), point.get("y"))

        for room in list((snapshot or {}).get("rooms") or []):
            if isinstance(room, dict):
                add_xy(room.get("x0"), room.get("y0"))
                add_xy(room.get("x1"), room.get("y1"))

        for key in ("robot", "charging_base"):
            point = (snapshot or {}).get(key)
            if isinstance(point, dict):
                add_xy(point.get("x"), point.get("y"))

        plan_store = getattr(self, "plan_store", None)
        if plan_store:
            try:
                plan = plan_store.snapshot()
            except Exception:
                plan = {}
            for key in ("zones", "no_go"):
                for zone in list(plan.get(key) or []):
                    if isinstance(zone, dict):
                        add_xy(zone.get("x0"), zone.get("y0"))
                        add_xy(zone.get("x1"), zone.get("y1"))

        if not coords:
            return None

        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        if abs(max_x - min_x) < 1e-6:
            min_x -= 0.5
            max_x += 0.5
        if abs(max_y - min_y) < 1e-6:
            min_y -= 0.5
            max_y += 0.5

        return min_x, min_y, max_x, max_y

    def _v72_default_base_center(self, snapshot):
        base = self._v72_xy((snapshot or {}).get("charging_base"))
        if base is not None:
            return base

        # V71 fija la base de una sesión en (0,0). Si todavía no está persistida
        # pero el mapa tiene recorrido, ese es el centro visual correcto.
        if list((snapshot or {}).get("points") or []):
            return (0.0, 0.0)

        bounds = self._v72_bounds(snapshot)
        if bounds:
            min_x, min_y, max_x, max_y = bounds
            return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        return (0.0, 0.0)

    @staticmethod
    def _v72_fit_scale_about_center(bounds, center, cw, ch, pad):
        if not bounds:
            return None
        min_x, min_y, max_x, max_y = bounds
        cx, cy = center
        max_dx = max(abs(min_x - cx), abs(max_x - cx), 0.5)
        max_dy = max(abs(min_y - cy), abs(max_y - cy), 0.5)
        avail_x = max(20.0, float(cw) / 2.0 - float(pad))
        avail_y = max(20.0, float(ch) / 2.0 - float(pad))
        return min(avail_x / max_dx, avail_y / max_dy)

    def _v72_sync_active_view(self):
        current = self._v72_active_map_id()
        if current != self._v72_active_map_seen:
            self._v72_active_map_seen = current
            view = self._v72_view()
            view["mode"] = "base"
            view["center"] = None
            view["scale"] = None
            self.after(20, self._v72_render_main_canvas)

    # --------------------------------------------------------- fixed legend
    def _v72_install_map_controls(self):
        canvas = self.map_canvas
        canvas.bind("<MouseWheel>", self._v72_mouse_wheel, add="+")
        canvas.bind("<Double-Button-2>", self._v72_zoom_extents_event, add="+")
        canvas.bind("<ButtonPress-1>", self._map_press)
        canvas.bind("<B1-Motion>", self._map_drag)
        canvas.bind("<ButtonRelease-1>", self._map_release)

        legend = tk.Frame(
            canvas,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e8f0",
            padx=10,
            pady=7,
        )
        legend.place(x=14, y=14)

        row = tk.Frame(legend, bg="#ffffff")
        row.pack()

        line1 = tk.Canvas(row, width=23, height=10, bg="#ffffff", highlightthickness=0)
        line1.pack(side="left")
        line1.create_line(1, 5, 22, 5, fill="#f97316", width=3)
        tk.Label(
            row,
            text="Perímetro",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(4, 13))

        line2 = tk.Canvas(row, width=23, height=10, bg="#ffffff", highlightthickness=0)
        line2.pack(side="left")
        line2.create_line(1, 5, 22, 5, fill="#3b82f6", width=3)
        tk.Label(
            row,
            text="Interior",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(4, 0))

        self._v72_legend = legend
        legend.lift()

    # ------------------------------------------------------ render viewport
    def _v72_render_main_canvas(self):
        local_map = getattr(self, "local_map", None)
        canvas = getattr(self, "map_canvas", None)
        if not local_map or canvas is None or not canvas.winfo_exists():
            return
        try:
            snapshot = local_map.snapshot()
        except Exception:
            return
        self._render_map_canvas(canvas, snapshot)

    def _render_map_canvas(self, canvas, snapshot):
        if canvas is not getattr(self, "map_canvas", None):
            return super()._render_map_canvas(canvas, snapshot)

        # V72 es dueño completo del viewport. Neutralizamos el pan heredado
        # antes del render base para reconstruir siempre desde coordenadas limpias.
        old_pan = (0.0, 0.0)
        map_pan = getattr(self, "_map_pan", None)
        if isinstance(map_pan, dict):
            old_pan = map_pan.get(canvas, (0.0, 0.0))
            map_pan[canvas] = (0.0, 0.0)

        result = super()._render_map_canvas(canvas, snapshot)

        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            if isinstance(map_pan, dict):
                map_pan[canvas] = old_pan
            if self._v72_legend is not None:
                self._v72_legend.lift()
            return result

        cw = max(300, canvas.winfo_width())
        ch = max(250, canvas.winfo_height())
        pad = float(transform.get("pad", 28))
        base_scale = float(transform.get("scale", 1.0) or 1.0)
        min_x = float(transform.get("min_x", 0.0))
        max_y = float(transform.get("max_y", 0.0))
        bounds = self._v72_bounds(snapshot)

        self._v72_sync_active_view()
        view = self._v72_view()
        mode = str(view.get("mode") or "base")

        if mode == "extents" and bounds:
            bx0, by0, bx1, by1 = bounds
            center = ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0)
            desired_scale = base_scale
        elif mode == "manual" and view.get("center") is not None and view.get("scale"):
            center = tuple(view["center"])
            desired_scale = float(view["scale"])
        else:
            center = self._v72_default_base_center(snapshot)
            fit = self._v72_fit_scale_about_center(bounds, center, cw, ch, pad)
            desired_scale = min(base_scale, fit) if fit else base_scale
            view["mode"] = "base"

        desired_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, float(desired_scale or base_scale)))
        zoom = desired_scale / max(1e-9, base_scale)

        center_screen_x = pad + (float(center[0]) - min_x) * base_scale
        center_screen_y = pad + (max_y - float(center[1])) * base_scale

        if abs(zoom - 1.0) > 1e-9:
            canvas.scale("all", 0.0, 0.0, zoom, zoom)

        dx = float(cw) / 2.0 - zoom * center_screen_x
        dy = float(ch) / 2.0 - zoom * center_screen_y
        if dx or dy:
            canvas.move("all", dx, dy)

        effective_pan_x = dx + (zoom - 1.0) * pad
        effective_pan_y = dy + (zoom - 1.0) * pad
        transform["scale"] = desired_scale
        transform["pan_x"] = effective_pan_x
        transform["pan_y"] = effective_pan_y
        if isinstance(map_pan, dict):
            map_pan[canvas] = (effective_pan_x, effective_pan_y)

        view["center"] = (float(center[0]), float(center[1]))
        view["scale"] = desired_scale

        if self._v72_legend is not None:
            self._v72_legend.lift()
        return result

    # ------------------------------------------------------------- pan
    def _map_press(self, event):
        if self._drawing_on_map():
            return super()._map_press(event)

        canvas = self.map_canvas
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return "break"

        center = self._canvas_to_world(
            canvas,
            max(1, canvas.winfo_width()) / 2.0,
            max(1, canvas.winfo_height()) / 2.0,
        )
        if center is None:
            return "break"

        self._v72_pan_start = (event.x, event.y)
        self._v72_pan_last = (event.x, event.y)
        self._v72_pan_center_start = center
        view = self._v72_view()
        view["mode"] = "manual"
        view["center"] = center
        view["scale"] = float(transform.get("scale", 1.0) or 1.0)
        canvas.configure(cursor="fleur")
        return "break"

    def _map_drag(self, event):
        if self._drawing_on_map():
            return super()._map_drag(event)
        if not self._v72_pan_start or not self._v72_pan_center_start:
            return "break"

        canvas = self.map_canvas
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return "break"

        scale = float(transform.get("scale", 1.0) or 1.0)
        sx, sy = self._v72_pan_start
        cx0, cy0 = self._v72_pan_center_start
        total_dx = float(event.x - sx)
        total_dy = float(event.y - sy)

        view = self._v72_view()
        view["mode"] = "manual"
        view["center"] = (
            float(cx0) - total_dx / scale,
            float(cy0) + total_dy / scale,
        )
        view["scale"] = scale

        lx, ly = self._v72_pan_last or (event.x, event.y)
        step_dx = float(event.x - lx)
        step_dy = float(event.y - ly)
        self._v72_pan_last = (event.x, event.y)

        if step_dx or step_dy:
            canvas.move("all", step_dx, step_dy)
            pan_x, pan_y = getattr(self, "_map_pan", {}).get(canvas, (0.0, 0.0))
            pan_x += step_dx
            pan_y += step_dy
            self._map_pan[canvas] = (pan_x, pan_y)
            transform["pan_x"] = pan_x
            transform["pan_y"] = pan_y

        if self._v72_legend is not None:
            self._v72_legend.lift()
        return "break"

    def _map_release(self, event):
        if self._drawing_on_map():
            return super()._map_release(event)
        self._v72_pan_start = None
        self._v72_pan_center_start = None
        self._v72_pan_last = None
        return "break"

    # ------------------------------------------------------------- zoom
    def _v72_mouse_wheel(self, event):
        if self._drawing_on_map():
            return "break"

        canvas = self.map_canvas
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return "break"

        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return "break"

        before = self._canvas_to_world(canvas, event.x, event.y)
        if before is None:
            return "break"

        current_scale = float(transform.get("scale", 1.0) or 1.0)
        factor = self.ZOOM_STEP if delta > 0 else (1.0 / self.ZOOM_STEP)
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, current_scale * factor))
        if abs(new_scale - current_scale) < 1e-9:
            return "break"

        cw = max(1.0, float(canvas.winfo_width()))
        ch = max(1.0, float(canvas.winfo_height()))
        offset_x = float(event.x) - cw / 2.0
        offset_y = float(event.y) - ch / 2.0

        center = (
            float(before[0]) - offset_x / new_scale,
            float(before[1]) + offset_y / new_scale,
        )

        view = self._v72_view()
        view["mode"] = "manual"
        view["center"] = center
        view["scale"] = new_scale
        self._v72_render_main_canvas()
        return "break"

    def _v72_zoom_extents_event(self, _event=None):
        if self._drawing_on_map():
            return "break"
        view = self._v72_view()
        view["mode"] = "extents"
        view["center"] = None
        view["scale"] = None
        self._v72_render_main_canvas()
        self._set_banner("Mapa encuadrado completo · Zoom Extents.")
        return "break"

    # ------------------------------------------------------- map selection
    def _switch_map(self, map_id, window=None):
        result = super()._switch_map(map_id, window)
        self._v72_active_map_seen = None
        self._v72_sync_active_view()
        return result

    def _v70_select_map(self, map_id):
        result = super()._v70_select_map(map_id)
        self._v72_active_map_seen = None
        self._v72_sync_active_view()
        return result

    def _reset_coordinate_session(self):
        result = super()._reset_coordinate_session()
        view = self._v72_view()
        view["mode"] = "base"
        view["center"] = None
        view["scale"] = None
        return result

    # ----------------------------------------------------------- diagnostic
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        view = dict(self._v72_view() or {})
        transform = None
        try:
            transform = dict(self._map_transforms.get(self.map_canvas) or {})
        except Exception:
            transform = {}

        lines = [
            "DIAGNÓSTICO V72 ACTIVO · viewport de mapa tipo CAD",
            "===================================================",
            f"modo vista: {view.get('mode') or '—'} · centro={view.get('center')!r}",
            f"escala efectiva: {view.get('scale')!r}",
            f"transform pan: {(transform.get('pan_x'), transform.get('pan_y')) if transform else None}",
            "leyenda fija: True · rueda=zoom · doble rueda=Zoom Extents",
            "regla V72: la navegación visual no modifica coordenadas ni lógica de mapeo V71",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import math
import tkinter as tk

import app_v86


class App(app_v86.App):
    """V87: modos nativos Bordes/Espiral + mapa visual tipo Mi Home."""

    MAP_BG = "#dfe9f2"
    MAP_FLOOR = "#b8d9f5"
    MAP_OUTLINE = "#1687ee"
    MAP_ROUTE = "#4d92db"
    MAP_BASE = "#2dc653"
    MAP_ROBOT = "#f8fafc"
    MAP_ROBOT_EDGE = "#d7dee5"
    MAP_CELL = 0.16
    MAP_FOOTPRINT_CELLS = 1

    # ========================================================= mapa visual
    @classmethod
    def _v87_floor_cells(cls, snapshot):
        """Convierte la trayectoria real en superficie explorada sin grilla visible."""
        points = [
            p for p in list((snapshot or {}).get("points") or [])
            if isinstance(p, dict)
        ]
        cells = set()
        size = float(cls.MAP_CELL)
        radius = int(cls.MAP_FOOTPRINT_CELLS)

        for point in points:
            try:
                x = float(point["x"])
                y = float(point["y"])
            except Exception:
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            cx = int(math.floor(x / size))
            cy = int(math.floor(y / size))
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    # Huella cuadrada suavizada por la alta densidad de puntos.
                    cells.add((cx + dx, cy + dy))
        return cells

    @classmethod
    def _v87_cell_bounds(cls, cell):
        size = float(cls.MAP_CELL)
        x, y = cell
        return x * size, y * size, (x + 1) * size, (y + 1) * size

    @staticmethod
    def _v87_path_segments(snapshot, jump=0.80):
        points = [
            p for p in list((snapshot or {}).get("points") or [])
            if isinstance(p, dict)
        ]
        if not points:
            return []
        segments = []
        current = []
        previous = None
        for point in points:
            try:
                x = float(point["x"])
                y = float(point["y"])
            except Exception:
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            item = (x, y)
            if previous is not None:
                if math.hypot(item[0] - previous[0], item[1] - previous[1]) > jump:
                    if len(current) >= 2:
                        segments.append(current)
                    current = []
            current.append(item)
            previous = item
        if len(current) >= 2:
            segments.append(current)
        return segments

    @staticmethod
    def _v87_xy(point):
        if not isinstance(point, dict):
            return None
        try:
            x = float(point["x"])
            y = float(point["y"])
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    def _v87_draw_floor(self, canvas, snapshot, xy, outline_width=3):
        cells = self._v87_floor_cells(snapshot)
        if not cells:
            return 0

        # Relleno continuo: sin outline por celda, por lo que desaparece la
        # apariencia de grilla. Luego dibujamos sólo el perímetro exterior.
        for cell in cells:
            x0, y0, x1, y1 = self._v87_cell_bounds(cell)
            sx0, sy1 = xy(x0, y0)
            sx1, sy0 = xy(x1, y1)
            canvas.create_rectangle(
                min(sx0, sx1),
                min(sy0, sy1),
                max(sx0, sx1),
                max(sy0, sy1),
                fill=self.MAP_FLOOR,
                outline=self.MAP_FLOOR,
                width=0,
                tags=("v87_floor",),
            )

        for cx, cy in cells:
            x0, y0, x1, y1 = self._v87_cell_bounds((cx, cy))
            if (cx - 1, cy) not in cells:
                a = xy(x0, y0); b = xy(x0, y1)
                canvas.create_line(*a, *b, fill=self.MAP_OUTLINE, width=outline_width, tags=("v87_outline",))
            if (cx + 1, cy) not in cells:
                a = xy(x1, y0); b = xy(x1, y1)
                canvas.create_line(*a, *b, fill=self.MAP_OUTLINE, width=outline_width, tags=("v87_outline",))
            if (cx, cy - 1) not in cells:
                a = xy(x0, y0); b = xy(x1, y0)
                canvas.create_line(*a, *b, fill=self.MAP_OUTLINE, width=outline_width, tags=("v87_outline",))
            if (cx, cy + 1) not in cells:
                a = xy(x0, y1); b = xy(x1, y1)
                canvas.create_line(*a, *b, fill=self.MAP_OUTLINE, width=outline_width, tags=("v87_outline",))
        return len(cells)

    def _v87_draw_route(self, canvas, snapshot, xy, width=2):
        for segment in self._v87_path_segments(snapshot):
            coords = []
            for x, y in segment:
                coords.extend(xy(x, y))
            if len(coords) >= 4:
                canvas.create_line(
                    *coords,
                    fill=self.MAP_ROUTE,
                    width=width,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                    tags=("v87_route",),
                )

    def _v87_draw_rooms_and_plan(self, canvas, snapshot, xy):
        # Habitaciones manuales siguen visibles.
        for room in list((snapshot or {}).get("rooms") or []):
            if not isinstance(room, dict):
                continue
            try:
                a = xy(room["x0"], room["y0"])
                b = xy(room["x1"], room["y1"])
            except Exception:
                continue
            left, right = sorted((a[0], b[0]))
            top, bottom = sorted((a[1], b[1]))
            canvas.create_rectangle(
                left, top, right, bottom,
                outline="#2563eb",
                width=2,
                dash=(5, 3),
                tags=("v87_room",),
            )
            canvas.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text=str(room.get("name") or "Habitación"),
                fill="#334155",
                font=("Segoe UI", 8, "bold"),
                tags=("v87_room",),
            )

        plan_store = getattr(self, "plan_store", None)
        if not plan_store:
            return
        try:
            plan = plan_store.snapshot()
        except Exception:
            return

        for zone in list((plan or {}).get("zones") or []):
            if not isinstance(zone, dict):
                continue
            try:
                a = xy(zone["x0"], zone["y0"]); b = xy(zone["x1"], zone["y1"])
            except Exception:
                continue
            canvas.create_rectangle(
                min(a[0], b[0]), min(a[1], b[1]),
                max(a[0], b[0]), max(a[1], b[1]),
                outline="#16a34a", width=2, dash=(5, 3),
                tags=("v87_zone",),
            )

        for zone in list((plan or {}).get("no_go") or []):
            if not isinstance(zone, dict):
                continue
            try:
                a = xy(zone["x0"], zone["y0"]); b = xy(zone["x1"], zone["y1"])
            except Exception:
                continue
            canvas.create_rectangle(
                min(a[0], b[0]), min(a[1], b[1]),
                max(a[0], b[0]), max(a[1], b[1]),
                outline="#dc2626", width=2, dash=(6, 4),
                tags=("v87_nogo",),
            )

    def _v87_draw_base_and_robot(self, canvas, snapshot, xy, miniature=False):
        base = self._v87_xy((snapshot or {}).get("charging_base"))
        robot_obj = (snapshot or {}).get("robot")
        robot = self._v87_xy(robot_obj)

        if miniature:
            base_half = 4
            robot_r = 4
        else:
            base_half = 11
            robot_r = 13

        base_screen = None
        if base is not None:
            bx, by = xy(*base)
            base_screen = (bx, by)
            canvas.create_rectangle(
                bx - base_half,
                by - base_half,
                bx + base_half,
                by + base_half,
                fill=self.MAP_BASE,
                outline="",
                tags=("v87_base",),
            )
            if not miniature:
                canvas.create_text(
                    bx, by,
                    text="⚡",
                    fill="white",
                    font=("Segoe UI Symbol", 12, "bold"),
                    tags=("v87_base",),
                )

        if robot is None:
            return

        rx, ry = xy(*robot)
        # Cargando: V84 fija robot y base al mismo punto físico. Separamos sólo
        # el icono unos píxeles para mostrar ambos, como hace Mi Home.
        if base_screen is not None and math.hypot(rx - base_screen[0], ry - base_screen[1]) < 2.0:
            rx -= 1.35 * robot_r

        canvas.create_oval(
            rx - robot_r, ry - robot_r,
            rx + robot_r, ry + robot_r,
            fill=self.MAP_ROBOT,
            outline=self.MAP_ROBOT_EDGE,
            width=2 if not miniature else 1,
            tags=("v87_robot",),
        )
        if miniature:
            return

        angle = 0.0
        if isinstance(robot_obj, dict):
            try:
                angle = float(robot_obj.get("angle", robot_obj.get("phi", 0.0)) or 0.0)
            except Exception:
                angle = 0.0
        hx = rx + math.cos(angle) * (robot_r - 4)
        hy = ry - math.sin(angle) * (robot_r - 4)
        canvas.create_line(
            rx, ry, hx, hy,
            fill="#64748b",
            width=2,
            capstyle=tk.ROUND,
            tags=("v87_robot",),
        )
        canvas.create_oval(
            rx - 2, ry - 2, rx + 2, ry + 2,
            fill="#94a3b8", outline="",
            tags=("v87_robot",),
        )

    def _render_map_canvas(self, canvas, snapshot):
        # Primero dejamos que V72 calcule viewport, zoom y pan. Después
        # reemplazamos únicamente la capa gráfica por el renderer V87.
        result = super()._render_map_canvas(canvas, snapshot)
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return result

        canvas.delete("all")
        try:
            canvas.configure(bg=self.MAP_BG, highlightbackground=self.MAP_BG)
        except Exception:
            pass

        scale = float(transform.get("scale", 1.0) or 1.0)
        min_x = float(transform.get("min_x", 0.0))
        max_y = float(transform.get("max_y", 0.0))
        pad = float(transform.get("pad", 28.0))
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)

        def xy(x, y):
            return (
                pad + (float(x) - min_x) * scale + pan_x,
                pad + (max_y - float(y)) * scale + pan_y,
            )

        self._v87_draw_floor(canvas, snapshot, xy, outline_width=3)
        self._v87_draw_route(canvas, snapshot, xy, width=2)
        self._v87_draw_rooms_and_plan(canvas, snapshot, xy)
        self._v87_draw_base_and_robot(canvas, snapshot, xy, miniature=False)

        selected = getattr(self, "selected_point", None)
        if canvas is getattr(self, "map_canvas", None) and selected:
            try:
                sx, sy = xy(selected[0], selected[1])
                canvas.create_oval(
                    sx - 7, sy - 7, sx + 7, sy + 7,
                    outline="#2563eb", width=2,
                    tags=("v87_selection",),
                )
            except Exception:
                pass

        legend = getattr(self, "_v72_legend", None)
        if legend is not None:
            try:
                legend.lift()
            except Exception:
                pass
        return result

    def _v70_render_thumbnail(self, canvas, snapshot, plan, active):
        canvas.delete("all")
        try:
            canvas.configure(bg=self.MAP_BG, highlightbackground=self.MAP_BG)
        except Exception:
            pass

        bounds = self._v70_collect_bounds(snapshot, plan)
        if bounds is None:
            canvas.create_text(
                87.5, 44,
                text="Sin mapear",
                fill="#64748b",
                font=("Segoe UI", 8),
            )
            return

        left, bottom, right, top = bounds
        width, height, margin = 175.0, 88.0, 7.0
        sx = (width - margin * 2) / max(1e-6, right - left)
        sy = (height - margin * 2) / max(1e-6, top - bottom)
        scale = min(sx, sy)

        def xy(x, y):
            return (
                margin + (float(x) - left) * scale,
                height - margin - (float(y) - bottom) * scale,
            )

        self._v87_draw_floor(canvas, snapshot, xy, outline_width=1)
        self._v87_draw_route(canvas, snapshot, xy, width=1)

        base = self._v87_xy((snapshot or {}).get("charging_base"))
        robot = self._v87_xy((snapshot or {}).get("robot"))
        if base is not None:
            bx, by = xy(*base)
            canvas.create_rectangle(bx - 3, by - 3, bx + 3, by + 3, fill=self.MAP_BASE, outline="")
        if robot is not None:
            rx, ry = xy(*robot)
            canvas.create_oval(rx - 3, ry - 3, rx + 3, ry + 3, fill=self.MAP_ROBOT, outline="#94a3b8")

    # ====================================================== diagnóstico V87
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        snapshot = {}
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            pass
        cells = self._v87_floor_cells(snapshot)
        approx_area = len(cells) * (self.MAP_CELL ** 2)
        lines = [
            "DIAGNÓSTICO V87 ACTIVO · modos nativos + mapa visual tipo Mi Home",
            "=================================================================",
            "sweep-type E10: global=0 · bordes=2 · espiral=4 · remoto=5",
            f"superficie visual: {len(cells)} celdas · área aproximada={approx_area:.2f} m²",
            "visual V87: sin grilla · piso continuo · contorno exterior · recorrido superpuesto",
            "visual V87: base verde con carga · robot circular orientado · dock superpuesto separado sólo visualmente",
            "regla V87: Limpiar bordes usa sweep-type=2 antes de iniciar",
            "regla V87: Espiral usa sweep-type=4 antes de iniciar",
            "regla V87: Iniciar normal fuerza sweep-type=0 para no heredar el patrón anterior",
            "regla V87: el estilo nuevo no altera coordenadas, cobertura ni lógica física V85/V86",
        ]
        return "\n".join(lines) + "\n\n" + inherited

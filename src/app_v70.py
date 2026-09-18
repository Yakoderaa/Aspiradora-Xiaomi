import math
import time
import tkinter as tk
from tkinter import messagebox

import app_v69


SURFACE = "#ffffff"
SURFACE_2 = "#f8fafc"
MAP_BG = "#f8fafc"
TEXT = "#111827"
MUTED = "#64748b"
BORDER = "#e2e8f0"
ACCENT = "#4f46e5"
ACCENT_SOFT = "#eef2ff"
GREEN = "#16a34a"
RED = "#dc2626"
BLUE = "#0284c7"


class App(app_v69.App):
    """V70: cuatro mapas siempre visibles + selección persistente en UI."""

    MAP_OVERVIEW_SLOTS = 4
    MAP_OVERVIEW_REFRESH_SECONDS = 0.85

    def __init__(self):
        self._v70_overview_frame = None
        self._v70_map_cards = []
        self._v70_last_overview_render = 0.0
        self._v70_last_overview_active = None
        self._v70_global_map_badge = None
        self._v70_map_selection_label = None
        self._v70_completion_notified = False
        super().__init__()
        self._v70_install_global_map_badge()
        self.after(180, lambda: self._v70_refresh_map_overview(force=True))
        self.after(220, self._v70_update_active_map_labels)

    # ---------------------------------------------------------- UI principal
    def _build_map_page_v22(self):
        super()._build_map_page_v22()

        title_parent = getattr(self, "map_status_label", None)
        if title_parent is not None:
            parent = self.map_status_label.master
            self._v70_map_selection_label = tk.Label(
                parent,
                text="Mapa seleccionado: —",
                bg=SURFACE,
                fg=ACCENT,
                font=("Segoe UI", 9, "bold"),
            )
            self._v70_map_selection_label.pack(anchor="w", pady=(3, 0))

        map_canvas = getattr(self, "map_canvas", None)
        if map_canvas is None:
            return
        map_outer = map_canvas.master

        gallery = tk.Frame(map_outer, bg=SURFACE)
        gallery.pack(
            fill="x",
            padx=10,
            pady=(0, 9),
            before=map_canvas,
        )
        for column in range(self.MAP_OVERVIEW_SLOTS):
            gallery.grid_columnconfigure(column, weight=1, uniform="v70maps")

        self._v70_overview_frame = gallery
        self._v70_refresh_map_overview(force=True)

    def _v70_install_global_map_badge(self):
        if self._v70_global_map_badge is not None:
            return
        battery = getattr(self, "battery_header", None)
        if battery is None:
            return
        parent = battery.master
        badge = tk.Label(
            parent,
            text="MAPA · —",
            bg=ACCENT_SOFT,
            fg=ACCENT,
            font=("Segoe UI", 9, "bold"),
            padx=11,
            pady=8,
            highlightthickness=1,
            highlightbackground="#c7d2fe",
        )
        badge.pack(side="left", padx=(0, 8), before=battery)
        self._v70_global_map_badge = badge

    @staticmethod
    def _v70_card_models(library):
        library = dict(library or {})
        active_id = str(library.get("active_map_id") or "")
        maps = [dict(item) for item in list(library.get("maps") or [])[:4] if isinstance(item, dict)]

        cards = []
        for index in range(4):
            if index < len(maps):
                item = maps[index]
                cards.append({
                    "slot": index + 1,
                    "empty": False,
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or f"Mapa {index + 1}"),
                    "active": str(item.get("id") or "") == active_id,
                    "points": len(item.get("points") or []),
                    "walls": len(item.get("mapped_walls") or []),
                    "rooms": len(item.get("rooms") or []),
                    "snapshot": item,
                })
            else:
                cards.append({
                    "slot": index + 1,
                    "empty": True,
                    "id": None,
                    "name": f"Mapa {index + 1}",
                    "active": False,
                    "points": 0,
                    "walls": 0,
                    "rooms": 0,
                    "snapshot": None,
                })
        return cards

    def _v70_refresh_map_overview(self, force=False):
        local_map = getattr(self, "local_map", None)
        if not local_map or self._v70_overview_frame is None:
            self._v70_update_active_map_labels()
            return

        now = time.monotonic()
        active_id = str(getattr(local_map, "active_map_id", "") or "")
        if (
            not force
            and active_id == self._v70_last_overview_active
            and now - self._v70_last_overview_render < self.MAP_OVERVIEW_REFRESH_SECONDS
        ):
            self._v70_update_active_map_labels()
            return

        self._v70_last_overview_render = now
        self._v70_last_overview_active = active_id

        try:
            library = local_map.library_snapshot()
        except Exception:
            return

        cards = self._v70_card_models(library)
        for child in self._v70_overview_frame.winfo_children():
            child.destroy()
        self._v70_map_cards = []

        for column, model in enumerate(cards):
            active = bool(model.get("active"))
            border = ACCENT if active else BORDER
            card = tk.Frame(
                self._v70_overview_frame,
                bg=SURFACE,
                highlightthickness=2 if active else 1,
                highlightbackground=border,
                highlightcolor=border,
                cursor="hand2" if not model.get("empty") else "arrow",
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0 if column == 3 else 4),
            )

            head = tk.Frame(card, bg=SURFACE)
            head.pack(fill="x", padx=9, pady=(8, 5))
            name = tk.Label(
                head,
                text=model["name"],
                bg=SURFACE,
                fg=TEXT if not model.get("empty") else MUTED,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            )
            name.pack(side="left", fill="x", expand=True)

            if active:
                tk.Label(
                    head,
                    text="SELECCIONADO",
                    bg=ACCENT_SOFT,
                    fg=ACCENT,
                    font=("Segoe UI", 7, "bold"),
                    padx=6,
                    pady=3,
                ).pack(side="right")
            elif model.get("empty"):
                tk.Label(
                    head,
                    text="LIBRE",
                    bg=SURFACE_2,
                    fg=MUTED,
                    font=("Segoe UI", 7, "bold"),
                    padx=6,
                    pady=3,
                ).pack(side="right")

            preview = tk.Canvas(
                card,
                bg=MAP_BG,
                width=175,
                height=88,
                highlightthickness=0,
                cursor="hand2" if not model.get("empty") else "arrow",
            )
            preview.pack(fill="x", padx=8)

            if model.get("empty"):
                preview.create_text(
                    88, 36,
                    text="+",
                    fill=ACCENT,
                    font=("Segoe UI", 24, "bold"),
                )
                preview.create_text(
                    88, 62,
                    text="Espacio disponible",
                    fill=MUTED,
                    font=("Segoe UI", 8),
                )
                info_text = "Creá otro mapa sin salir de esta pestaña"
            else:
                plan = {}
                plan_store = getattr(self, "plan_store", None)
                if plan_store:
                    try:
                        plan = plan_store.snapshot(model["id"])
                    except Exception:
                        plan = {}
                self._v70_render_thumbnail(preview, model["snapshot"], plan, active)
                zones = len(plan.get("zones", []) or [])
                blocks = len(plan.get("no_go", []) or [])
                info_text = (
                    f"{model['points']} puntos · {zones} zonas · {blocks} bloqueos"
                )

            tk.Label(
                card,
                text=info_text,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 7),
                anchor="w",
            ).pack(fill="x", padx=9, pady=(5, 6))

            if model.get("empty"):
                button = self._button(
                    card,
                    "+ Crear mapa",
                    self._v70_create_map_from_overview,
                    compact=True,
                )
            elif active:
                button = self._button(card, "Seleccionado", lambda: None, compact=True)
                button.configure(state="disabled")
            else:
                button = self._button(
                    card,
                    "Seleccionar",
                    lambda mid=model["id"]: self._v70_select_map(mid),
                    compact=True,
                )
            button.pack(fill="x", padx=8, pady=(0, 8))

            if not model.get("empty"):
                callback = lambda _event, mid=model["id"]: self._v70_select_map(mid)
                for widget in (card, head, name, preview):
                    widget.bind("<Button-1>", callback)

            self._v70_map_cards.append((card, model))

        self._v70_update_active_map_labels()

    @staticmethod
    def _v70_collect_bounds(snapshot, plan):
        coords = []

        def add(x, y):
            try:
                x = float(x)
                y = float(y)
            except Exception:
                return
            if math.isfinite(x) and math.isfinite(y):
                coords.append((x, y))

        for point in list((snapshot or {}).get("points") or []):
            if isinstance(point, dict):
                add(point.get("x"), point.get("y"))

        for wall in list((snapshot or {}).get("mapped_walls") or []):
            if not isinstance(wall, dict):
                continue
            for point in list(wall.get("points") or []):
                if isinstance(point, dict):
                    add(point.get("x"), point.get("y"))

        for key in ("robot", "charging_base"):
            point = (snapshot or {}).get(key)
            if isinstance(point, dict):
                add(point.get("x"), point.get("y"))

        for key in ("zones", "no_go"):
            for zone in list((plan or {}).get(key) or []):
                if not isinstance(zone, dict):
                    continue
                add(zone.get("x0"), zone.get("y0"))
                add(zone.get("x1"), zone.get("y1"))

        if not coords:
            return None
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        left, right = min(xs), max(xs)
        bottom, top = min(ys), max(ys)
        if abs(right - left) < 1e-6:
            left -= 1.0
            right += 1.0
        if abs(top - bottom) < 1e-6:
            bottom -= 1.0
            top += 1.0
        return left, bottom, right, top

    def _v70_render_thumbnail(self, canvas, snapshot, plan, active):
        canvas.delete("all")
        width = 175.0
        height = 88.0
        bounds = self._v70_collect_bounds(snapshot, plan)
        if bounds is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Sin mapear",
                fill=MUTED,
                font=("Segoe UI", 8),
            )
            return

        left, bottom, right, top = bounds
        margin = 8.0
        sx = (width - margin * 2) / max(1e-6, right - left)
        sy = (height - margin * 2) / max(1e-6, top - bottom)
        scale = min(sx, sy)

        def xy(x, y):
            px = margin + (float(x) - left) * scale
            py = height - margin - (float(y) - bottom) * scale
            return px, py

        for zone in list((plan or {}).get("zones") or []):
            try:
                x0, y0 = xy(zone["x0"], zone["y0"])
                x1, y1 = xy(zone["x1"], zone["y1"])
            except Exception:
                continue
            canvas.create_rectangle(x0, y0, x1, y1, outline=GREEN, width=1)

        for zone in list((plan or {}).get("no_go") or []):
            try:
                x0, y0 = xy(zone["x0"], zone["y0"])
                x1, y1 = xy(zone["x1"], zone["y1"])
            except Exception:
                continue
            canvas.create_rectangle(x0, y0, x1, y1, outline=RED, width=1)

        for wall in list((snapshot or {}).get("mapped_walls") or []):
            if not isinstance(wall, dict):
                continue
            coords = []
            for point in list(wall.get("points") or []):
                if not isinstance(point, dict):
                    continue
                try:
                    coords.extend(xy(point["x"], point["y"]))
                except Exception:
                    continue
            if len(coords) >= 4:
                canvas.create_line(*coords, fill="#334155", width=2)

        points = [p for p in list((snapshot or {}).get("points") or []) if isinstance(p, dict)]
        phase_coords = {}
        for point in points:
            try:
                phase = int(point.get("phase", 0) or 0)
                phase_coords.setdefault(phase, []).extend(xy(point["x"], point["y"]))
            except Exception:
                continue
        for phase, coords in phase_coords.items():
            if len(coords) >= 4:
                color = ACCENT if active else ("#64748b" if phase == 1 else "#94a3b8")
                canvas.create_line(*coords, fill=color, width=1)

        base = (snapshot or {}).get("charging_base")
        if isinstance(base, dict):
            try:
                x, y = xy(base["x"], base["y"])
                canvas.create_rectangle(x - 3, y - 3, x + 3, y + 3, fill=GREEN, outline="")
            except Exception:
                pass

        robot = (snapshot or {}).get("robot")
        if isinstance(robot, dict):
            try:
                x, y = xy(robot["x"], robot["y"])
                canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=BLUE, outline="")
            except Exception:
                pass

    # ------------------------------------------------------- selección mapas
    def _v70_active_map_name(self):
        local_map = getattr(self, "local_map", None)
        if not local_map:
            return "—"
        try:
            snapshot = local_map.snapshot()
            return str(snapshot.get("name") or "Mapa")
        except Exception:
            return "—"

    def _v70_update_active_map_labels(self):
        name = self._v70_active_map_name()
        if self._v70_map_selection_label is not None:
            self._v70_map_selection_label.configure(
                text=f"Mapa seleccionado: {name}"
            )
        if self._v70_global_map_badge is not None:
            self._v70_global_map_badge.configure(text=f"MAPA · {name}")

    def _v70_select_map(self, map_id):
        local_map = getattr(self, "local_map", None)
        if not local_map:
            return
        try:
            if str(local_map.active_map_id) != str(map_id):
                self._switch_map(map_id)
            self._v70_refresh_map_overview(force=True)
            self._v70_update_active_map_labels()
        except Exception as exc:
            messagebox.showerror("Mapas", str(exc), parent=self)

    def _v70_create_map_from_overview(self):
        if not getattr(self, "local_map", None):
            return
        self._create_map(lambda: self._v70_refresh_map_overview(force=True))
        self._v70_update_active_map_labels()

    def _refresh_map_library_button(self):
        result = super()._refresh_map_library_button()
        if hasattr(self, "map_library_button"):
            self.map_library_button.configure(text="Administrar")
        self._v70_update_active_map_labels()
        return result

    def _render_maps(self):
        result = super()._render_maps()
        self._v70_refresh_map_overview(force=False)
        self._v70_update_active_map_labels()
        return result

    # ----------------------------------------------------- fin de mapeo
    @staticmethod
    def _v70_completion_message(map_name):
        name = str(map_name or "Mapa")
        return (
            "El mapeo terminó y quedó guardado.\n\n"
            f"Mapa seleccionado: {name}"
        )

    def start_new_mapping(self):
        self._v70_completion_notified = False
        return super().start_new_mapping()

    def _v70_notify_mapping_complete(self):
        if self._v70_completion_notified:
            return
        self._v70_completion_notified = True
        name = self._v70_active_map_name()
        self._v70_refresh_map_overview(force=True)
        self._v70_update_active_map_labels()
        self._set_banner(f"Mapeo terminado · Mapa seleccionado: {name}.")
        messagebox.showinfo(
            "Mapeo terminado",
            self._v70_completion_message(name),
            parent=self,
        )

    def _render_status(self, status):
        was_phase2 = bool(getattr(self, "mapping_active", False)) and int(
            getattr(self, "mapping_phase", 0) or 0
        ) == 2
        was_step2_complete = bool(getattr(self, "mapping_step2_complete", False))

        result = super()._render_status(status)

        completed_now = (
            was_phase2
            and not was_step2_complete
            and bool(getattr(self, "mapping_step2_complete", False))
            and not bool(getattr(self, "mapping_active", False))
        )
        if completed_now:
            self.after(80, self._v70_notify_mapping_complete)

        self._v70_update_active_map_labels()
        return result

    # ---------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        name = self._v70_active_map_name()
        count = 0
        try:
            local_map = getattr(self, "local_map", None)
            count = len(local_map.list_maps()) if local_map else 0
        except Exception:
            pass
        lines = [
            "DIAGNÓSTICO V70 ACTIVO · 4 mapas visibles",
            "==========================================",
            f"mapa seleccionado: {name}",
            f"mapas guardados: {count}/4 · tarjetas visibles: 4",
            f"notificación fin de mapeo enviada: {bool(self._v70_completion_notified)}",
            "regla V70: los 4 slots de mapa permanecen visibles en la pestaña Mapa",
            "regla V70: seleccionar una tarjeta cambia el mapa activo sin abrir la biblioteca",
            "regla V70: el mapa activo se muestra también en la cabecera global",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

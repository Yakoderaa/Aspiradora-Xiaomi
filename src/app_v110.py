import math
import tkinter as tk
from tkinter import messagebox, simpledialog

import app_v109
import app_v9


BG = app_v109.BG
SURFACE = app_v109.SURFACE
SURFACE_2 = app_v109.SURFACE_2
TEXT = app_v109.TEXT
MUTED = app_v109.MUTED
BORDER = app_v109.BORDER
ACCENT = app_v109.ACCENT
ACCENT_SOFT = app_v109.ACCENT_SOFT
GREEN = app_v109.GREEN
GREEN_SOFT = app_v109.GREEN_SOFT
RED = app_v109.RED
RED_SOFT = app_v109.RED_SOFT


class App(app_v109.App):
    """V110: habitaciones como contenedor obligatorio de todas las zonas."""

    def __init__(self):
        self._v110_section = "rooms"
        self._v110_side_host = None
        self._v110_section_host = None
        self._v110_header_room = None
        self._v110_rooms_rendered = 0
        self._v110_zones_rendered = 0
        self._v110_orphans_attached = 0
        self._v110_orphans_deleted = 0
        self._v110_cascade_deletes = 0
        self._v110_diag_compat_hits = 0
        super().__init__()
        self.after(450, self._v110_reconcile_room_zones)
        self.after(600, lambda: self._v110_render_side(force=True))

    # ===================================================== diagnóstico legacy
    def _v87_floor_cells(self, snapshot=None):
        """Compatibilidad V110 para diagnósticos heredados.

        Algunas capas antiguas llaman _v87_floor_cells() sin pasar snapshot.
        V107+ exige snapshot. V110 acepta ambas formas para recuperar el
        diagnóstico completo en lugar de caer al modo de emergencia.
        """
        if snapshot is None:
            self._v110_diag_compat_hits += 1
            try:
                snapshot = self.local_map.snapshot() if self.local_map else {}
            except Exception:
                snapshot = {}
        return super()._v87_floor_cells(snapshot)

    # ========================================================= UI lateral
    def _build_map_page_v22(self):
        # V109 conserva toda la parte izquierda del mapa, incluida la regla de
        # que abajo sólo existe Administrar mapas.
        super()._build_map_page_v22()

        page = self._page("map")
        candidates = list(page.grid_slaves(row=0, column=1))
        if not candidates:
            return
        side = candidates[0]

        # Se sustituye únicamente el lateral heredado. Rehacemos los widgets
        # ocultos que otras capas todavía esperan encontrar.
        for child in list(side.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        self.point_label = tk.Label(side, text="", bg=BG)
        self.point_clean_button = self._button(
            side,
            "Limpiar aquí",
            self.clean_selected_point,
            compact=True,
        )
        self.point_clean_button.configure(state="disabled")

        outer, body = self._surface(side, 16, 14)
        outer.pack(fill="both", expand=True)
        self._v110_side_host = body

        header = tk.Frame(body, bg=SURFACE)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Espacios",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Habitaciones, zonas y bloqueos organizados en un solo lugar.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(3, 12))

        selector = tk.Frame(body, bg=SURFACE_2, padx=3, pady=3)
        selector.pack(fill="x", pady=(0, 12))
        self._v110_rooms_tab_btn = tk.Button(
            selector,
            text="Habitaciones",
            command=lambda: self._v110_show_section("rooms"),
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=8,
        )
        self._v110_rooms_tab_btn.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 2),
        )
        self._v110_zones_tab_btn = tk.Button(
            selector,
            text="Zonas",
            command=lambda: self._v110_show_section("zones"),
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=8,
        )
        self._v110_zones_tab_btn.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(2, 0),
        )

        self._v110_header_room = tk.Label(
            body,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self._v110_header_room.pack(fill="x", pady=(0, 7))

        self._v110_section_host = tk.Frame(body, bg=SURFACE)
        self._v110_section_host.pack(fill="both", expand=True)

        self._v110_update_segmented_buttons()
        self.after(50, lambda: self._v110_render_side(force=True))

    def _v110_update_segmented_buttons(self):
        rooms = self._v110_section == "rooms"
        for button, active in (
            (getattr(self, "_v110_rooms_tab_btn", None), rooms),
            (getattr(self, "_v110_zones_tab_btn", None), not rooms),
        ):
            if button is None:
                continue
            try:
                button.configure(
                    bg=ACCENT if active else SURFACE_2,
                    fg="white" if active else TEXT,
                    activebackground=ACCENT if active else "#eef2f7",
                    activeforeground="white" if active else TEXT,
                )
            except Exception:
                pass

    def _v110_show_section(self, section):
        section = "zones" if str(section) == "zones" else "rooms"
        if section == "zones" and self._v110_selected_room() is None:
            messagebox.showinfo(
                "Zonas",
                "Primero creá o seleccioná una habitación. Las zonas siempre pertenecen a una habitación.",
                parent=self,
            )
            section = "rooms"
        self._v110_section = section
        self._v110_update_segmented_buttons()
        self._v110_render_side(force=True)

    @staticmethod
    def _v110_room_id(room):
        value = (room or {}).get("id")
        return None if value is None else str(value)

    def _v110_rooms(self):
        try:
            return list(self.local_map.snapshot().get("rooms") or [])
        except Exception:
            return []

    def _v110_selected_room(self):
        rooms = self._v110_rooms()
        if not rooms:
            return None

        var = getattr(self, "_v109_selected_room_id", None)
        selected = str(var.get()) if var is not None else ""
        for room in rooms:
            if self._v110_room_id(room) == selected:
                return dict(room)

        room = dict(rooms[0])
        if var is not None:
            var.set(self._v110_room_id(room))
        return room

    def _v110_select_room(self, room_id):
        if self._v109_selected_room_id is None:
            self._v109_selected_room_id = tk.StringVar(value=str(room_id))
        else:
            self._v109_selected_room_id.set(str(room_id))
        if self._v109_selected_zone_key is not None:
            self._v109_selected_zone_key.set("")
        self._v110_render_side(force=True)
        self._render_maps()

    def _v110_room_items(self, room_id):
        if not self.plan_store or room_id is None:
            return {"zones": [], "no_go": []}
        return self.plan_store.room_items(
            room_id,
            map_id=self.plan_store.active_map_id(),
        )

    def _v110_render_side(self, force=False):
        host = getattr(self, "_v110_section_host", None)
        if host is None:
            return

        rooms = self._v110_rooms()
        if rooms and self._v109_selected_room_id is not None:
            valid = {self._v110_room_id(room) for room in rooms}
            if self._v109_selected_room_id.get() not in valid:
                self._v109_selected_room_id.set(self._v110_room_id(rooms[0]))
        elif self._v109_selected_room_id is not None:
            self._v109_selected_room_id.set("")
            self._v110_section = "rooms"

        room = self._v110_selected_room()
        if self._v110_header_room is not None:
            if room is None:
                text = "Sin habitación activa"
            else:
                items = self._v110_room_items(self._v110_room_id(room))
                count = len(items["zones"]) + len(items["no_go"])
                text = (
                    f"Habitación activa · {room.get('name','Habitación')} · "
                    f"{count} zona{'s' if count != 1 else ''}"
                )
            try:
                self._v110_header_room.configure(text=text)
            except Exception:
                pass

        for child in list(host.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        self._v110_update_segmented_buttons()
        if self._v110_section == "zones":
            self._v110_render_zones(host, room)
        else:
            self._v110_render_rooms(host, rooms)

    def _v110_card(self, parent, selected=False):
        return tk.Frame(
            parent,
            bg=ACCENT_SOFT if selected else SURFACE_2,
            highlightthickness=2 if selected else 1,
            highlightbackground=ACCENT if selected else BORDER,
            padx=11,
            pady=9,
        )

    @staticmethod
    def _v110_bind_tree(widget, callback):
        try:
            widget.bind("<Button-1>", callback)
        except Exception:
            pass
        for child in list(widget.winfo_children()):
            App._v110_bind_tree(child, callback)

    def _v110_render_rooms(self, host, rooms):
        self._v110_rooms_rendered += 1

        head = tk.Frame(host, bg=SURFACE)
        head.pack(fill="x", pady=(0, 10))
        left = tk.Frame(head, bg=SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="Habitaciones",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Cada zona pertenece a una habitación.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))
        self._button(
            head,
            "+ Nueva",
            self.enable_room_editor,
            accent=True,
            compact=True,
        ).pack(side="right")

        if not rooms:
            empty = tk.Frame(
                host,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
                padx=14,
                pady=18,
            )
            empty.pack(fill="x")
            tk.Label(
                empty,
                text="Todavía no hay habitaciones",
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                empty,
                text="Creá una habitación para habilitar zonas de limpieza y zonas bloqueadas.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=270,
                justify="left",
            ).pack(anchor="w", pady=(5, 0))
            return

        selected_id = (
            self._v109_selected_room_id.get()
            if self._v109_selected_room_id is not None
            else ""
        )
        list_host = tk.Frame(host, bg=SURFACE)
        list_host.pack(fill="both", expand=True)

        for room in rooms:
            room_id = self._v110_room_id(room)
            selected = room_id == selected_id
            items = self._v110_room_items(room_id)
            clean_count = len(items["zones"])
            blocked_count = len(items["no_go"])

            card = self._v110_card(list_host, selected=selected)
            card.pack(fill="x", pady=4)

            top = tk.Frame(card, bg=card.cget("bg"))
            top.pack(fill="x")
            tk.Label(
                top,
                text=room.get("name", "Habitación"),
                bg=card.cget("bg"),
                fg=TEXT,
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left")
            if selected:
                tk.Label(
                    top,
                    text="ACTIVA",
                    bg=ACCENT,
                    fg="white",
                    font=("Segoe UI", 7, "bold"),
                    padx=7,
                    pady=2,
                ).pack(side="right")

            meta = (
                f"{clean_count} limpieza"
                f"{'s' if clean_count != 1 else ''} · "
                f"{blocked_count} bloqueo"
                f"{'s' if blocked_count != 1 else ''}"
            )
            tk.Label(
                card,
                text=meta,
                bg=card.cget("bg"),
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=(4, 0))

            callback = lambda _e, rid=room_id: self._v110_select_room(rid)
            self._v110_bind_tree(card, callback)

        room = self._v110_selected_room()
        if room is not None:
            actions = tk.Frame(host, bg=SURFACE)
            actions.pack(fill="x", pady=(10, 0))
            self._button(
                actions,
                "Limpiar habitación",
                self._v109_clean_selected_room,
                accent=True,
                compact=True,
            ).pack(fill="x", pady=(0, 5))

            row = tk.Frame(actions, bg=SURFACE)
            row.pack(fill="x")
            self._button(
                row,
                "Ver zonas",
                lambda: self._v110_show_section("zones"),
                compact=True,
            ).pack(side="left", fill="x", expand=True, padx=(0, 3))
            self._button(
                row,
                "Bloquear",
                self._v109_toggle_selected_room_block,
                compact=True,
            ).pack(side="left", fill="x", expand=True, padx=3)
            self._button(
                row,
                "Eliminar",
                self._v110_delete_selected_room,
                compact=True,
                danger=True,
            ).pack(side="left", padx=(3, 0))

    def _v110_render_zones(self, host, room):
        self._v110_zones_rendered += 1

        if room is None:
            self._v110_section = "rooms"
            self._v110_render_rooms(host, self._v110_rooms())
            return

        room_id = self._v110_room_id(room)
        items = self._v110_room_items(room_id)

        summary = tk.Frame(
            host,
            bg=ACCENT_SOFT,
            highlightthickness=1,
            highlightbackground="#c7d2fe",
            padx=11,
            pady=9,
        )
        summary.pack(fill="x", pady=(0, 10))
        tk.Label(
            summary,
            text=room.get("name", "Habitación"),
            bg=ACCENT_SOFT,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            summary,
            text="Las zonas que crees ahora quedarán ancladas a esta habitación.",
            bg=ACCENT_SOFT,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=270,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        create = tk.Frame(host, bg=SURFACE)
        create.pack(fill="x", pady=(0, 10))
        self._button(
            create,
            "+ Zona de limpieza",
            lambda: self._v110_begin_zone_draw("zone"),
            accent=True,
            compact=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._button(
            create,
            "+ Bloqueo",
            lambda: self._v110_begin_zone_draw("no_go"),
            compact=True,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        entries = (
            [("clean", item) for item in items["zones"]]
            + [("block", item) for item in items["no_go"]]
        )

        if not entries:
            empty = tk.Frame(
                host,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
                padx=13,
                pady=16,
            )
            empty.pack(fill="x")
            tk.Label(
                empty,
                text="Sin zonas en esta habitación",
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            tk.Label(
                empty,
                text="Creá zonas de limpieza o bloqueos dentro del límite de la habitación.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=270,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))
            if self._v109_selected_zone_key is not None:
                self._v109_selected_zone_key.set("")
            return

        keys = {f"{kind}:{item.get('id')}" for kind, item in entries}
        if self._v109_selected_zone_key is not None:
            if self._v109_selected_zone_key.get() not in keys:
                kind, item = entries[0]
                self._v109_selected_zone_key.set(f"{kind}:{item.get('id')}")

        selected_key = (
            self._v109_selected_zone_key.get()
            if self._v109_selected_zone_key is not None
            else ""
        )
        list_host = tk.Frame(host, bg=SURFACE)
        list_host.pack(fill="both", expand=True)

        for kind, item in entries:
            key = f"{kind}:{item.get('id')}"
            selected = key == selected_key
            card = self._v110_card(list_host, selected=selected)
            card.pack(fill="x", pady=4)
            top = tk.Frame(card, bg=card.cget("bg"))
            top.pack(fill="x")
            tk.Label(
                top,
                text=item.get("name", "Zona"),
                bg=card.cget("bg"),
                fg=TEXT,
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left")
            tk.Label(
                top,
                text="LIMPIEZA" if kind == "clean" else "BLOQUEO",
                bg=GREEN_SOFT if kind == "clean" else RED_SOFT,
                fg=GREEN if kind == "clean" else RED,
                font=("Segoe UI", 7, "bold"),
                padx=6,
                pady=2,
            ).pack(side="right")

            width = abs(float(item.get("x1", 0)) - float(item.get("x0", 0)))
            height = abs(float(item.get("y1", 0)) - float(item.get("y0", 0)))
            tk.Label(
                card,
                text=f"{width:.2f} × {height:.2f} m",
                bg=card.cget("bg"),
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=(4, 0))

            def select_zone(_event, value=key):
                if self._v109_selected_zone_key is not None:
                    self._v109_selected_zone_key.set(value)
                self._v110_render_side(force=True)
                self._render_maps()

            self._v110_bind_tree(card, select_zone)

        actions = tk.Frame(host, bg=SURFACE)
        actions.pack(fill="x", pady=(10, 0))
        kind, zone = self._v109_selected_zone()
        if kind == "clean" and zone is not None:
            self._button(
                actions,
                "Limpiar zona",
                self._v109_clean_selected_zone,
                accent=True,
                compact=True,
            ).pack(fill="x", pady=(0, 5))

        self._button(
            actions,
            "Eliminar zona",
            self._v109_delete_selected_zone,
            compact=True,
            danger=True,
        ).pack(fill="x")

    # ======================================== anclaje habitación -> zonas
    @staticmethod
    def _v110_rect(item):
        try:
            x0, x1 = sorted((float(item["x0"]), float(item["x1"])))
            y0, y1 = sorted((float(item["y0"]), float(item["y1"])))
            return x0, y0, x1, y1
        except Exception:
            return None

    @classmethod
    def _v110_intersection_area(cls, a, b):
        ar = cls._v110_rect(a)
        br = cls._v110_rect(b)
        if ar is None or br is None:
            return 0.0
        x0 = max(ar[0], br[0])
        y0 = max(ar[1], br[1])
        x1 = min(ar[2], br[2])
        y1 = min(ar[3], br[3])
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)

    @classmethod
    def _v110_zone_inside_room(cls, zone, room, tolerance=0.03):
        zr = cls._v110_rect(zone)
        rr = cls._v110_rect(room)
        if zr is None or rr is None:
            return False
        return (
            zr[0] >= rr[0] - tolerance
            and zr[1] >= rr[1] - tolerance
            and zr[2] <= rr[2] + tolerance
            and zr[3] <= rr[3] + tolerance
        )

    def _v110_reconcile_room_zones(self):
        if not self.plan_store:
            return
        rooms = self._v110_rooms()
        valid = {self._v110_room_id(room): room for room in rooms}
        plan = self.plan_store.snapshot()
        changed_no_go = False

        for kind, source in (
            ("zone", list(plan.get("zones") or [])),
            ("no_go", list(plan.get("no_go") or [])),
        ):
            for item in source:
                current = item.get("room_id")
                if current is not None and str(current) in valid:
                    continue

                best_room = None
                best_score = 0.0
                for room_id, room in valid.items():
                    score = self._v110_intersection_area(item, room)
                    if score > best_score:
                        best_score = score
                        best_room = room_id

                if best_room is not None and best_score > 0.0:
                    self.plan_store.set_item_room(
                        "zone" if kind == "zone" else "no_go",
                        item.get("id"),
                        best_room,
                    )
                    self._v110_orphans_attached += 1
                else:
                    if kind == "zone":
                        self.plan_store.delete_zone(item.get("id"))
                    else:
                        self.plan_store.delete_no_go(item.get("id"))
                        changed_no_go = True
                    self._v110_orphans_deleted += 1

        if changed_no_go:
            try:
                self._sync_no_go_async()
            except Exception:
                pass
        self._v110_render_side(force=True)

    def _v110_begin_zone_draw(self, kind):
        room = self._v110_selected_room()
        if room is None:
            messagebox.showinfo(
                "Zonas",
                "Primero creá o seleccioná una habitación. Sin habitación no se pueden crear zonas.",
                parent=self,
            )
            self._v110_show_section("rooms")
            return
        self._v110_pending_room_id = self._v110_room_id(room)
        self.room_edit_mode = False
        self._plan_draw_mode = kind
        label = "zona de limpieza" if kind == "zone" else "zona bloqueada"
        self._set_banner(
            f"{room.get('name','Habitación')} · arrastrá dentro de la habitación para crear la {label}."
        )

    def _enable_plan_draw(self, kind):
        # Cualquier llamada heredada pasa por la misma regla.
        return self._v110_begin_zone_draw(kind)

    def _map_release(self, event):
        if self._plan_draw_mode and self._plan_drag_start:
            kind = self._plan_draw_mode
            room = self._v110_selected_room()
            start = self._canvas_to_world(
                self.map_canvas,
                *self._plan_drag_start,
            )
            end = self._canvas_to_world(
                self.map_canvas,
                event.x,
                event.y,
            )

            self._plan_draw_mode = None
            self._plan_drag_start = None
            if self._plan_drag_item:
                try:
                    self.map_canvas.delete(self._plan_drag_item)
                except Exception:
                    pass
                self._plan_drag_item = None

            if room is None:
                self._set_banner("La zona no se guardó: no hay habitación activa.")
                return
            if not start or not end:
                return
            if abs(start[0] - end[0]) < 0.12 or abs(start[1] - end[1]) < 0.12:
                self._set_banner("La zona dibujada es demasiado pequeña.")
                return

            candidate = {
                "x0": start[0],
                "y0": start[1],
                "x1": end[0],
                "y1": end[1],
            }
            if not self._v110_zone_inside_room(candidate, room):
                messagebox.showwarning(
                    "Zona fuera de la habitación",
                    "La zona debe quedar completamente dentro de la habitación activa.",
                    parent=self,
                )
                self._set_banner("Zona descartada · quedó fuera de la habitación.")
                return

            title = "Nueva zona" if kind == "zone" else "Nueva zona bloqueada"
            name = simpledialog.askstring(
                title,
                "Nombre o etiqueta:",
                parent=self,
            )
            if name is None:
                return

            room_id = self._v110_room_id(room)
            if kind == "zone":
                self.plan_store.add_zone(
                    name,
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    room_id=room_id,
                )
                self._set_banner(
                    f"Zona “{name or 'Zona'}” guardada en {room.get('name','Habitación')}."
                )
            else:
                self.plan_store.add_no_go(
                    name,
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    room_id=room_id,
                )
                self._set_banner(
                    f"Bloqueo “{name or 'Zona bloqueada'}” guardado en {room.get('name','Habitación')}."
                )
                self._sync_no_go_async()

            self._v109_selected_zone_key.set("")
            self._refresh_scheduler_page()
            self._v110_render_side(force=True)
            self._render_maps()
            return

        was_room = bool(getattr(self, "room_edit_mode", False))
        result = super()._map_release(event)
        if was_room:
            self.after(120, lambda: self._v110_render_side(force=True))
        return result

    def _v110_delete_selected_room(self):
        room = self._v110_selected_room()
        if room is None:
            return
        room_id = self._v110_room_id(room)
        items = self._v110_room_items(room_id)
        total = len(items["zones"]) + len(items["no_go"])
        detail = (
            f"\nTambién se eliminarán {total} zona"
            f"{'s' if total != 1 else ''} asociada"
            f"{'s' if total != 1 else ''}."
            if total
            else ""
        )
        if not messagebox.askyesno(
            "Eliminar habitación",
            f"¿Eliminar “{room.get('name','Habitación')}”?{detail}",
            parent=self,
        ):
            return

        removed = self.plan_store.delete_room_items(room_id)
        self.local_map.delete_room(room.get("id"))
        self._v110_cascade_deletes += (
            int(removed.get("zones", 0))
            + int(removed.get("no_go", 0))
        )
        if int(removed.get("no_go", 0)) > 0:
            self._sync_no_go_async()

        self._v109_selected_room_id.set("")
        self._v109_selected_zone_key.set("")
        self._v110_section = "rooms"
        self._refresh_scheduler_page()
        self._v110_render_side(force=True)
        self._render_maps()
        self._set_banner(
            f"Habitación eliminada · también se borraron "
            f"{removed.get('zones',0)} zonas de limpieza y "
            f"{removed.get('no_go',0)} bloqueos."
        )

    # El botón heredado de V109 también debe usar cascada.
    def _v109_delete_selected_room(self):
        return self._v110_delete_selected_room()

    def _v109_toggle_selected_room_block(self):
        room = self._v110_selected_room()
        if room is None or not self.plan_store:
            return
        room_id = self._v110_room_id(room)
        items = self._v110_room_items(room_id)
        target = self._v109_rect_signature(room)
        wall = next(
            (
                item for item in items["no_go"]
                if self._v109_rect_signature(item) == target
            ),
            None,
        )
        if wall is not None:
            self.plan_store.delete_no_go(wall.get("id"))
            self._set_banner(
                f"Habitación “{room.get('name','Habitación')}” desbloqueada."
            )
        else:
            self.plan_store.add_no_go(
                f"Habitación · {room.get('name','Habitación')}",
                room["x0"],
                room["y0"],
                room["x1"],
                room["y1"],
                room_id=room_id,
            )
            self._set_banner(
                f"Habitación “{room.get('name','Habitación')}” bloqueada."
            )
        self._sync_no_go_async()
        self._v110_render_side(force=True)
        self._render_maps()

    def _v109_selected_zone(self):
        kind, zone = super()._v109_selected_zone()
        room = self._v110_selected_room()
        if zone is None or room is None:
            return None, None
        if str(zone.get("room_id")) != self._v110_room_id(room):
            return None, None
        return kind, zone

    def _v109_refresh_side_panel(self, force=False):
        # El panel V109 ya no se usa visualmente. Conservamos el método porque
        # otras capas lo invocan, pero redirige al renderer moderno V110.
        self._v110_render_side(force=force)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        room = self._v110_selected_room()
        room_id = self._v110_room_id(room) if room else None
        items = self._v110_room_items(room_id) if room_id else {
            "zones": [],
            "no_go": [],
        }
        lines = [
            "DIAGNÓSTICO V110 PREPARADO · habitaciones y zonas ancladas",
            "================================================================",
            (
                f"sección={self._v110_section} · habitación activa="
                f"{(room or {}).get('name','—')} · room_id={room_id or '—'}"
            ),
            (
                f"zonas activas: limpieza={len(items['zones'])} · "
                f"bloqueos={len(items['no_go'])}"
            ),
            (
                f"migración legacy: asociados={self._v110_orphans_attached} · "
                f"eliminados={self._v110_orphans_deleted} · "
                f"borrados en cascada={self._v110_cascade_deletes}"
            ),
            (
                f"UI moderna: renders habitaciones={self._v110_rooms_rendered} · "
                f"renders zonas={self._v110_zones_rendered}"
            ),
            (
                f"compat diagnóstico _v87_floor_cells sin snapshot="
                f"{self._v110_diag_compat_hits}"
            ),
            (
                "regla V110: no existe zona nueva sin habitación activa; toda "
                "zona debe quedar dentro del rectángulo de su habitación"
            ),
            (
                "regla V110: cambiar habitación cambia la colección visible de "
                "zonas; borrar habitación elimina sus zonas y bloqueos"
            ),
            (
                "regla V110: abajo del mapa sigue quedando únicamente "
                "Administrar mapas"
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

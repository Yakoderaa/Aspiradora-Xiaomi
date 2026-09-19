import re
import tkinter as tk
from tkinter import messagebox, ttk

import app_v22
import app_v108
import app_v9
from xiaomi_e10_map_v109 import XiaomiE10MapV109


BG = app_v22.BG
SURFACE = app_v22.SURFACE
SURFACE_2 = app_v22.SURFACE_2
TEXT = app_v22.TEXT
MUTED = app_v22.MUTED
BORDER = app_v22.BORDER
ACCENT = app_v22.ACCENT
ACCENT_SOFT = app_v22.ACCENT_SOFT
GREEN = app_v22.GREEN
GREEN_SOFT = app_v22.GREEN_SOFT
RED = app_v22.RED
RED_SOFT = app_v22.RED_SOFT
MAP_BG = app_v22.MAP_BG


class App(app_v108.App):
    """V109: diagnóstico seguro + mapa físico + panel lateral unificado."""

    _V109_IPV4_RE = re.compile(
        r"(?<!\d)(?:25[0-5]|2[0-4]\d|1?\d?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!\d)"
    )

    def __init__(self):
        # Diagnóstico / privacidad.
        self._v109_diag_full_ok = 0
        self._v109_diag_fallbacks = 0
        self._v109_diag_refreshes = 0
        self._v109_diag_copy_ok = 0
        self._v109_last_diag_error = "—"
        self._v109_redactions = 0

        # Panel lateral: se inicializa antes de que app_v22 construya la página.
        self._v109_map_tabs = None
        self._v109_rooms_frame = None
        self._v109_zones_frame = None
        self._v109_selected_room_id = None
        self._v109_selected_zone_key = None
        self._v109_room_signature = None
        self._v109_zone_signature = None
        self._v109_origin_repairs = 0
        self._v109_last_origin_raw = None
        self._v109_panel_refreshes = 0

        super().__init__()
        self.after(300, lambda: self._v109_refresh_side_panel(force=True))

    # ========================================================= privacidad UI
    def _set_connection(self, connected, text=None):
        """Nunca mostrar la IP del robot en el estado visible de conexión."""
        if connected:
            return super()._set_connection(True, "Conectado")
        return super()._set_connection(False, text or "Desconectado")

    @classmethod
    def _v109_redact_ips(cls, value):
        text = str(value or "")
        redacted, count = cls._V109_IPV4_RE.subn("[IP OCULTA]", text)
        return redacted, int(count)

    # ================================================ página mapa V109
    def _build_map_page_v22(self):
        page = self._page("map")
        page.grid_columnconfigure(0, weight=5)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(0, weight=1)

        map_outer = tk.Frame(
            page,
            bg=SURFACE,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        map_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 7), pady=5)

        head = tk.Frame(map_outer, bg=SURFACE)
        head.pack(fill="x", padx=16, pady=(14, 8))
        title = tk.Frame(head, bg=SURFACE)
        title.pack(side="left")
        tk.Label(
            title,
            text="Plano de la vivienda",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")
        self.map_status_label = tk.Label(
            title,
            text="Mapa local listo",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.map_status_label.pack(anchor="w", pady=(2, 0))

        mapping_controls = tk.Frame(head, bg=SURFACE)
        mapping_controls.pack(side="right")
        self.stop_mapping_button = self._button(
            mapping_controls,
            "Detener",
            self.finish_mapping,
            compact=True,
        )
        self.stop_mapping_button.pack(side="right", padx=(6, 0))
        self.step2_mapping_button = self._button(
            mapping_controls,
            "Paso 2 · Interior",
            self.start_interior_mapping,
            compact=True,
        )
        self.step2_mapping_button.pack(side="right", padx=(6, 0))
        self.step1_mapping_button = self._button(
            mapping_controls,
            "Paso 1 · Perímetro",
            self.start_new_mapping,
            accent=True,
            compact=True,
        )
        self.step1_mapping_button.pack(side="right")

        self.map_canvas = tk.Canvas(
            map_outer,
            bg=MAP_BG,
            highlightthickness=0,
            cursor="fleur",
        )
        self.map_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.map_canvas.bind("<ButtonPress-1>", self._map_press)
        self.map_canvas.bind("<B1-Motion>", self._map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._map_release)
        self.map_canvas.bind("<Double-Button-1>", self._map_double_click)
        self.map_canvas.bind(
            "<Configure>",
            lambda _e: self.after(80, self._render_maps),
        )

        # Franja inferior: por pedido del usuario queda ÚNICAMENTE mapas.
        tools = tk.Frame(map_outer, bg=SURFACE)
        tools.pack(fill="x", padx=14, pady=(0, 12))
        self._map_toolbar = tools
        self.mapping_steps_info = tk.Label(
            tools,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        # Compatibilidad: existe, pero no se empaqueta.
        self._zone_tools_slot = tk.Frame(tools, bg=SURFACE)
        self._map_library_slot = tk.Frame(tools, bg=SURFACE)
        self._map_library_slot.pack(side="right")

        side = tk.Frame(page, bg=BG)
        side.grid(row=0, column=1, sticky="nsew", padx=(7, 5), pady=5)

        panel_outer, panel = self._surface(side, 14, 12)
        panel_outer.pack(fill="both", expand=True)
        tk.Label(
            panel,
            text="Habitaciones y zonas",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        tk.Label(
            panel,
            text="Seleccioná dónde limpiar o bloquear sin salir del mapa.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(3, 10))

        notebook = ttk.Notebook(panel)
        notebook.pack(fill="both", expand=True)
        self._v109_map_tabs = notebook

        rooms_tab = tk.Frame(notebook, bg=SURFACE)
        zones_tab = tk.Frame(notebook, bg=SURFACE)
        notebook.add(rooms_tab, text="Habitaciones")
        notebook.add(zones_tab, text="Zonas")

        # ---------------------------------------------- pestaña Habitaciones
        room_top = tk.Frame(rooms_tab, bg=SURFACE)
        room_top.pack(fill="x", padx=8, pady=(10, 6))
        self._button(
            room_top,
            "+ Añadir habitación",
            self.enable_room_editor,
            compact=True,
        ).pack(fill="x")

        self._v109_selected_room_id = tk.StringVar(value="")
        self.rooms_frame = tk.Frame(rooms_tab, bg=SURFACE)
        self._v109_rooms_frame = self.rooms_frame
        self.rooms_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        room_actions = tk.Frame(rooms_tab, bg=SURFACE)
        room_actions.pack(fill="x", padx=8, pady=(0, 10))
        self._button(
            room_actions,
            "Limpiar seleccionada",
            self._v109_clean_selected_room,
            accent=True,
            compact=True,
        ).pack(fill="x", pady=(0, 5))
        row = tk.Frame(room_actions, bg=SURFACE)
        row.pack(fill="x")
        self._button(
            row,
            "Bloquear / desbloquear",
            self._v109_toggle_selected_room_block,
            compact=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._button(
            row,
            "Eliminar",
            self._v109_delete_selected_room,
            compact=True,
            danger=True,
        ).pack(side="left", padx=(3, 0))

        # --------------------------------------------------- pestaña Zonas
        zone_top = tk.Frame(zones_tab, bg=SURFACE)
        zone_top.pack(fill="x", padx=8, pady=(10, 6))
        self._button(
            zone_top,
            "+ Zona de limpieza",
            lambda: self._enable_plan_draw("zone"),
            compact=True,
        ).pack(fill="x", pady=(0, 5))
        self._button(
            zone_top,
            "+ Zona bloqueada",
            lambda: self._enable_plan_draw("no_go"),
            compact=True,
        ).pack(fill="x")

        self._v109_selected_zone_key = tk.StringVar(value="")
        self._v109_zones_frame = tk.Frame(zones_tab, bg=SURFACE)
        self._v109_zones_frame.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=(5, 8),
        )

        zone_actions = tk.Frame(zones_tab, bg=SURFACE)
        zone_actions.pack(fill="x", padx=8, pady=(0, 10))
        self._button(
            zone_actions,
            "Limpiar seleccionada",
            self._v109_clean_selected_zone,
            accent=True,
            compact=True,
        ).pack(fill="x", pady=(0, 5))
        row = tk.Frame(zone_actions, bg=SURFACE)
        row.pack(fill="x")
        self._button(
            row,
            "Bloquear / desbloquear",
            self._v109_toggle_selected_zone_block,
            compact=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._button(
            row,
            "Eliminar",
            self._v109_delete_selected_zone,
            compact=True,
            danger=True,
        ).pack(side="left", padx=(3, 0))

        # Compatibilidad con la antigua selección de puntos: los widgets existen
        # para que el backend pueda actualizarlos, pero ya no ocupan el lateral.
        self.point_label = tk.Label(side, text="", bg=BG)
        self.point_clean_button = self._button(
            side,
            "Limpiar aquí",
            self.clean_selected_point,
            compact=True,
        )
        self.point_clean_button.configure(state="disabled")

    def _install_map_plan_controls(self):
        # V109: toda la gestión de habitaciones/zonas vive a la derecha.
        parent = getattr(self, "_zone_tools_slot", None)
        if parent is not None:
            for child in parent.winfo_children():
                child.destroy()
        return None

    def _install_map_library_control(self):
        parent = getattr(self, "_map_library_slot", None) or self._map_toolbar
        for child in parent.winfo_children():
            child.destroy()
        self.map_library_button = self._button(
            parent,
            "Administrar mapas",
            self.open_map_library,
            compact=True,
        )
        self.map_library_button.pack(side="right")
        self._refresh_map_library_button()

    # =========================================== panel habitaciones / zonas
    @staticmethod
    def _v109_rect_signature(item):
        try:
            return (
                round(float(item.get("x0")), 4),
                round(float(item.get("y0")), 4),
                round(float(item.get("x1")), 4),
                round(float(item.get("y1")), 4),
            )
        except Exception:
            return None

    def _v109_room_block(self, room, plan=None):
        plan = plan or (self.plan_store.snapshot() if self.plan_store else {})
        target = self._v109_rect_signature(room)
        if target is None:
            return None
        for wall in list((plan or {}).get("no_go") or []):
            if self._v109_rect_signature(wall) == target:
                return wall
        return None

    def _refresh_room_list(self, snapshot):
        rooms = list((snapshot or {}).get("rooms") or [])
        plan = self.plan_store.snapshot() if self.plan_store else {}
        blocked = {
            int(room.get("id")): bool(self._v109_room_block(room, plan))
            for room in rooms
            if room.get("id") is not None
        }
        signature = tuple(
            (
                int(room.get("id", -1)),
                str(room.get("name") or ""),
                self._v109_rect_signature(room),
                blocked.get(int(room.get("id", -1)), False),
            )
            for room in rooms
        )
        if signature == self._v109_room_signature:
            return
        self._v109_room_signature = signature

        frame = getattr(self, "_v109_rooms_frame", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()

        if not rooms:
            tk.Label(
                frame,
                text="No hay habitaciones.\nUsá “+ Añadir habitación” y dibujala en el mapa.",
                bg=SURFACE,
                fg=MUTED,
                justify="left",
                wraplength=280,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=8)
            if self._v109_selected_room_id is not None:
                self._v109_selected_room_id.set("")
            return

        valid_ids = {str(room.get("id")) for room in rooms}
        if (
            self._v109_selected_room_id is not None
            and self._v109_selected_room_id.get() not in valid_ids
        ):
            self._v109_selected_room_id.set(str(rooms[0].get("id")))

        for room in rooms:
            rid = str(room.get("id"))
            is_blocked = blocked.get(int(room.get("id", -1)), False)
            row = tk.Frame(
                frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            row.pack(fill="x", pady=3)
            tk.Radiobutton(
                row,
                variable=self._v109_selected_room_id,
                value=rid,
                bg=SURFACE_2,
                activebackground=SURFACE_2,
                selectcolor=SURFACE_2,
            ).pack(side="left", padx=(6, 2), pady=7)
            text = tk.Frame(row, bg=SURFACE_2)
            text.pack(side="left", fill="x", expand=True, pady=6)
            tk.Label(
                text,
                text=room.get("name", "Habitación"),
                bg=SURFACE_2,
                fg=TEXT,
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            tk.Label(
                text,
                text="Bloqueada" if is_blocked else "Disponible para limpiar",
                bg=SURFACE_2,
                fg=RED if is_blocked else GREEN,
                anchor="w",
                font=("Segoe UI", 7),
            ).pack(anchor="w")

    def _v109_refresh_zone_panel(self, force=False):
        frame = getattr(self, "_v109_zones_frame", None)
        if frame is None or not self.plan_store:
            return
        plan = self.plan_store.snapshot()
        zones = list(plan.get("zones") or [])
        blocks = list(plan.get("no_go") or [])
        signature = (
            tuple(
                (
                    "clean",
                    str(item.get("id")),
                    str(item.get("name") or ""),
                    self._v109_rect_signature(item),
                )
                for item in zones
            ),
            tuple(
                (
                    "block",
                    str(item.get("id")),
                    str(item.get("name") or ""),
                    self._v109_rect_signature(item),
                )
                for item in blocks
            ),
        )
        if not force and signature == self._v109_zone_signature:
            return
        self._v109_zone_signature = signature

        for child in frame.winfo_children():
            child.destroy()

        entries = [
            ("clean", item) for item in zones
        ] + [
            ("block", item) for item in blocks
        ]
        if not entries:
            tk.Label(
                frame,
                text="No hay zonas. Creá una zona de limpieza o una zona bloqueada.",
                bg=SURFACE,
                fg=MUTED,
                justify="left",
                wraplength=280,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=8)
            if self._v109_selected_zone_key is not None:
                self._v109_selected_zone_key.set("")
            return

        keys = {f"{kind}:{item.get('id')}" for kind, item in entries}
        if (
            self._v109_selected_zone_key is not None
            and self._v109_selected_zone_key.get() not in keys
        ):
            kind, item = entries[0]
            self._v109_selected_zone_key.set(f"{kind}:{item.get('id')}")

        for kind, item in entries:
            key = f"{kind}:{item.get('id')}"
            row = tk.Frame(
                frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            row.pack(fill="x", pady=3)
            tk.Radiobutton(
                row,
                variable=self._v109_selected_zone_key,
                value=key,
                bg=SURFACE_2,
                activebackground=SURFACE_2,
                selectcolor=SURFACE_2,
            ).pack(side="left", padx=(6, 2), pady=7)
            text = tk.Frame(row, bg=SURFACE_2)
            text.pack(side="left", fill="x", expand=True, pady=6)
            tk.Label(
                text,
                text=item.get("name", "Zona"),
                bg=SURFACE_2,
                fg=TEXT,
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            tk.Label(
                text,
                text="Zona de limpieza" if kind == "clean" else "Zona bloqueada",
                bg=SURFACE_2,
                fg=GREEN if kind == "clean" else RED,
                anchor="w",
                font=("Segoe UI", 7),
            ).pack(anchor="w")

    def _v109_refresh_side_panel(self, force=False):
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
            if force:
                self._v109_room_signature = None
            self._refresh_room_list(snapshot)
            self._v109_refresh_zone_panel(force=force)
            self._v109_panel_refreshes += 1
        except Exception:
            pass

    def _map_release(self, event):
        was_room = bool(getattr(self, "room_edit_mode", False))
        was_plan = bool(getattr(self, "_plan_draw_mode", None))
        result = super()._map_release(event)
        if was_room or was_plan:
            self.after(120, lambda: self._v109_refresh_side_panel(force=True))
        return result

    def _v109_selected_room(self):
        if not self.local_map or self._v109_selected_room_id is None:
            return None
        rid = self._v109_selected_room_id.get()
        for room in list(self.local_map.snapshot().get("rooms") or []):
            if str(room.get("id")) == str(rid):
                return dict(room)
        return None

    def _v109_selected_zone(self):
        if not self.plan_store or self._v109_selected_zone_key is None:
            return None, None
        key = self._v109_selected_zone_key.get()
        if ":" not in key:
            return None, None
        kind, item_id = key.split(":", 1)
        plan = self.plan_store.snapshot()
        source = plan.get("zones") if kind == "clean" else plan.get("no_go")
        for item in list(source or []):
            if str(item.get("id")) == item_id:
                return kind, dict(item)
        return None, None

    def _v109_clean_selected_room(self):
        room = self._v109_selected_room()
        if room is None:
            messagebox.showinfo(
                "Habitaciones",
                "Seleccioná una habitación.",
                parent=self,
            )
            return
        self.clean_local_room(room)

    def _v109_toggle_selected_room_block(self):
        room = self._v109_selected_room()
        if room is None or not self.plan_store:
            messagebox.showinfo(
                "Habitaciones",
                "Seleccioná una habitación.",
                parent=self,
            )
            return
        plan = self.plan_store.snapshot()
        wall = self._v109_room_block(room, plan)
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
            )
            self._set_banner(
                f"Habitación “{room.get('name','Habitación')}” bloqueada."
            )
        self._sync_no_go_async()
        self._v109_refresh_side_panel(force=True)
        self._render_maps()

    def _v109_delete_selected_room(self):
        room = self._v109_selected_room()
        if room is None:
            return
        if messagebox.askyesno(
            "Eliminar habitación",
            f"¿Eliminar “{room.get('name','Habitación')}”?",
            parent=self,
        ):
            self.local_map.delete_room(room.get("id"))
            self._v109_selected_room_id.set("")
            self._v109_refresh_side_panel(force=True)
            self._render_maps()

    def _v109_clean_selected_zone(self):
        kind, zone = self._v109_selected_zone()
        if zone is None:
            messagebox.showinfo("Zonas", "Seleccioná una zona.", parent=self)
            return
        if kind != "clean":
            messagebox.showinfo(
                "Zonas",
                "La zona seleccionada está bloqueada. Desbloqueala para limpiarla.",
                parent=self,
            )
            return
        self._v109_prepare_plan_origin()
        self._run_zones_now(
            [zone],
            "vacuum",
            int(self.suction_var.get()),
            0,
        )

    def _v109_matching_block_for_zone(self, zone):
        if not self.plan_store:
            return None
        target = self._v109_rect_signature(zone)
        for wall in self.plan_store.snapshot().get("no_go", []):
            if self._v109_rect_signature(wall) == target:
                return wall
        return None

    def _v109_toggle_selected_zone_block(self):
        kind, zone = self._v109_selected_zone()
        if zone is None or not self.plan_store:
            messagebox.showinfo("Zonas", "Seleccioná una zona.", parent=self)
            return
        if kind == "block":
            self.plan_store.delete_no_go(zone.get("id"))
            self._set_banner(f"Zona “{zone.get('name','Zona')}” desbloqueada.")
        else:
            wall = self._v109_matching_block_for_zone(zone)
            if wall is not None:
                self.plan_store.delete_no_go(wall.get("id"))
                self._set_banner(
                    f"Zona “{zone.get('name','Zona')}” desbloqueada."
                )
            else:
                self.plan_store.add_no_go(
                    f"Bloqueo · {zone.get('name','Zona')}",
                    zone["x0"],
                    zone["y0"],
                    zone["x1"],
                    zone["y1"],
                )
                self._set_banner(
                    f"Zona “{zone.get('name','Zona')}” bloqueada."
                )
        self._sync_no_go_async()
        self._v109_refresh_side_panel(force=True)
        self._render_maps()

    def _v109_delete_selected_zone(self):
        kind, zone = self._v109_selected_zone()
        if zone is None or not self.plan_store:
            return
        if not messagebox.askyesno(
            "Eliminar zona",
            f"¿Eliminar “{zone.get('name','Zona')}”?",
            parent=self,
        ):
            return
        if kind == "clean":
            self.plan_store.delete_zone(zone.get("id"))
        else:
            self.plan_store.delete_no_go(zone.get("id"))
            self._sync_no_go_async()
        self._v109_selected_zone_key.set("")
        self._v109_refresh_side_panel(force=True)
        self._render_maps()

    # ======================================= coordenadas raw para limpiar zona
    def _v109_prepare_plan_origin(self):
        if not self.plan_store:
            return False
        raw = (
            getattr(self, "_v77_base_raw", None)
            or getattr(self, "_v71_session_origin_raw", None)
        )
        if raw is None:
            return False
        try:
            x, y = float(raw[0]), float(raw[1])
        except Exception:
            return False

        plan = self.plan_store.snapshot()
        current = plan.get("device_origin")
        changed = True
        if isinstance(current, dict):
            try:
                changed = (
                    abs(float(current.get("x")) - x) > 1e-6
                    or abs(float(current.get("y")) - y) > 1e-6
                )
            except Exception:
                changed = True
        if changed:
            self.plan_store.set_device_origin(x, y)
            self._v109_origin_repairs += 1
        self._v109_last_origin_raw = (x, y)
        return True

    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        self._v109_prepare_plan_origin()
        return result

    def clean_local_room(self, room):
        self._v109_prepare_plan_origin()
        return super().clean_local_room(room)

    def _run_zones_now(self, zones, mode, suction, water):
        self._v109_prepare_plan_origin()
        return super()._run_zones_now(zones, mode, suction, water)

    # =========================================== cliente final físico V109
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV109)
        ):
            self._v40_client = XiaomiE10MapV109(vacuum, settings)
            self._v40_client_vacuum = vacuum

        try:
            points = (
                list(self.local_map.snapshot().get("points") or [])
                if self.local_map
                else []
            )
            self._v40_client.set_v109_reference_path(points)
        except Exception:
            pass
        return self._v40_client

    # ============================================== diagnóstico de emergencia
    def _v109_emergency_diagnostic(self, exc):
        self._v109_diag_fallbacks += 1
        self._v109_last_diag_error = (
            f"{type(exc).__name__}: {str(exc).strip() or repr(exc)}"
        )

        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception as snap_exc:
            snapshot = {}
            snapshot_error = (
                f"{type(snap_exc).__name__}: "
                f"{str(snap_exc).strip() or repr(snap_exc)}"
            )
        else:
            snapshot_error = "—"

        try:
            map_id = self._v72_active_map_id() or "—"
        except Exception:
            map_id = "—"

        points = list((snapshot or {}).get("points") or [])
        native = (snapshot or {}).get("native_grid")
        native_cells = (
            sum(1 for value in list((native or {}).get("cells") or []) if int(value))
            if isinstance(native, dict)
            else 0
        )

        lines = [
            "DIAGNÓSTICO V109 DE EMERGENCIA",
            "================================",
            "El diagnóstico completo heredado falló, pero V109 evita dejar la ventana vacía.",
            "",
            f"error diagnóstico: {self._v109_last_diag_error}",
            f"error snapshot: {snapshot_error}",
            f"mapa activo: {map_id}",
            f"mapping_active: {bool(getattr(self, 'mapping_active', False))}",
            f"mapping_phase: {getattr(self, 'mapping_phase', None)!r}",
            f"status físico: {getattr(self, '_v84_physical_status', None)!r}",
            f"retorno: {bool(getattr(self, '_v84_returning', False))}",
            f"dock: {bool(getattr(self, '_v84_dock_latched', False))}",
            f"puntos locales: {len(points)}",
            f"native_grid presente: {isinstance(native, dict)}",
            f"native_grid celdas: {native_cells}",
            f"origen raw zonas: {self._v109_last_origin_raw!r}",
            f"V107 final guardado: {bool(getattr(self, '_v107_final_saved', False))}",
            f"V108 modo visual: {getattr(self, '_v108_last_mode', '—')}",
            "",
            "Regla V109: esta salida mínima siempre debe aparecer aunque falle una sección heredada.",
        ]
        return "\n".join(lines)

    def _diagnostic_text(self):
        try:
            inherited = super()._diagnostic_text()
            self._v109_diag_full_ok += 1
            client = getattr(self, "_v40_client", None)
            map_diag = dict(
                getattr(client, "last_v109_diagnostics", {}) or {}
            ) if client is not None else {}
            top = list(map_diag.get("top") or [])[:5]
            map_lines = [
                "DIAGNÓSTICO V109 ACTIVO · físico + zonas + privacidad",
                "================================================================",
                (
                    f"diagnósticos completos OK={self._v109_diag_full_ok} · "
                    f"fallbacks={self._v109_diag_fallbacks} · "
                    f"último error={self._v109_last_diag_error}"
                ),
                (
                    "privacidad: estado visible=Conectado · "
                    "direcciones IPv4 redactadas automáticamente"
                ),
                (
                    f"origen raw para zonas={self._v109_last_origin_raw!r} · "
                    f"reparaciones={self._v109_origin_repairs} · "
                    "escala local→raw=metros/0.10"
                ),
                (
                    f"panel derecho: refresh={self._v109_panel_refreshes} · "
                    "abajo sólo Administrar mapas"
                ),
                (
                    f"layout final físico: fuente={map_diag.get('source','—')} · "
                    f"trayectoria={map_diag.get('path_points','—')} pts · "
                    f"seleccionado={map_diag.get('selected_key','—')} · "
                    f"orientación={map_diag.get('orientation','—')} · "
                    f"score={map_diag.get('score','—')}"
                ),
                (
                    f"ajuste físico={map_diag.get('physics','—')} · "
                    f"celdas={map_diag.get('cells','—')}"
                ),
                "top layouts físicos:",
            ]
            if top:
                for index, item in enumerate(top, start=1):
                    map_lines.append(
                        f"  #{index} {item.get('key')} · "
                        f"{item.get('orientation')} · score={item.get('score')} · "
                        f"cobertura={item.get('coverage')} · "
                        f"distμ={item.get('mean_distance')} · "
                        f"p90={item.get('p90')} · celdas={item.get('nonzero')}"
                    )
            else:
                map_lines.append("  — todavía sin captura final V109 —")

            map_lines.extend([
                (
                    "regla V109: el layout final se elige contra la trayectoria "
                    "física real, no sólo por conectividad del bitmap"
                ),
                (
                    "regla V109: habitación/zona se convierte de metros locales "
                    "a raw E10 usando 1 raw = 0,10 m"
                ),
                (
                    "regla V109: una excepción heredada no puede dejar F12 en blanco"
                ),
                "",
                "",
            ])
            text = "\n".join(map_lines) + str(inherited or "")
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)

        redacted, count = self._v109_redact_ips(text)
        self._v109_redactions += int(count)
        return redacted

    # ============================================ ventana F12 a prueba de fallo
    def _refresh_map_diag_window(self):
        win = getattr(self, "_map_diag_window", None)
        box = getattr(self, "_map_diag_text", None)
        try:
            if (
                not win
                or not win.winfo_exists()
                or not box
                or not box.winfo_exists()
            ):
                return
        except Exception:
            return

        try:
            text = self._diagnostic_text()
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)

        if not str(text or "").strip():
            self._v109_diag_fallbacks += 1
            text = (
                "DIAGNÓSTICO V109 DE EMERGENCIA\n"
                "================================\n"
                "La cadena de diagnóstico devolvió texto vacío.\n"
                f"mapping_active={bool(getattr(self, 'mapping_active', False))}\n"
                f"status={getattr(self, '_v84_physical_status', None)!r}\n"
                f"modo visual={getattr(self, '_v108_last_mode', '—')}\n"
            )

        try:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", str(text))
            box.configure(state="disabled")
            self._v109_diag_refreshes += 1
        except Exception:
            return

        try:
            win.after(700, self._refresh_map_diag_window)
        except Exception:
            pass

    def _copy_map_diagnostics(self):
        try:
            text = self._diagnostic_text()
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)
        if not str(text or "").strip():
            text = self._v109_emergency_diagnostic(
                RuntimeError("diagnóstico vacío")
            )
        redacted, count = self._v109_redact_ips(text)
        self._v109_redactions += int(count)
        try:
            self.clipboard_clear()
            self.clipboard_append(redacted)
            self.update_idletasks()
            self._v109_diag_copy_ok += 1
            self._set_banner(
                "Diagnóstico copiado · direcciones IP ocultas."
            )
        except Exception:
            pass


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

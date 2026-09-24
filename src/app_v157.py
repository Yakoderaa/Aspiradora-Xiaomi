import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

import app_v156
import app_v23
import app_v110
import app_v9
from robot_plans import local_rect_to_device
from route_learning_v157 import RouteLearningStoreV157, TrajectorySamplerV157
from target_geometry_v157 import room_local_rects
from targeted_v157 import TargetedRunnerV157
from whole_home_v157 import WholeHomeRunnerV157


SURFACE = app_v110.SURFACE
SURFACE_2 = app_v110.SURFACE_2
TEXT = app_v110.TEXT
MUTED = app_v110.MUTED
BORDER = app_v110.BORDER
ACCENT = app_v110.ACCENT
GREEN = app_v110.GREEN
GREEN_SOFT = app_v110.GREEN_SOFT
RED = app_v110.RED
DAY_NAMES = app_v23.DAY_NAMES
MODE_LABELS = app_v23.MODE_LABELS


class App(app_v156.App):
    """V157: una sola limpieza de vivienda + aprendizaje principal + rutinas."""

    # Más liviano sin quitar telemetría necesaria.
    LOCAL_ACTIVE_POLL_MS = 5000
    LOCAL_IDLE_POLL_MS = 30000
    LOCAL_BUSY_RETRY_MS = 2000
    RENDER_MIN_INTERVAL_SECONDS = 5.0
    UI_EVENT_BUDGET = 80

    def __init__(self):
        self._v157_learning_store = None
        self._v157_whole_active = False
        self._v157_whole_sampler = None
        self._v157_last_whole = {}
        self._v157_target_active = False
        self._v157_last_target = {}
        self._v157_last_origin = None
        self._v157_room_renames = 0
        self.schedule_room_vars = {}
        super().__init__()
        self._v157_learning_store = RouteLearningStoreV157(self.store.folder)
        self._v157_migrate_v156_guide()
        self._v157_sync_primary_to_v156()
        try:
            self._refresh_scheduler_page()
        except Exception:
            pass

    # ========================================================= Espacios
    def _build_map_page_v22(self):
        result = super()._build_map_page_v22()
        body = getattr(self, "_v110_side_host", None)
        if body is None:
            return result
        try:
            if getattr(self, "_v157_spaces_whole_frame", None) is not None:
                return result
            children = list(body.winfo_children())
            before = children[1] if len(children) > 1 else None
            frame = tk.Frame(body, bg=SURFACE)
            kwargs = {"fill": "x", "pady": (0, 12)}
            if before is not None:
                kwargs["before"] = before
            frame.pack(**kwargs)
            self._v157_spaces_whole_frame = frame

            button = tk.Button(
                frame,
                text="Limpiar vivienda",
                command=self.start_clean,
                bg="#2563eb",
                fg="white",
                activebackground="#1d4ed8",
                activeforeground="white",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 10, "bold"),
                padx=14,
                pady=10,
            )
            button.pack(fill="x")
            self._v157_spaces_whole_button = button
            tk.Label(
                frame,
                text="Principal · aprende la vivienda completa y mejora la guía general.",
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=300,
                justify="left",
            ).pack(anchor="w", pady=(5, 0))
        except Exception:
            pass
        return result

    # ================================================== guía / aprendizaje
    def _v157_migrate_v156_guide(self):
        store = self._v157_learning_store
        if store is None or store.primary() is not None:
            return
        points = list((getattr(self, "_v156_guide", {}) or {}).get("points") or [])
        if points:
            store.merge_primary(points, source="migrated-v156")

    def _v157_sync_primary_to_v156(self):
        if self._v157_learning_store is None:
            return
        primary = self._v157_learning_store.primary()
        if not primary:
            return
        self._v156_guide = dict(primary)
        try:
            self._v156_guide_cells = self._v156_cells_from_points(
                primary.get("points") or []
            )
        except Exception:
            self._v156_guide_cells = set()

    def _v157_whole_home(self, source="gui"):
        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return False
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá el mapeo antes de limpiar la vivienda.",
                parent=self,
            )
            return False
        if self._v157_whole_active or self._v157_target_active:
            self._set_banner("Ya hay una limpieza gestionada por V157 en curso.")
            return False

        try:
            core = self._fresh()
            if bool(core.diagnostic().get("active")):
                self._set_banner("El robot ya está ocupado por otra acción.")
                return False
            before = core._read()
        except Exception as exc:
            messagebox.showerror(
                "Limpiar vivienda",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return False

        sampler = TrajectorySamplerV157(
            self.vacuum,
            sample_m=0.25,
            prestart_robot=before.get("robot"),
        )
        self._v157_whole_sampler = sampler
        self._v157_whole_active = True
        self._set_banner(
            "Limpiar vivienda · misma ruta principal V157 · lectura + un único START 2/1."
        )

        def worker():
            runner = WholeHomeRunnerV157(core, source=source)

            def started(diag):
                self._post_ui("v157_whole_started", dict(diag or {}))

            def state(values):
                sampler.note_state(values)

            def idle(diag):
                self._post_ui("v157_whole_idle", dict(diag or {}))

            diag = runner.run(
                on_started=started,
                on_state=state,
                on_idle=idle,
            )
            learned = False
            learned_stats = sampler.stats()
            if (
                not diag.get("error")
                and diag.get("finish_reason") in ("dock", "dock_requested")
                and self._v157_learning_store is not None
            ):
                learned, learned_stats = self._v157_learning_store.merge_primary(
                    sampler.points,
                    source=str(source),
                )
            self._post_ui(
                "v157_whole_finished",
                dict(diag or {}),
                bool(learned),
                dict(learned_stats or {}),
            )

        threading.Thread(
            target=worker,
            name="V157WholeHome",
            daemon=True,
        ).start()
        return True

    def start_clean(self):
        # TODOS los botones globales heredados terminan acá.
        return self._v157_whole_home(source="whole-home-unified")

    # ================================================ telemetría / origen
    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        if not isinstance(state, dict) or not self.plan_store:
            return result
        try:
            base = self.vacuum.parse_position(state.get("charging_base"))
        except Exception:
            base = None
        if base:
            origin = (float(base["x"]), float(base["y"]))
            previous = self._v157_last_origin
            if (
                previous is None
                or abs(origin[0] - previous[0]) > 1e-6
                or abs(origin[1] - previous[1]) > 1e-6
            ):
                try:
                    self.plan_store.set_device_origin(*origin)
                    self._v157_last_origin = origin
                except Exception:
                    pass
        return result

    # ========================================= limpieza habitación / zona
    def _v157_plan_with_origin(self):
        if not self.plan_store:
            raise RuntimeError("No hay plan activo.")
        plan = self.plan_store.snapshot()
        origin = plan.get("device_origin")
        if not isinstance(origin, dict):
            base = getattr(self, "_v156_base_raw", None)
            if base is not None:
                self.plan_store.set_device_origin(float(base[0]), float(base[1]))
                plan = self.plan_store.snapshot()
        if not isinstance(plan.get("device_origin"), dict):
            raise RuntimeError(
                "Todavía no está calibrada la base del mapa. Abrí el mapa unos segundos con el robot en la base."
            )
        return plan

    def _v157_start_target_job(
        self,
        local_rects,
        label,
        learn_key,
        mode="vacuum",
        suction=2,
        water=0,
        source="gui-target",
    ):
        if not getattr(self, "vacuum", None):
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return False
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo("Mapeo en curso", "Terminá el mapeo antes de limpiar un espacio.", parent=self)
            return False
        if self._v157_whole_active or self._v157_target_active:
            self._set_banner("Ya hay una limpieza V157 en curso.")
            return False

        try:
            plan = self._v157_plan_with_origin()
            raw_rects = [
                local_rect_to_device(rect, plan)
                for rect in list(local_rects or [])
            ]
            if not raw_rects:
                raise RuntimeError("No hay superficie para limpiar.")
            core = self._fresh()
            if bool(core.diagnostic().get("active")):
                raise RuntimeError("El robot ya está ocupado.")
            before = core._read()
        except Exception as exc:
            messagebox.showerror(
                "Limpieza dirigida",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return False

        sampler = TrajectorySamplerV157(
            self.vacuum,
            sample_m=0.20,
            prestart_robot=before.get("robot"),
        )
        self._v157_target_active = True
        self._v114_target_clean_active = True
        self._zone_job_running = True
        self._set_banner(f"{label} · iniciando limpieza dirigida V157…")

        passes = ["vacuum", "mop"] if str(mode) == "vacuum_then_mop" else [str(mode)]

        def worker():
            last_diag = {}
            for pass_mode in passes:
                runner = TargetedRunnerV157(core, source=source)
                last_diag = runner.run(
                    raw_rects,
                    mode=pass_mode,
                    suction=suction,
                    water=water,
                    on_stage=lambda i, total: self._post_ui(
                        "plan_job_stage",
                        f"{label} · sector {i}/{total}",
                    ),
                    on_state=sampler.note_state,
                )
                if last_diag.get("error"):
                    break

            learned = False
            stats = sampler.stats()
            if (
                not last_diag.get("error")
                and self._v157_learning_store is not None
            ):
                learned, stats = self._v157_learning_store.merge_target(
                    learn_key,
                    sampler.points,
                    label=label,
                    source=source,
                )
            self._post_ui(
                "v157_target_finished",
                str(label),
                dict(last_diag or {}),
                bool(learned),
                dict(stats or {}),
            )

        threading.Thread(
            target=worker,
            name="V157TargetClean",
            daemon=True,
        ).start()
        return True

    def clean_local_room(self, room):
        room = dict(room or {})
        room_id = str(room.get("id") or "")
        plan = self.plan_store.snapshot() if self.plan_store else {}
        try:
            rects = room_local_rects(
                room,
                no_go=plan.get("no_go") or [],
            )
        except Exception as exc:
            messagebox.showerror("Limpiar habitación", str(exc), parent=self)
            return False
        try:
            suction = int(self.suction_var.get())
        except Exception:
            suction = 2
        return self._v157_start_target_job(
            rects,
            f"Habitación “{room.get('name', 'Habitación')}”",
            f"room:{room_id}",
            mode="vacuum",
            suction=suction,
            water=0,
            source="room-button",
        )

    def _run_zones_now(self, zones, mode, suction, water):
        zones = [dict(item) for item in list(zones or []) if isinstance(item, dict)]
        if not zones:
            return False
        key = "zone:" + ",".join(sorted(str(item.get("id") or "") for item in zones))
        label = (
            f"Zona “{zones[0].get('name','Zona')}”"
            if len(zones) == 1
            else f"{len(zones)} zonas"
        )
        return self._v157_start_target_job(
            zones,
            label,
            key,
            mode=mode,
            suction=suction,
            water=water,
            source="zone-button",
        )

    def _v114_run_safe_rectangles(
        self,
        target,
        kind,
        label,
        mode,
        suction,
        water,
    ):
        return self._v157_start_target_job(
            [dict(target)],
            str(label),
            f"{kind}:{str((target or {}).get('id') or label)}",
            mode=mode,
            suction=suction,
            water=water,
            source="legacy-target-routed-v157",
        )

    # ===================================================== renombrar habitación
    def _v157_rename_selected_room(self):
        room = self._v110_selected_room()
        if room is None:
            return
        current = str(room.get("name") or "Habitación")
        name = simpledialog.askstring(
            "Renombrar habitación",
            "Nuevo nombre:",
            initialvalue=current,
            parent=self,
        )
        if name is None or not str(name).strip():
            return
        try:
            self.local_map.rename_room(int(room.get("id")), str(name).strip())
            self._v157_room_renames += 1
            self._v110_render_side(force=True)
            self._refresh_scheduler_page()
            self._render_maps()
            self._set_banner(f"Habitación renombrada a “{str(name).strip()}”.")
        except Exception as exc:
            messagebox.showerror("Renombrar habitación", str(exc), parent=self)

    def _v110_render_rooms(self, host, rooms):
        result = super()._v110_render_rooms(host, rooms)
        if self._v110_selected_room() is not None:
            self._button(
                host,
                "Renombrar habitación",
                self._v157_rename_selected_room,
                compact=True,
            ).pack(fill="x", pady=(7, 0))
        return result

    # ======================================================= Programar UI
    def _build_scheduler_page(self):
        result = super()._build_scheduler_page()
        buttons = getattr(self, "_schedule_target_buttons", None)
        if not isinstance(buttons, dict) or "all" not in buttons:
            return result
        try:
            buttons["all"].configure(text="Vivienda")
            if "zones" in buttons:
                buttons["zones"].configure(text="Zonas")
            parent = buttons["all"].master
            room_btn = tk.Button(
                parent,
                text="Habitaciones",
                command=lambda: self._set_schedule_target("rooms"),
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                padx=10,
                pady=9,
            )
            room_btn.pack(side="left", fill="x", expand=True, padx=5)
            buttons["rooms"] = room_btn

            zone_frame = self.schedule_zone_frame
            room_frame = tk.Frame(
                zone_frame.master,
                bg=SURFACE_2,
                padx=12,
                pady=10,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            room_frame.pack(
                fill="x",
                pady=(10, 0),
                before=zone_frame,
            )
            self.schedule_room_frame = room_frame
            self.schedule_room_vars = {}
            self._refresh_schedule_target_buttons()
        except Exception:
            pass
        return result

    def _refresh_schedule_target_buttons(self):
        result = super()._refresh_schedule_target_buttons()
        selected = str(self.schedule_target_var.get()) if hasattr(self, "schedule_target_var") else "all"
        frame = getattr(self, "schedule_room_frame", None)
        if frame is not None:
            try:
                frame.configure(
                    highlightbackground=ACCENT if selected == "rooms" else BORDER
                )
            except Exception:
                pass
        return result

    def _refresh_scheduler_page(self):
        if not self.plan_store or not hasattr(self, "schedule_zone_frame"):
            return

        plan = self.plan_store.snapshot()
        rooms = list(self.local_map.snapshot().get("rooms") or []) if self.local_map else []
        zones = list(plan.get("zones") or [])

        room_frame = getattr(self, "schedule_room_frame", None)
        if room_frame is not None:
            previous_rooms = {
                rid: var.get()
                for rid, var in getattr(self, "schedule_room_vars", {}).items()
            }
            for child in room_frame.winfo_children():
                child.destroy()
            self.schedule_room_vars = {}
            tk.Label(
                room_frame,
                text="Habitaciones disponibles",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", pady=(0, 5))
            if not rooms:
                tk.Label(
                    room_frame,
                    text="No hay habitaciones creadas en este mapa.",
                    bg=SURFACE_2,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                ).pack(anchor="w")
            for room in rooms:
                rid = str(room.get("id"))
                var = tk.BooleanVar(value=previous_rooms.get(rid, False))
                self.schedule_room_vars[rid] = var
                tk.Checkbutton(
                    room_frame,
                    text=str(room.get("name") or "Habitación"),
                    variable=var,
                    bg=SURFACE_2,
                    activebackground=SURFACE_2,
                    selectcolor=SURFACE,
                    fg=TEXT,
                    font=("Segoe UI", 8),
                ).pack(anchor="w", pady=1)

        previous_zones = {
            zid: var.get()
            for zid, var in getattr(self, "schedule_zone_vars", {}).items()
        }
        for child in self.schedule_zone_frame.winfo_children():
            child.destroy()
        self.schedule_zone_vars = {}
        tk.Label(
            self.schedule_zone_frame,
            text="Zonas disponibles",
            bg=SURFACE_2,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        if not zones:
            tk.Label(
                self.schedule_zone_frame,
                text="No hay zonas guardadas en este mapa.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor="w")
        for zone in zones:
            zid = str(zone.get("id"))
            var = tk.BooleanVar(value=previous_zones.get(zid, False))
            self.schedule_zone_vars[zid] = var
            tk.Checkbutton(
                self.schedule_zone_frame,
                text=str(zone.get("name") or "Zona"),
                variable=var,
                bg=SURFACE_2,
                activebackground=SURFACE_2,
                selectcolor=SURFACE,
                fg=TEXT,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=1)

        for child in self.schedule_list_frame.winfo_children():
            child.destroy()
        schedules = list(plan.get("schedules") or [])
        active_count = sum(1 for item in schedules if bool(item.get("enabled", True)))
        if getattr(self, "_schedule_summary_label", None):
            self._schedule_summary_label.configure(
                text=f"{active_count} activa{'s' if active_count != 1 else ''} · {len(schedules)} total"
            )

        if not schedules:
            empty = tk.Frame(
                self.schedule_list_frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            empty.pack(fill="x", pady=8)
            tk.Label(
                empty,
                text="Todavía no hay rutinas",
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI Semibold", 12),
            ).pack(anchor="w", padx=18, pady=(18, 4))
            tk.Label(
                empty,
                text="Podés programar la vivienda completa, habitaciones o zonas.",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).pack(anchor="w", padx=18, pady=(0, 18))
            return

        rooms_by_id = {str(r.get("id")): str(r.get("name") or "Habitación") for r in rooms}
        zones_by_id = {str(z.get("id")): str(z.get("name") or "Zona") for z in zones}

        for schedule in schedules:
            enabled_value = bool(schedule.get("enabled", True))
            card = tk.Frame(
                self.schedule_list_frame,
                bg=SURFACE_2,
                highlightthickness=1,
                highlightbackground=ACCENT if enabled_value else BORDER,
            )
            card.pack(fill="x", pady=5)

            time_box = tk.Frame(card, bg="#f1f5f9", width=112)
            time_box.pack(side="left", fill="y")
            time_box.pack_propagate(False)
            tk.Label(
                time_box,
                text=f"{int(schedule.get('hour',0)):02d}:{int(schedule.get('minute',0)):02d}",
                bg="#f1f5f9",
                fg=TEXT,
                font=("Segoe UI Semibold", 18),
            ).pack(pady=(15, 2))
            tk.Label(
                time_box,
                text="ACTIVA" if enabled_value else "PAUSADA",
                bg=GREEN_SOFT if enabled_value else "#e2e8f0",
                fg=GREEN if enabled_value else MUTED,
                font=("Segoe UI", 7, "bold"),
                padx=7,
                pady=3,
            ).pack()

            center = tk.Frame(card, bg=SURFACE_2)
            center.pack(side="left", fill="both", expand=True, padx=14, pady=11)
            tk.Label(
                center,
                text=str(schedule.get("name") or "Limpieza"),
                bg=SURFACE_2,
                fg=TEXT,
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="w")
            days_text = " · ".join(
                DAY_NAMES[int(i)]
                for i in schedule.get("days", [])
                if 0 <= int(i) < 7
            ) or "Sin días"
            tk.Label(
                center,
                text=days_text,
                bg=SURFACE_2,
                fg=ACCENT,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", pady=(4, 2))

            target_type = str(schedule.get("target") or "all")
            if target_type == "rooms":
                names = [
                    rooms_by_id.get(str(rid), "habitación eliminada")
                    for rid in schedule.get("room_ids", [])
                ]
                target_text = "Habitaciones: " + ", ".join(names)
            elif target_type == "zones":
                names = [
                    zones_by_id.get(str(zid), "zona eliminada")
                    for zid in schedule.get("zone_ids", [])
                ]
                target_text = "Zonas: " + ", ".join(names)
            else:
                target_text = "Vivienda · misma acción que Limpiar vivienda"

            mode_name = next(
                (
                    label
                    for label, value in MODE_LABELS.items()
                    if value == schedule.get("mode")
                ),
                str(schedule.get("mode", "Aspirar")),
            )
            tk.Label(
                center,
                text=f"{mode_name} · {target_text}",
                bg=SURFACE_2,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=510,
                justify="left",
            ).pack(anchor="w", pady=(0, 6))

            actions = tk.Frame(center, bg=SURFACE_2)
            actions.pack(fill="x", pady=(2, 0))
            self._button(
                actions,
                "Ejecutar ahora",
                lambda s=dict(schedule): self._run_schedule_now(s),
                compact=True,
                accent=True,
            ).pack(side="left")
            self._button(
                actions,
                "Eliminar",
                lambda sid=schedule["id"]: self._delete_schedule(sid),
                compact=True,
                danger=True,
            ).pack(side="left", padx=(7, 0))

            toggle = tk.Button(
                card,
                text="Pausar" if enabled_value else "Activar",
                command=lambda sid=schedule["id"], state=enabled_value: self._toggle_schedule_v23(sid, not state),
                bg=SURFACE,
                fg=MUTED if enabled_value else GREEN,
                activebackground="#eef2f6",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=7,
            )
            toggle.pack(side="right", padx=12)

    def _add_schedule_from_form(self):
        try:
            hour = int(self.schedule_hour_var.get())
            minute = int(self.schedule_minute_var.get())
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except Exception:
            messagebox.showerror(
                "Programación",
                "Ingresá una hora válida entre 00:00 y 23:59.",
                parent=self,
            )
            return

        days = [i for i, var in enumerate(self.schedule_day_vars) if var.get()]
        if not days:
            messagebox.showinfo("Programación", "Elegí al menos un día.", parent=self)
            return

        target = str(self.schedule_target_var.get() or "all")
        zone_ids = [
            str(zid)
            for zid, var in getattr(self, "schedule_zone_vars", {}).items()
            if var.get()
        ]
        room_ids = [
            str(rid)
            for rid, var in getattr(self, "schedule_room_vars", {}).items()
            if var.get()
        ]
        if target == "zones" and not zone_ids:
            messagebox.showinfo("Programación", "Elegí al menos una zona.", parent=self)
            return
        if target == "rooms" and not room_ids:
            messagebox.showinfo("Programación", "Elegí al menos una habitación.", parent=self)
            return

        item = {
            "name": self.schedule_name_var.get().strip() or "Limpieza",
            "enabled": True,
            "days": days,
            "hour": hour,
            "minute": minute,
            "mode": MODE_LABELS[self.schedule_mode_var.get()],
            "suction": int(self.schedule_suction_var.get()),
            "water": int(self.schedule_water_var.get()),
            "target": target,
            "zone_ids": zone_ids,
            "room_ids": room_ids,
        }
        self.plan_store.add_schedule(item)
        self._refresh_scheduler_page()
        self._set_banner(
            "Rutina guardada. Vivienda usa exactamente Limpiar vivienda; "
            "habitaciones y zonas conservan su objetivo por ID."
        )

    def _run_schedule_now(self, schedule):
        schedule = dict(schedule or {})
        target = str(schedule.get("target") or "all")
        if target == "all":
            # MISMA función y MISMA ruta que cualquier botón Iniciar limpieza.
            return self.start_clean()

        if target == "rooms":
            rooms = list(self.local_map.snapshot().get("rooms") or []) if self.local_map else []
            by_id = {str(r.get("id")): r for r in rooms}
            selected = [
                by_id[str(rid)]
                for rid in schedule.get("room_ids", [])
                if str(rid) in by_id
            ]
            if not selected:
                self._post_ui("plan_job_error", "La rutina no tiene habitaciones válidas.")
                return False

            # Una rutina con varias habitaciones se ejecuta como una sola tarea
            # dirigida compuesta; cada habitación conserva su ID aunque cambie nombre.
            plan = self.plan_store.snapshot()
            rects = []
            labels = []
            for room in selected:
                rects.extend(room_local_rects(room, no_go=plan.get("no_go") or []))
                labels.append(str(room.get("name") or "Habitación"))
            return self._v157_start_target_job(
                rects,
                "Habitaciones: " + ", ".join(labels),
                "rooms:" + ",".join(sorted(str(r.get("id")) for r in selected)),
                mode=schedule.get("mode", "vacuum"),
                suction=schedule.get("suction", 2),
                water=schedule.get("water", 0),
                source="schedule-now-rooms",
            )

        plan = self.plan_store.snapshot()
        by_id = {str(z.get("id")): z for z in plan.get("zones", [])}
        selected = [
            by_id[str(zid)]
            for zid in schedule.get("zone_ids", [])
            if str(zid) in by_id
        ]
        if not selected:
            self._post_ui("plan_job_error", "La rutina no tiene zonas válidas.")
            return False
        return self._v157_start_target_job(
            selected,
            "Zonas programadas",
            "zones:" + ",".join(sorted(str(z.get("id")) for z in selected)),
            mode=schedule.get("mode", "vacuum"),
            suction=schedule.get("suction", 2),
            water=schedule.get("water", 0),
            source="schedule-now-zones",
        )

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v157_whole_started":
            self._set_banner(
                "Limpiar vivienda activo · único START 2/1 · aprendiendo guía principal."
            )
            return None

        if kind == "v157_whole_idle":
            self._set_banner(
                "Limpiar vivienda · E10 quedó inactivo/sin batería; "
                "la sesión espera status=4 para guardar el aprendizaje completo."
            )
            return None

        if kind == "v157_whole_finished":
            diag = dict(payload[0] or {}) if payload else {}
            learned = bool(payload[1]) if len(payload) > 1 else False
            stats = dict(payload[2] or {}) if len(payload) > 2 else {}
            self._v157_whole_active = False
            self._v157_last_whole = {
                "diag": diag,
                "learned": learned,
                "stats": stats,
            }
            self._v157_sync_primary_to_v156()
            if diag.get("error"):
                self._set_banner("Limpiar vivienda terminó con error: " + str(diag["error"]))
            elif learned:
                self._set_banner(
                    "Limpiar vivienda finalizada · guía principal aprendida/refinada · "
                    f"{stats.get('points',0)} celdas/puntos de referencia."
                )
            else:
                self._set_banner(
                    "Limpiar vivienda finalizada · no se modificó la guía "
                    "porque el ciclo no terminó confirmado en la base."
                )
            return None

        if kind == "v157_target_finished":
            label = str(payload[0])
            diag = dict(payload[1] or {})
            learned = bool(payload[2]) if len(payload) > 2 else False
            stats = dict(payload[3] or {}) if len(payload) > 3 else {}
            self._v157_target_active = False
            self._v114_target_clean_active = False
            self._zone_job_running = False
            self._v157_last_target = {
                "label": label,
                "diag": diag,
                "learned": learned,
                "stats": stats,
            }
            if diag.get("error"):
                self._post_ui("plan_job_error", str(diag.get("error")))
            else:
                self._post_ui(
                    "plan_job_done",
                    f"{label} · limpieza completada"
                    + (" · aprendizaje secundario guardado." if learned else "."),
                )
            return None

        if kind == "v155_mapping_finished":
            diag = dict(payload[1] or {}) if len(payload) > 1 else {}
            result = super()._handle_ui_event(kind, payload)
            if (
                not diag.get("error")
                and diag.get("finish_reason") in ("dock", "dock_requested")
                and self._v157_learning_store is not None
            ):
                self._v157_learning_store.merge_primary(
                    list(getattr(self, "_v156_candidate", []) or []),
                    source="mapping-v157",
                )
                self._v157_sync_primary_to_v156()
            return result

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        primary = (
            self._v157_learning_store.primary()
            if self._v157_learning_store is not None
            else None
        )
        core = getattr(self, "_fresh_core", None)
        core_diag = core.diagnostic() if core is not None else {}
        stats = dict((primary or {}).get("stats") or {})
        targets = {}
        if self._v157_learning_store is not None:
            try:
                targets = dict(self._v157_learning_store.load().get("targets") or {})
            except Exception:
                targets = {}
        lines = [
            "V157 VIVIENDA ÚNICA + IA DE RECORRIDO · LITE",
            "==============================================",
            "Limpiar vivienda = Iniciar limpieza = rutina Vivienda = MISMA función",
            "ruta global física: precheck de lectura -> UN A2/1",
            f"limpieza vivienda activa={self._v157_whole_active}",
            f"última vivienda={self._v157_last_whole or '—'}",
            (
                "guía principal: "
                f"runs={(primary or {}).get('runs',0)} · "
                f"points={stats.get('points',0)} · "
                f"span={stats.get('span_x',0.0)}×{stats.get('span_y',0.0)} m"
            ),
            f"aprendizajes secundarios={len(targets)}",
            f"último objetivo={self._v157_last_target or '—'}",
            f"renombres habitación={self._v157_room_renames}",
            (
                "rendimiento: "
                f"LAN={getattr(self,'_v95_local_polls_started',0)} · "
                f"UI={getattr(self,'_v96_ui_events_processed',0)} · "
                f"renders={getattr(self,'_v96_render_executed',0)} · "
                "Cloud recorrido=OFF"
            ),
            f"writes heredados bloqueados={core_diag.get('legacy_blocks',0)}",
            "programador: vivienda / habitaciones por ID / zonas",
            "2/3, 7/3, EDGE, remoto y recoveries automáticos siguen fuera",
        ]
        return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

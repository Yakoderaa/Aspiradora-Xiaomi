import math
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

import app_v129
import app_v9
from robot_plans import (
    constrain_polygon_to_native_grid,
    local_rect_to_device,
    native_grid_contains_point,
    start_zone_clean,
    sync_virtual_walls,
    wait_for_cleaning_cycle,
)
from xiaomi_e10_map_v130 import XiaomiE10MapV130


class App(app_v129.App):
    """V130: final robusto + origen 10/22 + habitaciones poligonales."""

    V130_DOCK_COLLAPSE_RATIO = 0.62
    V130_RETURN_READS = 3
    V130_RETURN_READ_PAUSE = 1.25
    V130_ROOM_VERTEX_SNAP_M = 0.10

    def __init__(self):
        self._v130_return_candidate = None
        self._v130_return_candidate_started = False
        self._v130_return_candidate_finished = False
        self._v130_return_candidate_errors = []
        self._v130_return_candidate_cells = 0
        self._v130_final_source = "—"
        self._v130_final_capture_failed = False
        self._v130_stale_1024_origins_blocked = 0
        self._v130_origin_from_1022 = 0
        self._v130_last_base_raw = None

        self._v130_polygon_mode = None
        self._v130_polygon_points = []
        self._v130_polygon_room_id = None
        self._v130_polygon_drag_index = None
        self._v130_polygon_toolbar_widgets = []
        self._v130_polygon_rooms_created = 0
        self._v130_polygon_rooms_edited = 0
        self._v130_point_selection_blocks = 0

        self._v130_room_clean_attempts = 0
        self._v130_room_clean_commands = 0
        self._v130_room_clean_completed = 0
        self._v130_room_clean_errors = 0
        self._v130_last_room_clean_error = "—"
        super().__init__()

    # ========================================================= cliente V130
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV130)
        ):
            self._v40_client = XiaomiE10MapV130(vacuum, settings)
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

        try:
            self._v40_client.set_v111_area_raw(
                getattr(self, "_v111_area_raw_max", 0),
                getattr(self, "_v111_area_m2_max", 0.0),
            )
        except Exception:
            pass
        return self._v40_client

    # ======================================== origen físico: 10/22, no 10/24
    def _v130_read_base_1022(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return None
        try:
            values = vacuum._get_many([("charging_base", 10, 22)])
            raw = values.get("charging_base")
            xy = self._v77_valid_base_xy(raw)
            if xy is None:
                return None
            return float(xy[0]), float(xy[1])
        except Exception:
            return None

    def _v71_set_origin(self, xy, source):
        source_text = str(source or "")
        if "10/24 antes de fase 1 perímetro V121" in source_text:
            self._v130_stale_1024_origins_blocked += 1
            base = self._v130_read_base_1022()
            if base is None:
                # Esperamos a que V77 vea charging_base. Un 10/24 viejo nunca
                # vuelve a transformarse en origen de la sesión.
                return False
            self._v77_base_raw = tuple(base)
            self._v130_last_base_raw = tuple(base)
            self._v130_origin_from_1022 += 1
            return super()._v71_set_origin(
                base,
                "10/22 chargingbase al iniciar mapa · V130",
            )
        return super()._v71_set_origin(xy, source)

    def _v109_prepare_plan_origin(self):
        base = self._v130_read_base_1022()
        if base is not None and getattr(self, "plan_store", None):
            try:
                self.plan_store.set_device_origin(base[0], base[1])
                self._v77_base_raw = tuple(base)
                self._v109_last_origin_raw = tuple(base)
                self._v130_last_base_raw = tuple(base)
                self._v130_origin_from_1022 += 1
                return True
            except Exception:
                pass
        return super()._v109_prepare_plan_origin()

    # ========================================== nueva sesión sin grid anterior
    def start_new_mapping(self):
        was_active = bool(getattr(self, "mapping_active", False))
        result = super().start_new_mapping()
        if not was_active and bool(getattr(self, "mapping_active", False)):
            self._v130_return_candidate = None
            self._v130_return_candidate_started = False
            self._v130_return_candidate_finished = False
            self._v130_return_candidate_errors = []
            self._v130_return_candidate_cells = 0
            self._v130_final_source = "—"
            self._v130_final_capture_failed = False

            # V107/V105 podían conservar flags/cachés de la sesión anterior
            # aunque V121 hubiese vaciado LocalMapStore.
            self._v107_final_grid = None
            self._v107_final_saved = False
            self._v107_final_candidates = 0
            self._v107_final_unique = 0
            self._v107_final_choice_reason = "nueva sesión V130"
            self._v107_hide_surface_until_final = True
            try:
                map_id = self._v105_map_id()
                self._v105_frozen_previews.pop(map_id, None)
                self._v100_live_grids.pop(map_id, None)
            except Exception:
                pass

            self.selected_point = None
            try:
                self.map_selected_xy = None
            except Exception:
                pass
            self._v130_cancel_polygon_room(render=False)
            try:
                self._render_maps()
            except Exception:
                pass
        return result

    # ============================= captura de seguridad durante status=3
    def _v130_capture_return_candidate_async(self):
        if self._v130_return_candidate_started:
            return False
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False

        self._v130_return_candidate_started = True
        settings = dict(self.settings or {})

        def worker():
            best = None
            best_cells = 0
            errors = []
            client = None
            try:
                client = XiaomiE10MapV130(vacuum, settings)
                try:
                    points = (
                        list(self.local_map.snapshot().get("points") or [])
                        if self.local_map
                        else []
                    )
                    client.set_v109_reference_path(points)
                except Exception:
                    pass
                try:
                    client.set_v111_area_raw(
                        getattr(self, "_v111_area_raw_max", 0),
                        getattr(self, "_v111_area_m2_max", 0.0),
                    )
                except Exception:
                    pass
                client.set_v107_final_mode(True)

                for index in range(int(self.V130_RETURN_READS)):
                    if vacuum is not getattr(self, "vacuum", None):
                        break
                    try:
                        if index > 0:
                            try:
                                client.request_live_upload()
                            except Exception:
                                pass
                            time.sleep(float(self.V130_RETURN_READ_PAUSE))

                        snapshot = client.load_live_partial()
                        grid = self._v107_grid_from_snapshot(snapshot)
                        if not isinstance(grid, dict):
                            raise RuntimeError("sin grid durante retorno")
                        cells = [
                            1 if int(value) else 0
                            for value in list(grid.get("cells") or [])
                        ]
                        metrics = dict(client._grid_metrics(cells) or {})
                        grid["metrics"] = dict(metrics)
                        count = int(sum(cells))
                        try:
                            client.note_v130_candidate(
                                f"return-read-{index + 1}",
                                grid,
                                metrics,
                            )
                        except Exception:
                            pass
                        if bool(metrics.get("valid")) and count > best_cells:
                            best = dict(grid)
                            best_cells = count
                    except Exception as exc:
                        errors.append(
                            f"retorno {index + 1}: "
                            + (str(exc).strip() or type(exc).__name__)
                        )
            except Exception as exc:
                errors.append(str(exc).strip() or type(exc).__name__)
            finally:
                if client is not None:
                    try:
                        client.set_v107_final_mode(False)
                    except Exception:
                        pass

            self._post_ui(
                "v130_return_candidate_done",
                best,
                best_cells,
                errors,
            )

        threading.Thread(
            target=worker,
            name="AspiradoraReturnMapV130",
            daemon=True,
        ).start()
        return True

    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))
        result = super()._render_status(status)

        if (
            physical == 3
            and bool(getattr(self, "_v121_phase2_departed", False))
            and not self._v130_return_candidate_started
        ):
            self._v130_capture_return_candidate_async()
        return result

    def _v107_choose_final_grid(self, grids):
        chosen, reason = super()._v107_choose_final_grid(grids)
        fallback = (
            dict(self._v130_return_candidate)
            if isinstance(self._v130_return_candidate, dict)
            else None
        )

        if chosen is None and fallback is not None:
            self._v130_final_source = "retorno status=3"
            self._v130_final_capture_failed = False
            return (
                fallback,
                "V130 fallback: captura válida durante retorno; "
                "las lecturas de dock fueron inválidas",
            )

        if isinstance(chosen, dict) and fallback is not None:
            dock_cells = int(sum(
                1 for value in list(chosen.get("cells") or []) if int(value)
            ))
            return_cells = int(sum(
                1 for value in list(fallback.get("cells") or []) if int(value)
            ))
            if (
                return_cells > 0
                and dock_cells
                < float(return_cells) * float(self.V130_DOCK_COLLAPSE_RATIO)
            ):
                self._v130_final_source = "retorno status=3"
                self._v130_final_capture_failed = False
                return (
                    fallback,
                    "V130 fallback: el frame de dock colapsó a "
                    f"{dock_cells}/{return_cells} celdas respecto al retorno",
                )

        if isinstance(chosen, dict):
            self._v130_final_source = "dock"
            self._v130_final_capture_failed = False
        else:
            self._v130_final_source = "sin captura válida"
            self._v130_final_capture_failed = True
        return chosen, reason

    def _v93_sync_map_status_label(self):
        if self._v130_final_capture_failed and not bool(
            getattr(self, "_v93_finalizing", False)
        ):
            label = getattr(self, "map_status_label", None)
            if label is not None:
                text = (
                    "Mapeo terminado · Xiaomi no entregó una geometría "
                    "final válida para esta sesión"
                )
                self._v93_last_status_text = text
                try:
                    label.configure(text=text, fg="#b45309")
                except Exception:
                    pass
                return
        return super()._v93_sync_map_status_label()

    # ============================================ punto aislado: eliminado UI
    def clean_selected_point(self):
        self.selected_point = None
        try:
            self.map_selected_xy = None
        except Exception:
            pass
        return None

    def _map_double_click(self, event):
        if self._v130_polygon_mode:
            if len(self._v130_polygon_points) >= 3:
                self._v130_finish_polygon_room()
            return "break"

        self._v130_point_selection_blocks += 1
        self.selected_point = None
        try:
            self.map_selected_xy = None
        except Exception:
            pass
        return "break"

    # =============================================== habitaciones rect/puntos
    def _v130_map_has_geometry(self):
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            return False
        grid = snapshot.get("native_grid")
        if isinstance(grid, dict) and any(
            int(value) for value in list(grid.get("cells") or [])
        ):
            return True
        return bool(snapshot.get("points"))

    def enable_room_editor(self):
        if not self._v130_map_has_geometry():
            messagebox.showinfo(
                "Habitaciones",
                "Primero terminá un mapa para definir habitaciones.",
                parent=self,
            )
            return

        chooser = tk.Toplevel(self)
        chooser.title("Nueva habitación")
        chooser.transient(self)
        chooser.resizable(False, False)
        body = tk.Frame(chooser, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="Cómo querés dibujar la habitación",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        tk.Label(
            body,
            text=(
                "Rectangular sirve para ambientes simples. Por puntos permite "
                "formas en L, pasillos y habitaciones irregulares."
            ),
            justify="left",
            wraplength=340,
        ).pack(anchor="w", pady=(5, 14))

        def rectangle():
            chooser.destroy()
            self._v130_cancel_polygon_room(render=False)
            self.room_edit_mode = True
            self._plan_draw_mode = None
            self._set_banner(
                "Habitación rectangular · arrastrá sobre el mapa para definirla."
            )

        def polygon():
            chooser.destroy()
            self._v130_start_polygon_room()

        self._button(
            body,
            "Habitación rectangular",
            rectangle,
            accent=True,
            compact=True,
        ).pack(fill="x", pady=(0, 7))
        self._button(
            body,
            "Habitación por puntos",
            polygon,
            compact=True,
        ).pack(fill="x")
        chooser.update_idletasks()
        try:
            chooser.grab_set()
        except Exception:
            pass

    def _v130_clear_polygon_toolbar(self):
        for widget in list(self._v130_polygon_toolbar_widgets):
            try:
                widget.destroy()
            except Exception:
                pass
        self._v130_polygon_toolbar_widgets = []

    def _v130_install_polygon_toolbar(self):
        self._v130_clear_polygon_toolbar()
        host = getattr(self, "_zone_tools_slot", None)
        if host is None:
            return

        finish_text = (
            "Guardar habitación"
            if self._v130_polygon_mode == "edit"
            else "Finalizar habitación"
        )
        finish = self._button(
            host,
            finish_text,
            self._v130_finish_polygon_room,
            accent=True,
            compact=True,
        )
        finish.pack(side="right", padx=(6, 0))
        cancel = self._button(
            host,
            "Cancelar",
            self._v130_cancel_polygon_room,
            compact=True,
        )
        cancel.pack(side="right")
        self._v130_polygon_toolbar_widgets = [finish, cancel]

    def _v130_start_polygon_room(self):
        self.room_edit_mode = False
        self._plan_draw_mode = None
        self._v130_polygon_mode = "create"
        self._v130_polygon_points = []
        self._v130_polygon_room_id = None
        self._v130_polygon_drag_index = None
        self.selected_point = None
        try:
            self.map_selected_xy = None
        except Exception:
            pass
        self._v130_install_polygon_toolbar()
        self._set_banner(
            "Habitación por puntos · hacé clic en cada vértice. "
            "Volvé al primer punto o usá Finalizar habitación."
        )
        self._render_maps()

    def _v130_edit_polygon_room(self):
        room = self._v110_selected_room()
        polygon = list((room or {}).get("polygon") or [])
        if len(polygon) < 3:
            return
        self.room_edit_mode = False
        self._plan_draw_mode = None
        self._v130_polygon_mode = "edit"
        self._v130_polygon_points = [
            (float(point["x"]), float(point["y"]))
            for point in polygon
        ]
        self._v130_polygon_room_id = room.get("id")
        self._v130_polygon_drag_index = None
        self._v130_install_polygon_toolbar()
        self._set_banner(
            "Editar habitación · arrastrá cualquiera de los vértices y "
            "después elegí Guardar habitación."
        )
        self._render_maps()

    def _v130_cancel_polygon_room(self, render=True):
        self._v130_polygon_mode = None
        self._v130_polygon_points = []
        self._v130_polygon_room_id = None
        self._v130_polygon_drag_index = None
        self._v130_clear_polygon_toolbar()
        try:
            self.map_canvas.delete("v130_poly_preview")
        except Exception:
            pass
        if render:
            try:
                self._render_maps()
            except Exception:
                pass

    @staticmethod
    def _v130_orientation(a, b, c):
        value = (
            (float(b[1]) - float(a[1])) * (float(c[0]) - float(b[0]))
            - (float(b[0]) - float(a[0])) * (float(c[1]) - float(b[1]))
        )
        if abs(value) < 1e-9:
            return 0
        return 1 if value > 0 else 2

    @classmethod
    def _v130_segments_intersect(cls, a, b, c, d):
        return (
            cls._v130_orientation(a, b, c)
            != cls._v130_orientation(a, b, d)
            and cls._v130_orientation(c, d, a)
            != cls._v130_orientation(c, d, b)
        )

    @classmethod
    def _v130_polygon_simple(cls, points):
        points = list(points or [])
        count = len(points)
        if count < 3:
            return False
        for i in range(count):
            a = points[i]
            b = points[(i + 1) % count]
            for j in range(i + 1, count):
                if j == i or (j + 1) % count == i or (i + 1) % count == j:
                    continue
                c = points[j]
                d = points[(j + 1) % count]
                if cls._v130_segments_intersect(a, b, c, d):
                    return False
        return True

    @staticmethod
    def _v130_point_in_polygon(x, y, polygon):
        points = list(polygon or [])
        if len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = float(points[i][0]), float(points[i][1])
            xj, yj = float(points[j][0]), float(points[j][1])
            if (
                (yi > y) != (yj > y)
                and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    def _v130_snap_room_point(self, point):
        step = float(self.V130_ROOM_VERTEX_SNAP_M)
        try:
            native = self.local_map.snapshot().get("native_grid")
            resolution = float((native or {}).get("resolution", 0.0) or 0.0)
            if resolution > 0.0:
                step = max(0.05, resolution / 2.0)
        except Exception:
            pass
        return (
            round(float(point[0]) / step) * step,
            round(float(point[1]) / step) * step,
        )

    def _v130_point_near_floor(self, point):
        try:
            native = self.local_map.snapshot().get("native_grid")
        except Exception:
            native = None
        if not isinstance(native, dict):
            return True

        base = {"x": float(point[0]), "y": float(point[1])}
        if native_grid_contains_point(base, native):
            return True
        try:
            resolution = float(native.get("resolution", 0.2) or 0.2)
        except Exception:
            resolution = 0.2
        for dx, dy in (
            (-resolution, 0.0),
            (resolution, 0.0),
            (0.0, -resolution),
            (0.0, resolution),
            (-resolution, -resolution),
            (-resolution, resolution),
            (resolution, -resolution),
            (resolution, resolution),
        ):
            if native_grid_contains_point(
                {"x": point[0] + dx, "y": point[1] + dy},
                native,
            ):
                return True
        return False

    def _v130_screen_points(self):
        transform = getattr(self, "_map_transforms", {}).get(
            getattr(self, "map_canvas", None)
        )
        if not transform:
            return []
        scale = float(transform.get("scale", 1.0) or 1.0)
        min_x = float(transform.get("min_x", 0.0))
        max_y = float(transform.get("max_y", 0.0))
        pad = float(transform.get("pad", 28.0))
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)
        return [
            (
                pad + (float(x) - min_x) * scale + pan_x,
                pad + (max_y - float(y)) * scale + pan_y,
            )
            for x, y in self._v130_polygon_points
        ]

    def _v130_draw_polygon_preview(self):
        canvas = getattr(self, "map_canvas", None)
        if canvas is None or not self._v130_polygon_mode:
            return
        try:
            canvas.delete("v130_poly_preview")
        except Exception:
            return
        screen = self._v130_screen_points()
        if not screen:
            return

        flat = [coord for point in screen for coord in point]
        if len(flat) >= 4:
            canvas.create_line(
                *flat,
                fill="#4f46e5",
                width=3,
                joinstyle=tk.ROUND,
                tags=("v130_poly_preview",),
            )
        if len(screen) >= 3:
            canvas.create_line(
                screen[-1][0],
                screen[-1][1],
                screen[0][0],
                screen[0][1],
                fill="#818cf8",
                width=2,
                dash=(5, 3),
                tags=("v130_poly_preview",),
            )
        for index, (x, y) in enumerate(screen):
            radius = 6 if index == 0 else 5
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#4f46e5",
                outline="white",
                width=2,
                tags=("v130_poly_preview",),
            )

    def _drawing_on_map(self):
        if self._v130_polygon_mode:
            return True
        return super()._drawing_on_map()

    def _map_press(self, event):
        if not self._v130_polygon_mode:
            return super()._map_press(event)

        screen = self._v130_screen_points()
        if self._v130_polygon_mode == "edit":
            best = None
            best_distance = 15.0
            for index, point in enumerate(screen):
                distance = math.hypot(
                    float(event.x) - point[0],
                    float(event.y) - point[1],
                )
                if distance < best_distance:
                    best = index
                    best_distance = distance
            self._v130_polygon_drag_index = best
            return "break"

        if (
            len(screen) >= 3
            and math.hypot(
                float(event.x) - screen[0][0],
                float(event.y) - screen[0][1],
            ) <= 14.0
        ):
            self._v130_finish_polygon_room()
            return "break"

        point = self._canvas_to_world(
            self.map_canvas,
            event.x,
            event.y,
        )
        if point is None:
            return "break"
        point = self._v130_snap_room_point(point)
        if not self._v130_point_near_floor(point):
            self._set_banner(
                "Ese vértice quedó demasiado lejos de la superficie Xiaomi."
            )
            return "break"
        if self._v130_polygon_points and math.hypot(
            point[0] - self._v130_polygon_points[-1][0],
            point[1] - self._v130_polygon_points[-1][1],
        ) < 0.05:
            return "break"

        self._v130_polygon_points.append(point)
        self._v130_draw_polygon_preview()
        self._set_banner(
            f"Habitación por puntos · {len(self._v130_polygon_points)} "
            "vértices · seguí marcando o elegí Finalizar habitación."
        )
        return "break"

    def _map_drag(self, event):
        if not self._v130_polygon_mode:
            return super()._map_drag(event)
        if (
            self._v130_polygon_mode == "edit"
            and self._v130_polygon_drag_index is not None
        ):
            point = self._canvas_to_world(
                self.map_canvas,
                event.x,
                event.y,
            )
            if point is not None:
                point = self._v130_snap_room_point(point)
                if self._v130_point_near_floor(point):
                    self._v130_polygon_points[
                        self._v130_polygon_drag_index
                    ] = point
                    self._v130_draw_polygon_preview()
        return "break"

    def _map_release(self, event):
        if self._v130_polygon_mode:
            self._v130_polygon_drag_index = None
            return "break"
        return super()._map_release(event)

    def _v130_finish_polygon_room(self):
        points = list(self._v130_polygon_points)
        if len(points) < 3:
            self._set_banner(
                "La habitación por puntos necesita al menos 3 vértices."
            )
            return
        if not self._v130_polygon_simple(points):
            messagebox.showwarning(
                "Habitación por puntos",
                "Los lados de la habitación se cruzan. Mové los vértices "
                "hasta formar un polígono simple.",
                parent=self,
            )
            return

        if self._v130_polygon_mode == "edit":
            try:
                room = self.local_map.update_polygon_room(
                    int(self._v130_polygon_room_id),
                    points,
                )
                self._v130_polygon_rooms_edited += 1
            except Exception as exc:
                messagebox.showerror(
                    "Habitación por puntos",
                    str(exc).strip() or type(exc).__name__,
                    parent=self,
                )
                return
            name = room.get("name", "Habitación")
            self._v130_cancel_polygon_room(render=False)
            self._v110_render_side(force=True)
            self._render_maps()
            self._set_banner(f"Habitación “{name}” actualizada.")
            return

        name = simpledialog.askstring(
            "Nueva habitación",
            "Nombre de la habitación:",
            parent=self,
        )
        if name is None:
            return
        try:
            room = self.local_map.add_polygon_room(name, points)
            self._v130_polygon_rooms_created += 1
            if getattr(self, "_v109_selected_room_id", None) is not None:
                self._v109_selected_room_id.set(str(room.get("id")))
        except Exception as exc:
            messagebox.showerror(
                "Habitación por puntos",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return

        self._v130_cancel_polygon_room(render=False)
        self._v110_render_side(force=True)
        self._render_maps()
        self._set_banner(
            f"Habitación “{room.get('name','Habitación')}” creada con "
            f"{len(points)} vértices."
        )

    # ============================ renderer único para rectángulos y polígonos
    def _v87_draw_rooms_and_plan(
        self,
        canvas,
        snapshot,
        xy,
        transform=None,
    ):
        selected = self._v110_selected_room()
        selected_id = self._v110_room_id(selected) if selected else None

        for room in list((snapshot or {}).get("rooms") or []):
            if not isinstance(room, dict):
                continue
            room_id = self._v110_room_id(room)
            active = room_id == selected_id
            polygon = list(room.get("polygon") or [])
            if len(polygon) >= 3:
                coords = []
                world = []
                try:
                    for point in polygon:
                        px = float(point["x"])
                        py = float(point["y"])
                        world.append((px, py))
                        coords.extend(xy(px, py))
                except Exception:
                    continue
                canvas.create_polygon(
                    *coords,
                    fill="",
                    outline="#4f46e5" if active else "#94a3b8",
                    width=3 if active else 1,
                    dash=() if active else (5, 3),
                    tags=("v87_room", "v110_room", "v130_polygon_room"),
                )
                cx = sum(point[0] for point in world) / len(world)
                cy = sum(point[1] for point in world) / len(world)
                sx, sy = xy(cx, cy)
            else:
                try:
                    a = xy(room["x0"], room["y0"])
                    b = xy(room["x1"], room["y1"])
                except Exception:
                    continue
                left, right = sorted((a[0], b[0]))
                top, bottom = sorted((a[1], b[1]))
                canvas.create_rectangle(
                    left,
                    top,
                    right,
                    bottom,
                    outline="#4f46e5" if active else "#94a3b8",
                    width=3 if active else 1,
                    dash=() if active else (5, 3),
                    tags=("v87_room", "v110_room"),
                )
                sx = (left + right) / 2.0
                sy = (top + bottom) / 2.0

            canvas.create_text(
                sx,
                sy,
                text=str(room.get("name") or "Habitación"),
                fill="#111827" if active else "#64748b",
                font=("Segoe UI", 8, "bold"),
                tags=("v87_room", "v110_room"),
            )

        if self.plan_store and selected_id is not None:
            items = self._v110_room_items(selected_id)
            for zone in list(items.get("zones") or []):
                try:
                    a = xy(zone["x0"], zone["y0"])
                    b = xy(zone["x1"], zone["y1"])
                except Exception:
                    continue
                canvas.create_rectangle(
                    min(a[0], b[0]),
                    min(a[1], b[1]),
                    max(a[0], b[0]),
                    max(a[1], b[1]),
                    outline="#16a34a",
                    width=2,
                    dash=(5, 3),
                    tags=("v87_zone", "v110_active_zone"),
                )
            for zone in list(items.get("no_go") or []):
                try:
                    a = xy(zone["x0"], zone["y0"])
                    b = xy(zone["x1"], zone["y1"])
                except Exception:
                    continue
                canvas.create_rectangle(
                    min(a[0], b[0]),
                    min(a[1], b[1]),
                    max(a[0], b[0]),
                    max(a[1], b[1]),
                    outline="#dc2626",
                    width=2,
                    dash=(6, 4),
                    tags=("v87_nogo", "v110_active_zone"),
                )

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        if (
            canvas is getattr(self, "map_canvas", None)
            and self._v130_polygon_mode
        ):
            self._v130_draw_polygon_preview()
        return result

    def _v110_render_rooms(self, host, rooms):
        result = super()._v110_render_rooms(host, rooms)
        room = self._v110_selected_room()
        if len(list((room or {}).get("polygon") or [])) >= 3:
            self._button(
                host,
                "Editar vértices",
                self._v130_edit_polygon_room,
                compact=True,
            ).pack(fill="x", pady=(7, 0))
        return result

    def _v110_zone_inside_room(self, zone, room, tolerance=0.03):
        polygon = list((room or {}).get("polygon") or [])
        if len(polygon) < 3:
            return super()._v110_zone_inside_room(
                zone,
                room,
                tolerance=tolerance,
            )
        try:
            x0, x1 = sorted((float(zone["x0"]), float(zone["x1"])))
            y0, y1 = sorted((float(zone["y0"]), float(zone["y1"])))
        except Exception:
            return False

        points = [
            (float(point["x"]), float(point["y"]))
            for point in polygon
        ]
        # Muestreo denso suficiente para evitar que una zona rectangular corte
        # por fuera de una concavidad del polígono.
        for ix in range(5):
            x = x0 + (x1 - x0) * ix / 4.0
            for iy in range(5):
                y = y0 + (y1 - y0) * iy / 4.0
                if not self._v130_point_in_polygon(x, y, points):
                    return False
        return True

    def _v109_toggle_selected_room_block(self):
        room = self._v110_selected_room()
        if len(list((room or {}).get("polygon") or [])) >= 3:
            messagebox.showinfo(
                "Habitación irregular",
                "Para bloquear una parte de una habitación irregular usá "
                "“+ Bloqueo” dentro de Zonas.",
                parent=self,
            )
            return
        return super()._v109_toggle_selected_room_block()

    # ============================================= limpieza real de habitación
    def _v130_run_polygon_room(self, room):
        if not self.vacuum:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(self._v114_target_clean_active) or bool(
            getattr(self, "_zone_job_running", False)
        ):
            messagebox.showinfo(
                "Limpieza",
                "Ya hay una limpieza dirigida gestionada por la app.",
                parent=self,
            )
            return

        label = f"Habitación “{room.get('name', 'Habitación')}”"
        self._v130_room_clean_attempts += 1
        try:
            map_id, _snapshot, native, plan = self._v114_active_map_context()
            constrained = constrain_polygon_to_native_grid(
                room.get("polygon") or [],
                native,
                no_go=plan.get("no_go") or [],
                max_rectangles=48,
            )
        except Exception as exc:
            self._v130_room_clean_errors += 1
            self._v130_last_room_clean_error = (
                str(exc).strip() or type(exc).__name__
            )
            messagebox.showerror(
                "Limpiar habitación",
                self._v130_last_room_clean_error,
                parent=self,
            )
            return

        rects = [dict(item) for item in constrained["rectangles"]]
        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v114_map_fingerprint_before = original_fp
        self._v114_map_fingerprint_after = original_fp
        self._v114_target_clean_active = True
        self._zone_job_running = True
        self._v114_target_clean_kind = "room-polygon"
        self._v114_target_clean_label = label
        self._v114_target_clean_map_id = map_id
        self._v114_target_requested = dict(constrained["requested"])
        self._v114_target_rects = list(rects)
        self._v114_target_raw_rects = [
            local_rect_to_device(rect, plan) for rect in rects
        ]
        self._v114_target_requested_area = float(
            constrained["requested_area"]
        )
        self._v114_target_allowed_area = float(
            constrained["allowed_area"]
        )
        self._v114_target_coverage_ratio = float(
            constrained["coverage_ratio"]
        )
        self._v114_target_selected_cells = int(
            constrained["selected_cells"]
        )
        self._v114_target_blocked_cells = int(
            constrained["blocked_cells"]
        )

        try:
            suction = max(1, min(4, int(self.suction_var.get())))
        except Exception:
            suction = 1
        vacuum = self.vacuum

        def worker():
            guard_started = False
            try:
                vacuum.begin_targeted_clean()
                guard_started = True
                sync_virtual_walls(vacuum, plan)
                total = len(rects)
                for index, rect in enumerate(rects, start=1):
                    if str(self.local_map.active_map_id or "") != map_id:
                        raise RuntimeError(
                            "El mapa activo cambió durante la limpieza."
                        )
                    self._post_ui(
                        "plan_job_stage",
                        f"{label} · sector {index}/{total}",
                    )
                    start_zone_clean(
                        vacuum,
                        rect,
                        plan,
                        "vacuum",
                        suction,
                        0,
                    )
                    self._v114_target_commands += 1
                    self._v130_room_clean_commands += 1

                    # wait_for_cleaning_cycle no acepta un ACK como éxito:
                    # exige observar status físico 5/6/7.
                    wait_for_cleaning_cycle(vacuum)
                    self._v114_target_completed += 1
                    self._v130_room_clean_completed += 1
                    self._v114_restore_grid_if_needed(
                        original_grid,
                        original_fp,
                        map_id,
                    )
                    time.sleep(0.8)

                self._post_ui(
                    "plan_job_done",
                    f"{label} · limpieza completada.",
                )
            except Exception as exc:
                self._v114_target_errors += 1
                self._v130_room_clean_errors += 1
                self._v130_last_room_clean_error = (
                    str(exc).strip() or type(exc).__name__
                )
                self._v114_last_target_error = self._v130_last_room_clean_error
                self._post_ui(
                    "plan_job_error",
                    self._v130_last_room_clean_error,
                )
            finally:
                if guard_started:
                    try:
                        vacuum.end_targeted_clean()
                    except Exception:
                        pass
                self._v114_restore_grid_if_needed(
                    original_grid,
                    original_fp,
                    map_id,
                )
                self._v114_target_clean_active = False
                self._zone_job_running = False

        threading.Thread(
            target=worker,
            name="AspiradoraPolygonRoomV130",
            daemon=True,
        ).start()

    def clean_local_room(self, room):
        self._v130_room_clean_attempts += 1
        self._v109_prepare_plan_origin()
        if len(list((room or {}).get("polygon") or [])) >= 3:
            # El helper cuenta su propio intento; compensamos para mantener un
            # contador por clic del usuario.
            self._v130_room_clean_attempts -= 1
            return self._v130_run_polygon_room(room)
        return super().clean_local_room(room)

    # =================================== fase1 vs fase2: diagnóstico de huecos
    def _v130_phase_gap_metrics(self):
        try:
            points = list(self.local_map.snapshot().get("points") or [])
        except Exception:
            points = []
        cell = 0.40
        phase1 = set()
        phase2 = set()
        for point in points:
            if not isinstance(point, dict):
                continue
            try:
                key = (
                    int(round(float(point["x"]) / cell)),
                    int(round(float(point["y"]) / cell)),
                )
                phase = int(point.get("phase", 0) or 0)
            except Exception:
                continue
            if phase == 1:
                phase1.add(key)
            elif phase == 2:
                phase2.add(key)

        covered_near = set()
        for x, y in phase2:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    covered_near.add((x + dx, y + dy))
        edge_only = phase1 - covered_near
        return {
            "cell_m": cell,
            "phase1_cells": len(phase1),
            "phase2_cells": len(phase2),
            "phase1_without_phase2_nearby": len(edge_only),
            "ratio_pending": (
                float(len(edge_only)) / float(len(phase1))
                if phase1 else 0.0
            ),
        }

    def _v130_persist_late_return_candidate(self):
        candidate = (
            dict(self._v130_return_candidate)
            if isinstance(self._v130_return_candidate, dict)
            else None
        )
        if candidate is None or not getattr(self, "local_map", None):
            return False
        try:
            self.local_map.set_native_grid(candidate)
            self._v107_final_grid = dict(candidate)
            self._v107_final_saved = True
            self._v107_hide_surface_until_final = False
            self._v130_final_capture_failed = False
            self._v130_final_source = "retorno status=3 tardío"
            self._v107_final_choice_reason = (
                "V130 fallback tardío: retorno válido tras dock inválido"
            )

            map_id = self._v105_map_id()
            self._v105_frozen_previews[map_id] = (
                self._v105_copy_grid(candidate)
            )
            self._v100_live_grids[map_id] = dict(candidate)
            self._v70_refresh_map_overview(force=True)
            self._v96_last_render_at = 0.0
            self._render_maps()
            self._set_banner(
                "Mapa Xiaomi final recuperado desde la captura válida "
                "del regreso a base."
            )
            return True
        except Exception as exc:
            self._v130_return_candidate_errors.append(
                "persistencia tardía: "
                + (str(exc).strip() or type(exc).__name__)
            )
            return False

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v130_return_candidate_done":
            candidate = payload[0] if payload else None
            cells = int(payload[1]) if len(payload) > 1 else 0
            errors = list(payload[2]) if len(payload) > 2 else []
            self._v130_return_candidate_finished = True
            self._v130_return_candidate_errors = errors[-4:]
            if isinstance(candidate, dict):
                self._v130_return_candidate = dict(candidate)
                self._v130_return_candidate_cells = cells

                # Si las 3 lecturas de dock ya terminaron y fueron inválidas,
                # la captura de retorno puede llegar unos segundos después.
                # En ese caso se publica ahora, sin esperar otro evento.
                finalized = (
                    int(getattr(self, "_v93_finalized_serial", -1) or -1)
                    == int(getattr(self, "_v74_mapping_serial", 0) or 0)
                )
                if finalized and not bool(
                    getattr(self, "_v107_final_saved", False)
                ):
                    self._v130_persist_late_return_candidate()
            return None

        if kind == "v107_final_grid_done":
            result = super()._handle_ui_event(kind, payload)
            if not bool(getattr(self, "_v107_final_saved", False)):
                self._v130_final_capture_failed = True
            self._v93_sync_map_status_label()
            return result

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V130 ACTIVO · cierre final + habitaciones poligonales",
            "==================================================================",
            (
                "origen: 10/24 viejo bloqueado="
                f"{self._v130_stale_1024_origins_blocked} · "
                f"10/22 aplicado={self._v130_origin_from_1022} · "
                f"base={self._v130_last_base_raw or '—'}"
            ),
            (
                "fallback mapa: retorno iniciado="
                f"{self._v130_return_candidate_started} · terminado="
                f"{self._v130_return_candidate_finished} · celdas="
                f"{self._v130_return_candidate_cells} · fuente final="
                f"{self._v130_final_source}"
            ),
            (
                f"errores captura retorno={self._v130_return_candidate_errors or []} · "
                f"fallo final={self._v130_final_capture_failed}"
            ),
            (
                "habitaciones poligonales: creadas="
                f"{self._v130_polygon_rooms_created} · editadas="
                f"{self._v130_polygon_rooms_edited} · modo="
                f"{self._v130_polygon_mode or '—'} · vértices="
                f"{len(self._v130_polygon_points)}"
            ),
            (
                "limpieza habitación: intentos="
                f"{self._v130_room_clean_attempts} · comandos="
                f"{self._v130_room_clean_commands} · completados="
                f"{self._v130_room_clean_completed} · errores="
                f"{self._v130_room_clean_errors} · último="
                f"{self._v130_last_room_clean_error}"
            ),
            f"cobertura Paso1/Paso2={self._v130_phase_gap_metrics()}",
            (
                "selección de punto aislado: eliminada · dobles clic bloqueados="
                f"{self._v130_point_selection_blocks}"
            ),
            "regla V130: 10/22 chargingbase manda como origen físico; un 10/24 previo al START no puede anclar la sesión",
            "regla V130: las 3 lecturas de dock siguen siendo primarias; sólo se usa el retorno si dock es inválido o colapsa",
            "regla V130: habitación = rectángulo o polígono; ambos usan la misma coordenada local y el mismo grid Xiaomi",
            "regla V130: una habitación poligonal se rasteriza a subzonas E10 y cada sector exige status físico 5/6/7",
            "regla V130: el antiatasco de Fase 2 sigue siendo PASIVO como V129",
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

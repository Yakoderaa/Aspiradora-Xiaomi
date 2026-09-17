import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog

import app_v17
from backup_bundle import auto_backup, read_bundle, write_bundle
from xiaomi_e10_live import XiaomiE10Live

# app_v9 sólo reexportaba parte de la paleta. v17 usa APP_BG al crear la página
# Programar, así que lo dejamos disponible antes de construir la interfaz.
app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9.APP_BG = "#f4f5f7"

CARD = app_v17.CARD
CARD_ALT = app_v17.CARD_ALT
TEXT = app_v17.TEXT
MUTED = app_v17.MUTED
BORDER = app_v17.BORDER
GREEN = app_v17.GREEN
RED = app_v17.RED


class App(app_v17.App):
    """v18: trayectoria MIoT real + biblioteca de 4 mapas + backup/importación."""

    def __init__(self):
        self._map_library_window = None
        super().__init__()
        self._adopt_legacy_plan_to_active_map()
        self._activate_plan_for_current_map(reset_coordinates=True)
        self._install_map_library_control()
        self.after(1200, self._safe_auto_backup)
        self.after(150, self._render_maps)

    # ---------------------------------------------------- conexión E10 live
    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10Live(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui("connect_error", str(exc).strip() or "El robot no respondió correctamente.", quiet)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------ trayectoria completa en vivo
    def _apply_map_state(self, state):
        path = list((state or {}).get("path") or [])
        phase = int(self.mapping_phase or 0)
        result = super()._apply_map_state(state)

        # Incorporamos todo el tramo devuelto por get-current-path, no sólo el
        # último punto. Así la pared crece incluso si entre sondeos llegaron
        # varias posiciones nuevas.
        if self.mapping_active and phase in (1, 2) and path and not (
            phase == 2 and self.mapping_transitioning
        ):
            try:
                origin_x = float(path[0]["x"])
                origin_y = float(path[0]["y"])
                localized = []
                for index, point in enumerate(path):
                    pid = int(point.get("id", index))
                    localized.append({
                        "id": 500000 + pid,
                        "x": float(point["x"]) - origin_x,
                        "y": float(point["y"]) - origin_y,
                        "phi": float(point.get("phi", 0) or 0),
                        "update": int(point.get("update", 1) or 0),
                    })
                self.local_map.merge_trajectory(localized, phase=phase)
                self._render_maps()
            except Exception:
                pass

        if self.mapping_active and hasattr(self, "map_status_label"):
            snapshot = self.local_map.snapshot() if self.local_map else {}
            wall_points = sum(
                1 for p in snapshot.get("points", []) if int(p.get("phase", 0) or 0) == 1
            )
            source = str((state or {}).get("path_source") or "esperando trayectoria")
            start = (state or {}).get("path_start")
            end = (state or {}).get("path_end")
            direct_count = int((state or {}).get("direct_path_count", 0) or 0)
            action_count = int((state or {}).get("action_path_count", 0) or 0)
            range_text = f" · tramo {start}→{end}" if start is not None or end is not None else ""
            self.map_status_label.configure(
                text=(
                    f"Paredes EN VIVO · {wall_points} muestras · {source}{range_text} "
                    f"· directo {direct_count} / acción {action_count}"
                ),
                fg=GREEN,
            )
        return result

    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        # get-current-path agrega una acción MIoT. ~3 lecturas/s sigue siendo
        # visualmente fluido y evita saturar el E10.
        delay = 340 if self.mapping_active else (750 if self._last_robot_status in (3, 5, 6, 7) else 2200)
        self.after(delay, self._poll_local_map)

    # ---------------------------------------------------------- mapas/planes
    def _adopt_legacy_plan_to_active_map(self):
        if not self.plan_store or not self.local_map:
            return
        active = self.local_map.active_map_id
        data = self.plan_store.snapshot_all()
        changed = False

        for key in ("zones", "no_go", "points", "schedules"):
            for item in data.get(key, []) or []:
                if str(item.get("map_id") or "legacy") == "legacy":
                    item["map_id"] = active
                    changed = True

        origins = data.setdefault("device_origins", {})
        if "legacy" in origins:
            origins.setdefault(active, origins["legacy"])
            origins.pop("legacy", None)
            changed = True
        managed = data.setdefault("virtual_walls_managed_maps", {})
        if "legacy" in managed:
            managed.setdefault(active, managed["legacy"])
            managed.pop("legacy", None)
            changed = True

        if str(data.get("active_map_id") or "legacy") == "legacy":
            data["active_map_id"] = active
            changed = True

        if changed:
            self.plan_store.replace_all(data)
        else:
            self.plan_store.set_active_map(active)

    def _reset_coordinate_session(self):
        self._coord_prev_local.clear()
        self._coord_last_change.clear()
        self._coord_active_source = None
        self._coord_global_last = None
        self._coord_motion_history = []
        self._live_last_point = {1: None, 2: None}

    def _activate_plan_for_current_map(self, reset_coordinates=False):
        if not self.plan_store or not self.local_map:
            return
        map_id = self.local_map.active_map_id
        self.plan_store.set_active_map(map_id)
        plan = self.plan_store.snapshot(map_id)
        origin = plan.get("device_origin")
        if reset_coordinates:
            self._reset_coordinate_session()
        if isinstance(origin, dict) and "x" in origin and "y" in origin:
            self._coord_origins["robot"] = (float(origin["x"]), float(origin["y"]))
        else:
            self._coord_origins.pop("robot", None)
        self.selected_point = None

    def _install_map_library_control(self):
        tools = self.map_status_label.master
        self.map_library_button = self._button(tools, "Mapas", self.open_map_library, compact=True)
        self.map_library_button.pack(side="right", padx=(7, 0))
        self._refresh_map_library_button()

    def _refresh_map_library_button(self):
        if not hasattr(self, "map_library_button") or not self.local_map:
            return
        maps = self.local_map.list_maps()
        active = next((m for m in maps if m.get("active")), maps[0] if maps else None)
        if active:
            self.map_library_button.configure(text=f"Mapas · {active['name']} ({len(maps)}/4)")

    def _render_maps(self):
        result = super()._render_maps()
        self._refresh_map_library_button()
        return result

    def open_map_library(self):
        if not self.local_map or not self.plan_store:
            return
        if self._map_library_window and self._map_library_window.winfo_exists():
            self._map_library_window.destroy()

        win = tk.Toplevel(self)
        win.title("Biblioteca de mapas")
        win.geometry("680x520")
        win.minsize(620, 460)
        win.transient(self)
        self._map_library_window = win

        shell = tk.Frame(win, padx=18, pady=16)
        shell.pack(fill="both", expand=True)
        head = tk.Frame(shell)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="Mapas guardados", font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(head, text="Máximo 4", fg="#777", font=("Segoe UI", 9)).pack(side="right")

        list_frame = tk.Frame(shell)
        list_frame.pack(fill="both", expand=True)

        footer = tk.Frame(shell)
        footer.pack(fill="x", pady=(14, 0))
        create_button = self._button(footer, "+ Nuevo mapa", lambda: self._create_map(rebuild), accent=True, compact=True)
        create_button.pack(side="left")
        self._button(footer, "Importar .xvac", lambda: self._import_backup(win), compact=True).pack(side="right", padx=(8, 0))
        self._button(footer, "Exportar .xvac", self._export_backup, compact=True).pack(side="right")

        def rebuild():
            for child in list_frame.winfo_children():
                child.destroy()
            maps = self.local_map.list_maps()
            for item in maps:
                row = tk.Frame(list_frame, bg=CARD_ALT, highlightthickness=1, highlightbackground=BORDER)
                row.pack(fill="x", pady=4)
                left = tk.Frame(row, bg=CARD_ALT)
                left.pack(side="left", fill="x", expand=True, padx=12, pady=9)
                title = item.get("name", "Mapa") + (" · ACTIVO" if item.get("active") else "")
                tk.Label(left, text=title, bg=CARD_ALT, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
                plan = self.plan_store.snapshot(item["id"])
                detail = (
                    f"{item.get('points', 0)} puntos · {len(plan.get('zones', []))} zonas · "
                    f"{len(plan.get('no_go', []))} bloqueos · {len(plan.get('schedules', []))} programaciones"
                )
                tk.Label(left, text=detail, bg=CARD_ALT, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

                actions = tk.Frame(row, bg=CARD_ALT)
                actions.pack(side="right", padx=8)
                if not item.get("active"):
                    tk.Button(actions, text="Usar", command=lambda mid=item["id"]: self._switch_map(mid, win), relief="flat").pack(side="left", padx=2)
                tk.Button(actions, text="Renombrar", command=lambda m=dict(item): self._rename_map(m, rebuild), relief="flat").pack(side="left", padx=2)
                if len(maps) > 1:
                    tk.Button(actions, text="Eliminar", command=lambda m=dict(item): self._delete_map(m, rebuild), relief="flat", fg=RED).pack(side="left", padx=2)
            create_button.configure(state="normal" if len(maps) < 4 else "disabled")

        rebuild()

    def _mapping_busy(self):
        if self.mapping_active:
            messagebox.showinfo("Mapas", "Terminá el mapeo actual antes de cambiar de mapa.", parent=self)
            return True
        return False

    def _switch_map(self, map_id, window=None):
        if self._mapping_busy():
            return
        try:
            self.local_map.select_map(map_id)
            self._activate_plan_for_current_map(reset_coordinates=True)
            self._refresh_scheduler_page()
            self._render_maps()
            self._sync_no_go_async()
            active = self.local_map.snapshot()
            self._set_banner(f"Mapa activo: {active.get('name', 'Mapa')}.")
            if window and window.winfo_exists():
                window.destroy()
        except Exception as exc:
            messagebox.showerror("Mapas", str(exc), parent=self)

    def _create_map(self, refresh):
        if self._mapping_busy():
            return
        name = simpledialog.askstring("Nuevo mapa", "Nombre del mapa:", parent=self._map_library_window or self)
        if name is None:
            return
        try:
            self.local_map.create_map(name.strip() or "Nuevo mapa")
            self._activate_plan_for_current_map(reset_coordinates=True)
            self._refresh_scheduler_page()
            self._render_maps()
            refresh()
            self._set_banner("Mapa nuevo creado. Colocá el E10 en su base y empezá el mapeo.")
        except Exception as exc:
            messagebox.showerror("Mapas", str(exc), parent=self)

    def _rename_map(self, item, refresh):
        name = simpledialog.askstring("Renombrar mapa", "Nuevo nombre:", initialvalue=item.get("name", "Mapa"), parent=self._map_library_window or self)
        if name is None:
            return
        try:
            self.local_map.rename_map(item["id"], name)
            self._render_maps()
            refresh()
        except Exception as exc:
            messagebox.showerror("Mapas", str(exc), parent=self)

    def _delete_map(self, item, refresh):
        if self._mapping_busy():
            return
        if not messagebox.askyesno(
            "Eliminar mapa",
            f"¿Eliminar “{item.get('name', 'Mapa')}” junto con sus zonas, bloqueos y programaciones?",
            parent=self._map_library_window or self,
        ):
            return
        try:
            deleted_id = item["id"]
            self.local_map.delete_map(deleted_id)
            self.plan_store.delete_map_data(deleted_id)
            self._activate_plan_for_current_map(reset_coordinates=True)
            self._refresh_scheduler_page()
            self._render_maps()
            self._sync_no_go_async()
            refresh()
        except Exception as exc:
            messagebox.showerror("Mapas", str(exc), parent=self)

    # ------------------------------------------------------- export/import
    def _safe_auto_backup(self, prefix="automatico"):
        if not self.local_map or not self.plan_store:
            return None
        try:
            return auto_backup(
                self.store.folder,
                self.local_map.library_snapshot(),
                self.plan_store.snapshot_all(),
                prefix=prefix,
                keep=8,
            )
        except Exception:
            return None

    def _export_backup(self):
        if not self.local_map or not self.plan_store:
            return
        suggested = f"Aspiradora-Xiaomi-{datetime.now().strftime('%Y-%m-%d')}.xvac"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar mapas y programaciones",
            defaultextension=".xvac",
            initialfile=suggested,
            filetypes=[("Respaldo Aspiradora Xiaomi", "*.xvac"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        try:
            write_bundle(path, self.local_map.library_snapshot(), self.plan_store.snapshot_all())
            self._set_banner(f"Respaldo exportado: {path}")
            messagebox.showinfo(
                "Respaldo creado",
                "Se exportaron los mapas, zonas, bloqueos, puntos y programaciones.\n\nEl archivo no contiene tu token ni credenciales Xiaomi.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Exportar", str(exc), parent=self)

    def _import_backup(self, library_window=None):
        if self._mapping_busy():
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Importar mapas y programaciones",
            filetypes=[("Respaldo Aspiradora Xiaomi", "*.xvac"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        try:
            payload = read_bundle(path)
        except Exception as exc:
            messagebox.showerror("Importar", str(exc), parent=self)
            return
        if not messagebox.askyesno(
            "Importar respaldo",
            "Esto reemplazará la biblioteca de mapas, zonas y programaciones actuales.\n\n"
            "Antes voy a crear automáticamente un respaldo de lo que tenés ahora. ¿Continuar?",
            parent=self,
        ):
            return
        try:
            self._safe_auto_backup("antes-de-importar")
            self.local_map.replace_library(payload["maps"])
            self.plan_store.replace_all(payload["cleaning_plan"])
            self.plan_store.set_active_map(self.local_map.active_map_id)
            self._activate_plan_for_current_map(reset_coordinates=True)
            self._refresh_scheduler_page()
            self._render_maps()
            self._sync_no_go_async()
            if library_window and library_window.winfo_exists():
                library_window.destroy()
            self._set_banner("Respaldo importado correctamente.")
        except Exception as exc:
            messagebox.showerror("Importar", str(exc), parent=self)

    # ---------------------------------------------------------- updater
    def _manual_update_found_safe(self, update):
        # AppData no se borra al actualizar. Además dejamos un .xvac local como
        # segunda capa de seguridad antes de instalar la siguiente versión.
        self._safe_auto_backup("antes-de-actualizar")
        return super()._manual_update_found_safe(update)


if __name__ == "__main__":
    app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

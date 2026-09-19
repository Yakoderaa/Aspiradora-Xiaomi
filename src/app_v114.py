import hashlib
import json
import math
import threading
import time
from tkinter import messagebox

import app_v113
import app_v9
from robot_plans import (
    constrain_rect_to_native_grid,
    local_rect_to_device,
    native_grid_contains_point,
    start_point_clean,
    start_zone_clean,
    sync_virtual_walls,
    wait_for_cleaning_cycle,
)


class App(app_v113.App):
    """V114: el mapa Xiaomi guardado gobierna la limpieza dirigida."""

    V114_MAX_SAFE_RECTS = 24

    def __init__(self):
        self._v114_target_clean_active = False
        self._v114_target_clean_kind = "—"
        self._v114_target_clean_label = "—"
        self._v114_target_clean_map_id = None
        self._v114_target_requested = None
        self._v114_target_rects = []
        self._v114_target_raw_rects = []
        self._v114_target_requested_area = 0.0
        self._v114_target_allowed_area = 0.0
        self._v114_target_coverage_ratio = 0.0
        self._v114_target_selected_cells = 0
        self._v114_target_blocked_cells = 0
        self._v114_target_commands = 0
        self._v114_target_completed = 0
        self._v114_target_errors = 0
        self._v114_last_target_error = "—"
        self._v114_map_fingerprint_before = None
        self._v114_map_fingerprint_after = None
        self._v114_map_restores = 0
        self._v114_live_grid_updates_blocked = 0
        self._v114_mapping_ui_blocks = 0
        super().__init__()

    # ======================================================= mapa inmutable
    @staticmethod
    def _v114_grid_fingerprint(grid):
        if not isinstance(grid, dict):
            return None
        try:
            payload = {
                "side": int(grid.get("side", 0) or 0),
                "resolution": round(
                    float(grid.get("resolution", 0.0) or 0.0), 8
                ),
                "base_cell": [
                    round(float(value), 6)
                    for value in list(grid.get("base_cell") or [])[:2]
                ],
                "cells": [
                    int(value) for value in list(grid.get("cells") or [])
                ],
            }
        except Exception:
            return None
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def _v114_active_map_context(self):
        if not self.local_map or not self.plan_store:
            raise RuntimeError("No hay un mapa activo.")
        snapshot = self.local_map.snapshot()
        native = snapshot.get("native_grid")
        if not isinstance(native, dict):
            raise RuntimeError(
                "Este mapa todavía no tiene una planta Xiaomi final. "
                "Terminá un mapeo completo antes de usar limpieza dirigida."
            )
        map_id = str(self.local_map.active_map_id or "")
        plan = self.plan_store.snapshot()
        if str(plan.get("active_map_id") or "") != map_id:
            raise RuntimeError(
                "La geometría y el plan de limpieza pertenecen a mapas "
                "distintos. Volvé a seleccionar el mapa antes de limpiar."
            )
        refreshed_origin = self._v109_prepare_plan_origin()
        plan = self.plan_store.snapshot()
        origin = plan.get("device_origin")
        origin_valid = False
        if isinstance(origin, dict):
            try:
                ox = float(origin.get("x"))
                oy = float(origin.get("y"))
                origin_valid = (
                    math.isfinite(ox)
                    and math.isfinite(oy)
                    and ox < 250.0
                    and oy < 250.0
                )
            except Exception:
                origin_valid = False
        if not refreshed_origin and not origin_valid:
            raise RuntimeError(
                "No pude calibrar la base física para este mapa. "
                "Dejá el E10 acoplado unos segundos y volvé a intentar."
            )
        return map_id, snapshot, dict(native), plan

    def _v88_prepare_live_grid(self, snapshot):
        if bool(self._v114_target_clean_active):
            self._v114_live_grid_updates_blocked += 1
            return None
        return super()._v88_prepare_live_grid(snapshot)

    def _v114_restore_grid_if_needed(self, original_grid, original_fp):
        try:
            current = self.local_map.snapshot().get("native_grid")
            current_fp = self._v114_grid_fingerprint(current)
        except Exception:
            current_fp = None
        self._v114_map_fingerprint_after = current_fp

        if (
            original_fp is not None
            and current_fp is not None
            and current_fp != original_fp
        ):
            self.local_map.set_native_grid(original_grid)
            self._v114_map_restores += 1
            self._v114_map_fingerprint_after = original_fp
            try:
                self._render_maps()
            except Exception:
                pass

    # ==================================================== bloqueo de Mapear UI
    def _v114_cleaning_busy(self):
        if not bool(self._v114_target_clean_active):
            return False
        self._v114_mapping_ui_blocks += 1
        messagebox.showinfo(
            "Limpieza en curso",
            "Terminá la limpieza dirigida antes de mapear, cambiar o eliminar "
            "el mapa activo.",
            parent=self,
        )
        return True

    def start_new_mapping(self):
        if self._v114_cleaning_busy():
            return
        return super().start_new_mapping()

    def start_clean(self):
        if bool(self._v114_target_clean_active):
            messagebox.showinfo(
                "Limpieza en curso",
                "Terminá la limpieza de habitación/zona antes de iniciar otra "
                "limpieza.",
                parent=self,
            )
            return
        return super().start_clean()

    def _switch_map(self, map_id, window=None):
        if self._v114_cleaning_busy():
            return
        return super()._switch_map(map_id, window)

    def _create_map(self, rebuild):
        if self._v114_cleaning_busy():
            return
        return super()._create_map(rebuild)

    def _delete_map(self, item, rebuild):
        if self._v114_cleaning_busy():
            return
        return super()._delete_map(item, rebuild)

    # =================================================== preparar geometría
    def _v114_constrain_target(self, target, kind, label):
        if bool(getattr(self, "mapping_active", False)):
            raise RuntimeError(
                "No se puede iniciar una limpieza dirigida mientras hay un "
                "mapeo activo."
            )
        map_id, snapshot, native, plan = self._v114_active_map_context()
        constrained = constrain_rect_to_native_grid(
            target,
            native,
            no_go=plan.get("no_go") or [],
            max_rectangles=self.V114_MAX_SAFE_RECTS,
        )

        self._v114_target_clean_kind = str(kind)
        self._v114_target_clean_label = str(label)
        self._v114_target_clean_map_id = map_id
        self._v114_target_requested = dict(constrained["requested"])
        self._v114_target_rects = [
            dict(item) for item in constrained["rectangles"]
        ]
        self._v114_target_raw_rects = [
            local_rect_to_device(item, plan)
            for item in self._v114_target_rects
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
        return map_id, snapshot, native, plan, constrained

    # =================================================== ejecución dirigida
    def _v114_run_safe_rectangles(
        self,
        target,
        kind,
        label,
        mode,
        suction,
        water,
    ):
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

        try:
            (
                map_id,
                _snapshot,
                native,
                plan,
                constrained,
            ) = self._v114_constrain_target(target, kind, label)
        except Exception as exc:
            self._v114_target_errors += 1
            self._v114_last_target_error = (
                str(exc).strip() or type(exc).__name__
            )
            messagebox.showerror(
                "Limpieza dirigida",
                self._v114_last_target_error,
                parent=self,
            )
            return

        if float(constrained["coverage_ratio"]) < 0.999:
            self._set_banner(
                f"{label} · ajustada al mapa Xiaomi: "
                f"{float(constrained['coverage_ratio']):.0%} de la selección "
                "es superficie limpiable."
            )

        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v114_map_fingerprint_before = original_fp
        self._v114_map_fingerprint_after = original_fp
        self._v114_last_target_error = "—"
        self._v114_target_clean_active = True
        self._zone_job_running = True
        vacuum = self.vacuum
        rects = [dict(item) for item in constrained["rectangles"]]

        try:
            suction = max(1, min(4, int(suction or 1)))
        except Exception:
            suction = 1
        try:
            water = max(0, min(3, int(water or 0)))
        except Exception:
            water = 0

        def worker():
            guard_started = False
            try:
                if str(self.local_map.active_map_id or "") != map_id:
                    raise RuntimeError(
                        "El mapa activo cambió antes de iniciar la limpieza."
                    )

                vacuum.begin_targeted_clean()
                guard_started = True

                # Los bloqueos deben estar sincronizados antes de enviar la
                # primera zona. Si falla la sincronización, no limpiamos.
                sync_virtual_walls(vacuum, plan)

                passes = (
                    ["vacuum", "mop"]
                    if str(mode) == "vacuum_then_mop"
                    else [str(mode)]
                )
                total = len(passes) * len(rects)
                current = 0

                for clean_mode in passes:
                    for rect in rects:
                        current += 1
                        if str(self.local_map.active_map_id or "") != map_id:
                            raise RuntimeError(
                                "El mapa activo cambió durante la limpieza."
                            )
                        self._post_ui(
                            "plan_job_stage",
                            f"{label} · sector {current}/{total}",
                        )
                        start_zone_clean(
                            vacuum,
                            rect,
                            plan,
                            clean_mode,
                            suction,
                            water,
                        )
                        self._v114_target_commands += 1
                        wait_for_cleaning_cycle(vacuum)
                        self._v114_target_completed += 1
                        self._v114_restore_grid_if_needed(
                            original_grid,
                            original_fp,
                        )
                        time.sleep(0.8)

                self._post_ui(
                    "plan_job_done",
                    f"{label} · limpieza completada sin modificar el mapa.",
                )
            except Exception as exc:
                self._v114_target_errors += 1
                self._v114_last_target_error = (
                    str(exc).strip() or type(exc).__name__
                )
                self._v114_restore_grid_if_needed(
                    original_grid,
                    original_fp,
                )
                self._post_ui(
                    "plan_job_error",
                    self._v114_last_target_error,
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
                )
                self._v114_target_clean_active = False

        threading.Thread(
            target=worker,
            name="AspiradoraTargetCleanV114",
            daemon=True,
        ).start()

    def clean_local_room(self, room):
        label = f"Habitación “{room.get('name', 'Habitación')}”"
        try:
            suction = int(self.suction_var.get())
        except Exception:
            suction = 1
        return self._v114_run_safe_rectangles(
            room,
            "room",
            label,
            "vacuum",
            suction,
            0,
        )

    def _run_zones_now(self, zones, mode, suction, water):
        zones = [dict(item) for item in list(zones or []) if isinstance(item, dict)]
        if not zones:
            return
        if len(zones) == 1:
            zone = zones[0]
            return self._v114_run_safe_rectangles(
                zone,
                "zone",
                f"Zona “{zone.get('name', 'Zona')}”",
                mode,
                suction,
                water,
            )

        # Varias zonas: se validan todas contra el mismo mapa antes de mover el
        # robot. Luego se usa su envolvente sólo para delegar en la misma ruta
        # segura una por una; nunca se dispara un mapeo.
        def multi_worker():
            for zone in zones:
                while (
                    bool(self._v114_target_clean_active)
                    or bool(getattr(self, "_zone_job_running", False))
                ):
                    time.sleep(0.5)
                self._v114_run_safe_rectangles(
                    zone,
                    "zone",
                    f"Zona “{zone.get('name', 'Zona')}”",
                    mode,
                    suction,
                    water,
                )
                while (
                    bool(self._v114_target_clean_active)
                    or bool(getattr(self, "_zone_job_running", False))
                ):
                    time.sleep(0.8)

        threading.Thread(
            target=multi_worker,
            name="AspiradoraMultiZoneV114",
            daemon=True,
        ).start()

    def _run_schedule_now(self, schedule):
        if str((schedule or {}).get("target", "all")) != "zones":
            return super()._run_schedule_now(schedule)
        if not self.plan_store:
            return
        plan = self.plan_store.snapshot()
        zones_by_id = {
            str(zone.get("id")): dict(zone)
            for zone in list(plan.get("zones") or [])
            if isinstance(zone, dict)
        }
        zones = [
            zones_by_id[str(zone_id)]
            for zone_id in list((schedule or {}).get("zone_ids") or [])
            if str(zone_id) in zones_by_id
        ]
        if not zones:
            self._post_ui(
                "plan_job_error",
                "La programación no tiene zonas disponibles en el mapa activo.",
            )
            return
        return self._run_zones_now(
            zones,
            (schedule or {}).get("mode", "vacuum"),
            (schedule or {}).get("suction", 1),
            (schedule or {}).get("water", 1),
        )

    def clean_selected_point(self):
        if not self.selected_point or not self.vacuum:
            return
        try:
            map_id, _snapshot, native, plan = self._v114_active_map_context()
            point = {
                "x": float(self.selected_point[0]),
                "y": float(self.selected_point[1]),
            }
            if not native_grid_contains_point(
                point,
                native,
                no_go=plan.get("no_go") or [],
            ):
                raise RuntimeError(
                    "El punto elegido no pertenece a una celda limpiable del "
                    "mapa Xiaomi o está bloqueado."
                )
        except Exception as exc:
            messagebox.showerror(
                "Limpieza puntual",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return

        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v114_map_fingerprint_before = original_fp
        self._v114_target_clean_active = True
        self._v114_target_clean_kind = "point"
        self._v114_target_clean_label = "Punto seleccionado"
        self._v114_target_clean_map_id = map_id

        try:
            suction = int(self.suction_var.get())
        except Exception:
            suction = 1

        def worker():
            guard_started = False
            try:
                self.vacuum.begin_targeted_clean()
                guard_started = True
                sync_virtual_walls(self.vacuum, plan)
                start_point_clean(
                    self.vacuum,
                    point,
                    plan,
                    suction,
                )
                self._v114_target_commands += 1
                wait_for_cleaning_cycle(self.vacuum)
                self._v114_target_completed += 1
            except Exception as exc:
                self._v114_target_errors += 1
                self._v114_last_target_error = (
                    str(exc).strip() or type(exc).__name__
                )
            finally:
                if guard_started:
                    try:
                        self.vacuum.end_targeted_clean()
                    except Exception:
                        pass
                self._v114_restore_grid_if_needed(
                    original_grid,
                    original_fp,
                )
                self._v114_target_clean_active = False

        threading.Thread(
            target=worker,
            name="AspiradoraPointCleanV114",
            daemon=True,
        ).start()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        blocked_mapping = int(
            getattr(
                vacuum,
                "_targeted_clean_blocked_mapping_calls",
                0,
            )
            or 0
        ) if vacuum is not None else 0
        last_blocked = (
            getattr(vacuum, "_targeted_clean_last_blocked", None)
            if vacuum is not None
            else None
        )
        guard = bool(
            vacuum.targeted_clean_guard_active()
            if vacuum is not None
            and hasattr(vacuum, "targeted_clean_guard_active")
            else False
        )

        raw_preview = []
        for rect in self._v114_target_raw_rects[:8]:
            raw_preview.append(
                (
                    round(float(rect["x0"]), 3),
                    round(float(rect["y0"]), 3),
                    round(float(rect["x1"]), 3),
                    round(float(rect["y1"]), 3),
                )
            )

        lines = [
            "DIAGNÓSTICO V114 ACTIVO · mapa Xiaomi operativo",
            "================================================",
            (
                f"limpieza dirigida: activa={self._v114_target_clean_active} · "
                f"tipo={self._v114_target_clean_kind} · "
                f"objetivo={self._v114_target_clean_label}"
            ),
            (
                f"map_id={self._v114_target_clean_map_id or '—'} · "
                f"guard E10={guard} · llamadas de mapeo bloqueadas="
                f"{blocked_mapping} · última={last_blocked or '—'}"
            ),
            (
                f"selección local={self._v114_target_requested or '—'} · "
                f"área pedida={self._v114_target_requested_area:.3f} m² · "
                f"área limpiable={self._v114_target_allowed_area:.3f} m² · "
                f"cobertura={self._v114_target_coverage_ratio:.1%}"
            ),
            (
                f"grid: celdas seleccionadas={self._v114_target_selected_cells} · "
                f"celdas excluidas por bloqueos={self._v114_target_blocked_cells} · "
                f"subzonas seguras={len(self._v114_target_rects)}"
            ),
            f"raw enviado (preview): {raw_preview or '—'}",
            (
                f"comandos/terminados/errores="
                f"{self._v114_target_commands}/"
                f"{self._v114_target_completed}/"
                f"{self._v114_target_errors} · "
                f"último error={self._v114_last_target_error}"
            ),
            (
                f"mapa protegido: antes={self._v114_map_fingerprint_before or '—'} · "
                f"después={self._v114_map_fingerprint_after or '—'} · "
                f"restauraciones={self._v114_map_restores} · "
                f"updates live bloqueados={self._v114_live_grid_updates_blocked}"
            ),
            (
                f"UI: intentos de mapear/cambiar mapa bloqueados durante limpieza="
                f"{self._v114_mapping_ui_blocks}"
            ),
            "regla V114: Mapear y Limpiar son rutas independientes; una limpieza dirigida nunca puede ejecutar build-map/arm_new_map/start_mapping",
            "regla V114: habitación/zona se recorta contra el native_grid Xiaomi final y contra los bloqueos antes de convertir a raw",
            "regla V114: el mapa Xiaomi guardado queda congelado durante la limpieza y se restaura si cualquier evento intenta modificarlo",
            "regla V114: la geometría final sigue siendo exactamente la de V113/V111; V114 no modifica el decoder del mapa",
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

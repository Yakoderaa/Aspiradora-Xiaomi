import json
import math
import threading
import time
from pathlib import Path
from tkinter import messagebox

import app_v141
import app_v9
from robot_plans import (
    constrain_polygon_to_native_grid,
    constrain_rect_to_native_grid,
    local_rect_to_device,
    start_zone_clean,
    sync_virtual_walls,
    wait_for_cleaning_cycle,
)


class App(app_v141.App):
    """V142: aprendizaje adaptativo persistente por habitación."""

    AI_LEARNING_VERSION = 1
    AI_ROOM_SCORE_TARGET = 0.88
    AI_MAX_AUTO_RETRIES = 2
    AI_STRATEGIES = ("area_first", "row_sweep", "reverse", "fine_split")

    def __init__(self):
        self._v142_learning = {}
        self._v142_learning_path = None
        self._v142_learning_lock = threading.RLock()
        self._v142_ai_card = None
        self._v142_ai_status_label = None
        self._v142_last_room_result = {}
        self._v142_last_map_analysis = {}
        self._v142_decisions = []
        self._v142_room_sessions = 0
        self._v142_room_retries = 0
        self._v142_profiles_learned = 0
        super().__init__()
        self._v142_init_learning()
        self.after_idle(self._v142_install_ai_card)

    # =================================================== almacenamiento IA
    @staticmethod
    def _v142_learning_defaults():
        return {
            "version": App.AI_LEARNING_VERSION,
            "maps": {},
            "updated_at": None,
        }

    def _v142_init_learning(self):
        try:
            folder = Path(getattr(self.local_map, "folder"))
        except Exception:
            folder = Path.home() / ".aspiradora_xiaomi"
        folder.mkdir(parents=True, exist_ok=True)
        self._v142_learning_path = folder / "adaptive_learning.json"

        data = self._v142_learning_defaults()
        try:
            if self._v142_learning_path.exists():
                candidate = json.loads(
                    self._v142_learning_path.read_text(encoding="utf-8")
                )
                if isinstance(candidate, dict):
                    data.update(candidate)
        except Exception:
            data = self._v142_learning_defaults()

        if not isinstance(data.get("maps"), dict):
            data["maps"] = {}
        data["version"] = self.AI_LEARNING_VERSION
        self._v142_learning = data
        self._v142_profiles_learned = self._v142_count_profiles()

    def _v142_save_learning(self):
        with self._v142_learning_lock:
            if self._v142_learning_path is None:
                return False
            self._v142_learning["version"] = self.AI_LEARNING_VERSION
            self._v142_learning["updated_at"] = time.time()
            tmp = self._v142_learning_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    self._v142_learning,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            tmp.replace(self._v142_learning_path)
            self._v142_profiles_learned = self._v142_count_profiles()
        self._v142_update_ai_status()
        return True

    def _v142_count_profiles(self):
        total = 0
        for map_data in dict(self._v142_learning.get("maps") or {}).values():
            total += len(dict((map_data or {}).get("rooms") or {}))
        return total

    def _v142_room_key(self, room):
        map_id = str(getattr(self.local_map, "active_map_id", "") or "")
        room_id = str((room or {}).get("id") or "")
        if not room_id:
            room_id = str((room or {}).get("name") or "room")
        return map_id, room_id

    def _v142_room_profile(self, room, create=True):
        map_id, room_id = self._v142_room_key(room)
        maps = self._v142_learning.setdefault("maps", {})
        if not create and map_id not in maps:
            return {}
        map_data = maps.setdefault(map_id, {"rooms": {}})
        rooms = map_data.setdefault("rooms", {})
        if not create and room_id not in rooms:
            return {}
        profile = rooms.setdefault(
            room_id,
            {
                "name": str((room or {}).get("name") or "Habitación"),
                "runs": 0,
                "best_strategy": "area_first",
                "best_score": 0.0,
                "ema_score": 0.0,
                "problem_runs": 0,
                "strategies": {},
                "history": [],
            },
        )
        profile["name"] = str((room or {}).get("name") or profile.get("name") or "Habitación")
        return profile

    def _v142_update_strategy_stats(
        self,
        room,
        strategy,
        score,
        area_ratio,
        completion_ratio,
        elapsed,
        error=None,
    ):
        with self._v142_learning_lock:
            profile = self._v142_room_profile(room, create=True)
            profile["runs"] = int(profile.get("runs", 0) or 0) + 1
            prev_ema = float(profile.get("ema_score", 0.0) or 0.0)
            profile["ema_score"] = (
                float(score)
                if profile["runs"] <= 1
                else 0.70 * prev_ema + 0.30 * float(score)
            )

            stats = profile.setdefault("strategies", {}).setdefault(
                str(strategy),
                {
                    "runs": 0,
                    "mean_score": 0.0,
                    "best_score": 0.0,
                    "mean_area_ratio": 0.0,
                    "mean_completion": 0.0,
                    "mean_seconds": 0.0,
                    "errors": 0,
                },
            )
            n = int(stats.get("runs", 0) or 0)
            n2 = n + 1
            stats["runs"] = n2
            stats["mean_score"] = (
                (float(stats.get("mean_score", 0.0) or 0.0) * n + float(score))
                / n2
            )
            stats["best_score"] = max(
                float(stats.get("best_score", 0.0) or 0.0),
                float(score),
            )
            stats["mean_area_ratio"] = (
                (
                    float(stats.get("mean_area_ratio", 0.0) or 0.0) * n
                    + float(area_ratio)
                )
                / n2
            )
            stats["mean_completion"] = (
                (
                    float(stats.get("mean_completion", 0.0) or 0.0) * n
                    + float(completion_ratio)
                )
                / n2
            )
            stats["mean_seconds"] = (
                (
                    float(stats.get("mean_seconds", 0.0) or 0.0) * n
                    + float(elapsed)
                )
                / n2
            )
            if error:
                stats["errors"] = int(stats.get("errors", 0) or 0) + 1

            best_strategy = str(profile.get("best_strategy") or "area_first")
            best_score = float(profile.get("best_score", 0.0) or 0.0)
            if float(score) > best_score + 1e-6:
                profile["best_score"] = float(score)
                profile["best_strategy"] = str(strategy)
            elif best_strategy not in profile["strategies"]:
                profile["best_strategy"] = str(strategy)
                profile["best_score"] = max(best_score, float(score))

            if float(score) < self.AI_ROOM_SCORE_TARGET:
                profile["problem_runs"] = (
                    int(profile.get("problem_runs", 0) or 0) + 1
                )

            history = list(profile.get("history") or [])
            history.append({
                "t": time.time(),
                "strategy": str(strategy),
                "score": round(float(score), 4),
                "area_ratio": round(float(area_ratio), 4),
                "completion": round(float(completion_ratio), 4),
                "seconds": round(float(elapsed), 2),
                "error": str(error)[:300] if error else None,
            })
            profile["history"] = history[-40:]
            self._v142_save_learning()

    def _v142_strategy_rank(self, room):
        profile = self._v142_room_profile(room, create=True)
        stats = dict(profile.get("strategies") or {})

        untried = [
            strategy for strategy in self.AI_STRATEGIES
            if int((stats.get(strategy) or {}).get("runs", 0) or 0) == 0
        ]
        preferred = str(profile.get("best_strategy") or "area_first")

        ranked = []
        if preferred in self.AI_STRATEGIES:
            ranked.append(preferred)

        tried = sorted(
            (
                (
                    float((stats.get(strategy) or {}).get("mean_score", 0.0) or 0.0),
                    strategy,
                )
                for strategy in self.AI_STRATEGIES
                if strategy not in ranked
                and int((stats.get(strategy) or {}).get("runs", 0) or 0) > 0
            ),
            reverse=True,
        )
        ranked.extend(strategy for _score, strategy in tried)

        for strategy in untried:
            if strategy not in ranked:
                ranked.append(strategy)

        for strategy in self.AI_STRATEGIES:
            if strategy not in ranked:
                ranked.append(strategy)
        return ranked

    # ===================================================== estrategias IA
    @staticmethod
    def _v142_rect_area(rect):
        return max(
            0.0,
            (float(rect["x1"]) - float(rect["x0"]))
            * (float(rect["y1"]) - float(rect["y0"])),
        )

    def _v142_fine_split_rects(self, rects):
        result = []
        for rect in list(rects or []):
            r = dict(rect)
            x0, x1 = sorted((float(r["x0"]), float(r["x1"])))
            y0, y1 = sorted((float(r["y0"]), float(r["y1"])))
            width = x1 - x0
            height = y1 - y0

            if len(result) >= 62:
                result.append(r)
                continue

            # Sólo subdividimos sectores suficientemente grandes. Nunca
            # expandimos la geometría: las dos mitades permanecen dentro del
            # rectángulo validado contra el native_grid.
            if max(width, height) < 0.85:
                result.append(r)
            elif width >= height:
                mid = (x0 + x1) * 0.5
                result.extend([
                    {"x0": x0, "y0": y0, "x1": mid, "y1": y1},
                    {"x0": mid, "y0": y0, "x1": x1, "y1": y1},
                ])
            else:
                mid = (y0 + y1) * 0.5
                result.extend([
                    {"x0": x0, "y0": y0, "x1": x1, "y1": mid},
                    {"x0": x0, "y0": mid, "x1": x1, "y1": y1},
                ])

            if len(result) >= 64:
                break
        return result[:64]

    def _v142_strategy_rects(self, rects, strategy):
        rects = [dict(item) for item in list(rects or [])]
        if strategy == "reverse":
            return list(reversed(rects))
        if strategy == "row_sweep":
            return sorted(
                rects,
                key=lambda r: (
                    round((float(r["y0"]) + float(r["y1"])) * 0.5, 3),
                    round((float(r["x0"]) + float(r["x1"])) * 0.5, 3),
                ),
            )
        if strategy == "fine_split":
            return self._v142_fine_split_rects(rects)
        return sorted(
            rects,
            key=lambda r: (
                -self._v142_rect_area(r),
                float(r["y0"]),
                float(r["x0"]),
            ),
        )

    @staticmethod
    def _v142_room_polygon(room):
        polygon = list((room or {}).get("polygon") or [])
        if len(polygon) >= 3:
            return polygon
        return [
            {"x": float(room["x0"]), "y": float(room["y0"])},
            {"x": float(room["x1"]), "y": float(room["y0"])},
            {"x": float(room["x1"]), "y": float(room["y1"])},
            {"x": float(room["x0"]), "y": float(room["y1"])},
        ]

    def _v142_constrain_room(self, room, native, plan):
        polygon = list((room or {}).get("polygon") or [])
        if len(polygon) >= 3:
            return constrain_polygon_to_native_grid(
                polygon,
                native,
                no_go=plan.get("no_go") or [],
                max_rectangles=48,
            )
        return constrain_rect_to_native_grid(
            room,
            native,
            no_go=plan.get("no_go") or [],
            max_rectangles=48,
        )

    # =================================================== evaluación calidad
    def _v142_score_pass(
        self,
        expected_area,
        geometry_ratio,
        completed,
        total,
        physical_area,
        elapsed,
        error=None,
    ):
        completion = (
            min(1.0, float(completed) / float(total))
            if total > 0 else 0.0
        )
        area_ratio = (
            min(1.0, max(0.0, float(physical_area) / float(expected_area)))
            if expected_area > 1e-6 and physical_area > 0.02
            else 0.0
        )
        physical_available = area_ratio > 0.0

        if physical_available:
            score = (
                0.68 * area_ratio
                + 0.27 * completion
                + 0.05 * min(1.0, max(0.0, float(geometry_ratio)))
            )
        else:
            # Sin 7/23 fiable no fingimos una cobertura física. Damos un
            # puntaje prudente basado en finalización + geometría válida.
            score = (
                0.72 * completion
                + 0.18 * min(1.0, max(0.0, float(geometry_ratio)))
            )
            score = min(score, 0.89)

        if error:
            score *= 0.55

        return {
            "score": max(0.0, min(1.0, float(score))),
            "area_ratio": area_ratio,
            "completion_ratio": completion,
            "physical_area_m2": float(physical_area),
            "expected_area_m2": float(expected_area),
            "geometry_ratio": float(geometry_ratio),
            "physical_area_available": bool(physical_available),
            "elapsed_seconds": float(elapsed),
            "error": error,
        }

    def _v142_record_decision(self, **row):
        item = {"t": round(time.monotonic(), 3)}
        item.update(row)
        self._v142_decisions = (list(self._v142_decisions) + [item])[-80:]
        try:
            self._v141_log("IA adaptativa", **row)
        except Exception:
            pass

    # ================================================ limpieza habitación IA
    def clean_local_room(self, room):
        if not self.vacuum:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá el mapeo antes de limpiar una habitación.",
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
        try:
            map_id, _snapshot, native, plan = self._v114_active_map_context()
            constrained = self._v142_constrain_room(room, native, plan)
        except Exception as exc:
            messagebox.showerror(
                "Limpieza inteligente",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return

        base_rects = [dict(item) for item in constrained["rectangles"]]
        if not base_rects:
            messagebox.showerror(
                "Limpieza inteligente",
                "La habitación no tiene superficie limpiable.",
                parent=self,
            )
            return

        try:
            suction = max(1, min(4, int(self.suction_var.get())))
        except Exception:
            suction = 1

        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v114_map_fingerprint_before = original_fp
        self._v114_map_fingerprint_after = original_fp
        self._v114_target_clean_active = True
        self._zone_job_running = True
        self._v114_target_clean_kind = "room-ai"
        self._v114_target_clean_label = label
        self._v114_target_clean_map_id = map_id
        self._v114_target_requested = dict(constrained["requested"])
        self._v114_target_rects = list(base_rects)
        self._v114_target_raw_rects = [
            local_rect_to_device(item, plan) for item in base_rects
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

        vacuum = self.vacuum
        self._v142_room_sessions += 1

        def worker():
            guard_started = False
            best_result = None
            tried = []
            try:
                vacuum.begin_targeted_clean()
                guard_started = True
                sync_virtual_walls(vacuum, plan)

                ranking = self._v142_strategy_rank(room)
                max_passes = 1 + int(self.AI_MAX_AUTO_RETRIES)

                for pass_index in range(max_passes):
                    if str(self.local_map.active_map_id or "") != map_id:
                        raise RuntimeError(
                            "El mapa activo cambió durante la limpieza inteligente."
                        )

                    strategy = next(
                        (
                            item for item in ranking
                            if item not in tried
                        ),
                        "area_first",
                    )
                    tried.append(strategy)
                    rects = self._v142_strategy_rects(
                        base_rects,
                        strategy,
                    )

                    if pass_index > 0:
                        self._v142_room_retries += 1
                        self._post_ui(
                            "plan_job_stage",
                            (
                                f"{label} · IA repite la habitación "
                                f"({pass_index + 1}/{max_passes}) con "
                                f"{strategy}."
                            ),
                        )

                    started = time.monotonic()
                    completed = 0
                    physical_area = 0.0
                    error = None

                    for index, rect in enumerate(rects, start=1):
                        if str(self.local_map.active_map_id or "") != map_id:
                            raise RuntimeError(
                                "El mapa activo cambió durante la limpieza."
                            )
                        self._post_ui(
                            "plan_job_stage",
                            (
                                f"{label} · IA {strategy} · "
                                f"sector {index}/{len(rects)}"
                            ),
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
                        wait_for_cleaning_cycle(vacuum)
                        completed += 1
                        self._v114_target_completed += 1
                        self._v130_room_clean_completed += 1

                        # 7/23 es el único indicador físico de área disponible
                        # en este B112. Se toma al cierre de cada subzona.
                        try:
                            status = vacuum.status()
                            area = float(
                                getattr(status, "cleaning_area", 0.0) or 0.0
                            )
                            if math.isfinite(area) and area > 0:
                                physical_area += area
                        except Exception:
                            pass

                        self._v114_restore_grid_if_needed(
                            original_grid,
                            original_fp,
                            map_id,
                        )
                        time.sleep(0.65)

                    elapsed = time.monotonic() - started
                    result = self._v142_score_pass(
                        float(constrained["allowed_area"]),
                        float(constrained["coverage_ratio"]),
                        completed,
                        len(rects),
                        physical_area,
                        elapsed,
                        error=error,
                    )
                    result["strategy"] = strategy
                    result["pass_index"] = pass_index
                    result["sectors"] = len(rects)

                    self._v142_update_strategy_stats(
                        room,
                        strategy,
                        result["score"],
                        result["area_ratio"],
                        result["completion_ratio"],
                        elapsed,
                        error=error,
                    )
                    self._v142_record_decision(
                        room=str(room.get("name") or "Habitación"),
                        strategy=strategy,
                        score=round(result["score"], 3),
                        area_ratio=round(result["area_ratio"], 3),
                        pass_index=pass_index,
                    )

                    if (
                        best_result is None
                        or result["score"] > best_result["score"]
                    ):
                        best_result = dict(result)

                    if result["score"] >= self.AI_ROOM_SCORE_TARGET:
                        break

                    # Si no existe telemetría física de área y todos los
                    # sectores terminaron, evitamos gastar tres pasadas sólo
                    # porque el firmware omitió 7/23.
                    if (
                        not result["physical_area_available"]
                        and result["completion_ratio"] >= 0.999
                        and pass_index >= 1
                    ):
                        break

                self._v142_last_room_result = {
                    "room": str(room.get("name") or "Habitación"),
                    "tried": list(tried),
                    "best": dict(best_result or {}),
                    "profile": dict(
                        self._v142_room_profile(room, create=True)
                    ),
                }

                best_score = float(
                    (best_result or {}).get("score", 0.0) or 0.0
                )
                if best_score >= self.AI_ROOM_SCORE_TARGET:
                    self._post_ui(
                        "plan_job_done",
                        (
                            f"{label} · IA terminó con calidad "
                            f"{best_score:.0%}. Aprendizaje guardado."
                        ),
                    )
                else:
                    self._post_ui(
                        "plan_job_done",
                        (
                            f"{label} · IA terminó con calidad "
                            f"{best_score:.0%}. Guardé el mejor patrón y "
                            "la habitación quedó marcada para seguir aprendiendo."
                        ),
                    )
            except Exception as exc:
                self._v114_target_errors += 1
                self._v130_room_clean_errors += 1
                self._v130_last_room_clean_error = (
                    str(exc).strip() or type(exc).__name__
                )
                self._v114_last_target_error = self._v130_last_room_clean_error
                self._v142_record_decision(
                    room=str(room.get("name") or "Habitación"),
                    event="error",
                    error=self._v130_last_room_clean_error,
                )
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
            name="AspiradoraAIRoomLearningV142",
            daemon=True,
        ).start()

    # ============================================= análisis mapa/paredes IA
    def _v142_analyze_native_grid(self):
        try:
            grid = self.local_map.snapshot().get("native_grid")
        except Exception:
            grid = None
        if not isinstance(grid, dict):
            return {}

        try:
            side = int(grid.get("side", 0) or 0)
            resolution = float(grid.get("resolution", 0.0) or 0.0)
            cells = [1 if int(v) else 0 for v in list(grid.get("cells") or [])]
        except Exception:
            return {}
        if side <= 0 or len(cells) != side * side:
            return {}

        floor = {
            (i % side, i // side)
            for i, value in enumerate(cells)
            if value
        }
        if not floor:
            return {}

        boundary_edges = 0
        for x, y in floor:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) not in floor:
                    boundary_edges += 1

        # Componentes de piso: útil para detectar islas/artefactos del decoder.
        unseen = set(floor)
        components = []
        while unseen:
            seed = unseen.pop()
            stack = [seed]
            count = 1
            while stack:
                x, y = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = (x + dx, y + dy)
                    if nxt in unseen:
                        unseen.remove(nxt)
                        stack.append(nxt)
                        count += 1
            components.append(count)
        components.sort(reverse=True)

        largest_ratio = (
            float(components[0]) / float(len(floor))
            if components else 0.0
        )
        confidence = (
            min(1.0, largest_ratio)
            * min(1.0, len(floor) / 120.0)
        )
        result = {
            "floor_cells": len(floor),
            "components": len(components),
            "largest_component_ratio": round(largest_ratio, 4),
            "boundary_edges": int(boundary_edges),
            "estimated_wall_m": round(boundary_edges * resolution, 2),
            "resolution": resolution,
            "confidence": round(confidence, 3),
        }
        self._v142_last_map_analysis = dict(result)
        return result

    # ============================================================= Ajustes IA
    def _v142_update_ai_status(self):
        label = getattr(self, "_v142_ai_status_label", None)
        if label is None:
            return
        try:
            label.configure(
                text=(
                    f"Activa · {self._v142_profiles_learned} habitaciones "
                    "con aprendizaje guardado · máximo 2 reintentos automáticos"
                )
            )
        except Exception:
            pass

    def _v142_install_ai_card(self):
        if self._v142_ai_card is not None:
            return True
        page = getattr(self, "_pages", {}).get("settings")
        if page is None:
            return False

        try:
            palette = self._v98_palette(
                str((self.settings or {}).get("theme") or "light")
            )
        except Exception:
            palette = {
                "card": "#ffffff",
                "text": "#17181a",
                "muted": "#7b8088",
                "border": "#e8eaed",
            }

        card = tk.Frame(
            page,
            bg=palette["card"],
            highlightthickness=1,
            highlightbackground=palette["border"],
        )
        card.pack(fill="x", padx=5, pady=5)
        self._v142_ai_card = card

        tk.Label(
            card,
            text="Navegación inteligente · aprendizaje adaptativo",
            bg=palette["card"],
            fg=palette["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 5))

        tk.Label(
            card,
            text=(
                "La app aprende por habitación qué orden y subdivisión de zonas "
                "consigue mejor cobertura. Si una pasada queda floja, prueba "
                "otra estrategia y conserva la que obtiene mejor resultado."
            ),
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=780,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self._v142_ai_status_label = tk.Label(
            card,
            text="",
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 8),
            justify="left",
        )
        self._v142_ai_status_label.pack(anchor="w", padx=20, pady=(0, 10))
        self._v142_update_ai_status()

        self._button(
            card,
            "Borrar aprendizaje de IA",
            self._v142_confirm_clear_learning,
            compact=True,
        ).pack(anchor="w", padx=20, pady=(0, 18))
        return True

    def _v142_confirm_clear_learning(self):
        if not messagebox.askyesno(
            "Borrar aprendizaje de IA",
            "¿Querés borrar lo que la app aprendió de todas las habitaciones?\n\n"
            "No borra mapas, Wi-Fi ni configuraciones de la aspiradora.",
            parent=self,
        ):
            return False
        with self._v142_learning_lock:
            self._v142_learning = self._v142_learning_defaults()
            self._v142_save_learning()
        self._v142_last_room_result = {}
        self._v142_decisions = []
        self._set_banner("Aprendizaje de IA borrado · perfiles reiniciados.")
        return True

    # ============================================================= eventos
    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind == "v107_final_grid_done":
            analysis = self._v142_analyze_native_grid()
            if analysis:
                self._v142_record_decision(
                    event="map-analysis",
                    wall_m=analysis.get("estimated_wall_m"),
                    components=analysis.get("components"),
                    confidence=analysis.get("confidence"),
                )
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        profile_preview = []
        try:
            map_id = str(getattr(self.local_map, "active_map_id", "") or "")
            rooms = (
                self._v142_learning.get("maps", {})
                .get(map_id, {})
                .get("rooms", {})
            )
            for room_id, profile in list(rooms.items())[:8]:
                profile_preview.append({
                    "room_id": room_id,
                    "name": profile.get("name"),
                    "runs": profile.get("runs"),
                    "best_strategy": profile.get("best_strategy"),
                    "best_score": round(
                        float(profile.get("best_score", 0.0) or 0.0),
                        3,
                    ),
                    "problem_runs": profile.get("problem_runs"),
                })
        except Exception:
            profile_preview = []

        lines = [
            "DIAGNÓSTICO V142 ACTIVO · aprendizaje adaptativo por habitación",
            "================================================================",
            (
                f"perfiles aprendidos={self._v142_profiles_learned} · "
                f"sesiones habitación={self._v142_room_sessions} · "
                f"reintentos automáticos={self._v142_room_retries}"
            ),
            f"último resultado habitación={self._v142_last_room_result or '—'}",
            f"perfiles mapa activo={profile_preview or '—'}",
            f"análisis mapa/paredes={self._v142_last_map_analysis or '—'}",
            f"decisiones recientes={self._v142_decisions[-12:] or '—'}",
            (
                "estrategias IA: area_first, row_sweep, reverse y fine_split; "
                "la mejor queda persistida por habitación"
            ),
            (
                f"objetivo calidad={self.AI_ROOM_SCORE_TARGET:.0%} · "
                f"máximo reintentos={self.AI_MAX_AUTO_RETRIES}"
            ),
            (
                "seguridad: todas las subzonas nacen del native_grid Xiaomi "
                "y respetan no-go; la IA nunca expande una habitación"
            ),
            (
                "aprendizaje: cobertura física usa 7/23 cuando está disponible; "
                "si falta, usa finalización + geometría con puntaje prudente"
            ),
            (
                "persistencia: adaptive_learning.json sobrevive cierre de app "
                "y reinicio de Windows"
            ),
            "backup previo a IA: rama GitHub backup-v140-pre-ia",
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

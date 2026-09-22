import math
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v141
import app_v9
from adaptive_navigation import AdaptiveNavigationMemory


class App(app_v141.App):
    """V142-IA: navegación adaptativa y aprendizaje persistente por habitación."""

    AI_ROOM_SCORE_TARGET = 88.0
    AI_MONITOR_INTERVAL = 1.4
    AI_MAPPING_CELL = 0.35

    def __init__(self):
        self._v142_ai = None
        self._v142_ai_card = None
        self._v142_ai_summary_label = None
        self._v142_room_context = None
        self._v142_room_token = 0
        self._v142_mapping_token = 0
        self._v142_mapping_diag = {}
        self._v142_room_diag = {}
        super().__init__()
        try:
            self._v142_ai = AdaptiveNavigationMemory(self.local_map.folder)
        except Exception:
            self._v142_ai = None
        self.after_idle(self._v142_install_ai_card)
        self.after(1200, self._v142_refresh_ai_summary)

    # ============================================================ UI IA
    def _v142_install_ai_card(self):
        page = getattr(self, "_pages", {}).get("settings")
        if page is None or self._v142_ai_card is not None:
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
            text="Navegación inteligente (IA)",
            bg=palette["card"],
            fg=palette["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 5))

        tk.Label(
            card,
            text=(
                "Aprende por habitación: compara cobertura, tiempo, fallos y "
                "repeticiones. Si una pasada queda por debajo del objetivo, "
                "puede repetirla automáticamente y guardar la estrategia que "
                "mejor resultado dio."
            ),
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=800,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self._v142_ai_summary_label = tk.Label(
            card,
            text="Memoria IA: cargando…",
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        self._v142_ai_summary_label.pack(anchor="w", padx=20, pady=(0, 10))

        self._button(
            card,
            "Borrar aprendizaje de IA",
            self._v142_confirm_reset_learning,
            compact=True,
        ).pack(anchor="w", padx=20, pady=(0, 18))
        return True

    def _v142_refresh_ai_summary(self):
        summary = (
            self._v142_ai.summary()
            if self._v142_ai is not None
            else {"learned_rooms": 0, "strong_rooms": 0, "mapping_sessions": 0}
        )
        label = getattr(self, "_v142_ai_summary_label", None)
        try:
            if label is not None and label.winfo_exists():
                label.configure(
                    text=(
                        "Memoria IA: "
                        f"{summary['learned_rooms']} habitaciones aprendidas · "
                        f"{summary['strong_rooms']} con patrón estable · "
                        f"{summary['mapping_sessions']} sesiones analizadas"
                    )
                )
        except Exception:
            pass
        return summary

    def _v142_confirm_reset_learning(self):
        if self._v142_ai is None:
            return False
        ok = messagebox.askyesno(
            "Borrar aprendizaje de IA",
            "¿Querés borrar únicamente lo que la IA aprendió de habitaciones "
            "y recorridos?\n\nNo se borran mapas, Wi-Fi ni configuraciones.",
            parent=self,
        )
        if not ok:
            return False
        self._v142_ai.reset_learning()
        self._v142_refresh_ai_summary()
        self._set_banner("Aprendizaje de IA borrado · mapas y Wi-Fi conservados.")
        return True

    # ================================================ métricas habitación
    @staticmethod
    def _v142_strategy_passes(strategy):
        return {
            "single": 1,
            "verified_double": 2,
            "verified_triple": 3,
        }.get(str(strategy), 1)

    def _v142_room_monitor(self, token, context):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return
        context["samples"] = 0
        context["max_area_raw"] = 0
        context["max_clean_time"] = 0
        context["faults"] = []
        context["saw_active"] = False
        deadline = time.monotonic() + 60 * 45

        while time.monotonic() < deadline:
            if token != self._v142_room_token:
                return
            try:
                status = vacuum.status()
                context["samples"] += 1
                context["max_area_raw"] = max(
                    int(context.get("max_area_raw", 0) or 0),
                    int(getattr(status, "cleaning_area_raw", 0) or 0),
                )
                context["max_clean_time"] = max(
                    int(context.get("max_clean_time", 0) or 0),
                    int(getattr(status, "cleaning_time", 0) or 0),
                )
                code = int(getattr(status, "status", -1) or -1)
                if code in (5, 6, 7):
                    context["saw_active"] = True
                fault = int(getattr(status, "fault", 0) or 0)
                if fault and fault not in context["faults"]:
                    context["faults"].append(fault)
            except Exception:
                context["monitor_errors"] = int(
                    context.get("monitor_errors", 0) or 0
                ) + 1

            if bool(context.get("finished")):
                return
            time.sleep(self.AI_MONITOR_INTERVAL)

    def _v142_score_room(self, context, completed):
        room = context["room"]
        area = (
            self._v142_ai.room_area(room)
            if self._v142_ai is not None
            else 1.0
        )
        cleaned_m2 = float(context.get("max_area_raw", 0) or 0) * 0.1
        if cleaned_m2 > 0.0 and area > 0.0:
            coverage = min(1.0, cleaned_m2 / max(0.1, area * 0.72))
            telemetry = True
        else:
            coverage = 0.70 if completed and context.get("saw_active") else 0.0
            telemetry = False

        faults = len(context.get("faults") or [])
        elapsed = max(0.1, time.monotonic() - float(context["started_at"]))
        completion_score = 30.0 if completed else 0.0
        coverage_score = 58.0 * coverage
        stability_score = 12.0 if faults == 0 else max(0.0, 12.0 - faults * 6.0)
        score = max(0.0, min(100.0, completion_score + coverage_score + stability_score))
        return {
            "score": round(score, 2),
            "completed": bool(completed),
            "coverage_proxy": round(coverage, 3),
            "coverage_telemetry": telemetry,
            "cleaned_m2": round(cleaned_m2, 3),
            "room_area_m2": round(area, 3),
            "elapsed_s": round(elapsed, 1),
            "faults": list(context.get("faults") or []),
            "samples": int(context.get("samples", 0) or 0),
            "pass_index": int(context.get("pass_index", 1) or 1),
        }

    def _v142_launch_room_pass(self, context):
        if context is not self._v142_room_context:
            return False
        context["started_at"] = time.monotonic()
        context["finished"] = False
        context["samples"] = 0
        context["max_area_raw"] = 0
        context["max_clean_time"] = 0
        context["faults"] = []
        context["saw_active"] = False
        context["monitor_errors"] = 0

        self._v142_room_token += 1
        token = self._v142_room_token
        threading.Thread(
            target=self._v142_room_monitor,
            args=(token, context),
            name="AspiradoraAIRoomMonitorV142",
            daemon=True,
        ).start()

        self._set_banner(
            "IA · "
            f"{context['name']} · pasada {context['pass_index']}/"
            f"{context['planned_passes']} · estrategia {context['strategy']}."
        )
        return super().clean_local_room(context["room"])

    def clean_local_room(self, room):
        # Las repeticiones IA llaman directamente a _v142_launch_room_pass,
        # así que un clic nuevo siempre crea una sesión independiente.
        if self._v142_ai is None:
            return super().clean_local_room(room)

        strategy = self._v142_ai.choose_room_strategy(room)
        context = {
            "room": dict(room or {}),
            "name": str((room or {}).get("name") or "Habitación"),
            "strategy": strategy,
            "planned_passes": self._v142_strategy_passes(strategy),
            "pass_index": 1,
            "scores": [],
            "started_at": time.monotonic(),
            "finished": False,
        }
        self._v142_room_context = context
        self._v142_room_diag = {
            "room": context["name"],
            "strategy": strategy,
            "status": "running",
        }
        return self._v142_launch_room_pass(context)

    def _v142_finish_room_pass(self, completed):
        context = self._v142_room_context
        if not isinstance(context, dict):
            return
        context["finished"] = True
        metrics = self._v142_score_room(context, completed)
        context["scores"].append(metrics["score"])

        profile = {}
        if self._v142_ai is not None:
            profile = self._v142_ai.record_room_attempt(
                context["room"],
                context["strategy"],
                metrics,
            )
        self._v142_room_diag = {
            "room": context["name"],
            "strategy": context["strategy"],
            "metrics": metrics,
            "profile": profile,
        }
        self._v142_refresh_ai_summary()

        retry = False
        if self._v142_ai is not None:
            retry = self._v142_ai.should_retry_room(
                context["room"],
                metrics["score"],
                completed,
                context["pass_index"],
            )
        retry = bool(
            retry
            and context["pass_index"] < context["planned_passes"]
            and int(profile.get("consecutive_worse", 0) or 0) < 2
        )

        if retry:
            context["pass_index"] += 1
            self._set_banner(
                "IA · cobertura mejorable en "
                f"{context['name']} ({metrics['score']:.0f}/100). "
                "Voy a repetir la habitación y comparar el resultado."
            )
            self.after(1800, lambda: self._v142_launch_room_pass(context))
            return

        best = float(profile.get("best_score", metrics["score"]) or metrics["score"])
        strategy = str(profile.get("recommended") or context["strategy"])
        self._set_banner(
            "IA · "
            f"{context['name']} finalizada · puntuación {metrics['score']:.0f}/100 · "
            f"mejor histórico {best:.0f}/100 · próxima estrategia: {strategy}."
        )
        self._v142_room_context = None

    # ============================================ IA sobre recorrido/mapa
    @staticmethod
    def _v142_xy_points(snapshot, phase=None):
        result = []
        for p in list((snapshot or {}).get("points") or []):
            if not isinstance(p, dict):
                continue
            try:
                if phase is not None and int(p.get("phase", 0) or 0) != int(phase):
                    continue
                result.append((float(p["x"]), float(p["y"])))
            except Exception:
                continue
        return result

    def _v142_classify_path(self, points):
        if len(points) < 8:
            return {"pattern": "insufficient", "confidence": 0.0}
        path = 0.0
        for a, b in zip(points, points[1:]):
            path += math.hypot(b[0] - a[0], b[1] - a[1])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        diag = math.hypot(span_x, span_y)
        cell = self.AI_MAPPING_CELL
        unique = {
            (int(round(x / cell)), int(round(y / cell)))
            for x, y in points
        }
        revisit = 1.0 - min(1.0, len(unique) / max(1.0, len(points)))

        if path >= 5.0 and diag <= 1.8 and revisit >= 0.45:
            pattern = "spiral_or_loop"
            confidence = min(1.0, 0.55 + revisit * 0.45)
        elif path >= 4.0 and len(unique) <= 5:
            pattern = "stuck"
            confidence = 0.92
        elif diag >= 3.0 and len(unique) >= 12:
            pattern = "expanding"
            confidence = min(1.0, 0.55 + diag / 12.0)
        else:
            pattern = "mixed"
            confidence = 0.55

        return {
            "pattern": pattern,
            "confidence": round(confidence, 3),
            "path_m": round(path, 2),
            "span_x": round(span_x, 2),
            "span_y": round(span_y, 2),
            "unique_cells": len(unique),
            "revisit_ratio": round(revisit, 3),
        }

    def _v142_mapping_monitor(self, token, serial):
        last_signature = None
        while token == self._v142_mapping_token:
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return
            if not bool(getattr(self, "mapping_active", False)):
                return
            phase = int(getattr(self, "mapping_phase", 0) or 0)
            if phase not in (1, 2):
                time.sleep(1.5)
                continue
            try:
                snapshot = self.local_map.snapshot()
                points = self._v142_xy_points(snapshot, phase=phase)
                metrics = self._v142_classify_path(points[-160:])
                metrics["phase"] = phase
                signature = (
                    metrics.get("pattern"),
                    metrics.get("unique_cells"),
                    len(points),
                )
                if signature != last_signature:
                    self._v142_mapping_diag = dict(metrics)
                    last_signature = signature
                # V142 aprende/clasifica; no toma el control de ruedas por una
                # inferencia débil. Sólo registra patrones de alta confianza.
                if (
                    self._v142_ai is not None
                    and float(metrics.get("confidence", 0.0) or 0.0) >= 0.85
                    and metrics.get("pattern") in ("spiral_or_loop", "stuck")
                ):
                    tagged = dict(metrics)
                    tagged["serial"] = serial
                    self._v142_ai.record_mapping_pattern(tagged)
            except Exception as exc:
                self._v142_mapping_diag = {
                    "error": str(exc).strip() or type(exc).__name__
                }
            time.sleep(2.0)

    def _v142_start_mapping_ai(self):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        self._v142_mapping_token += 1
        token = self._v142_mapping_token
        serial = int(getattr(self, "_v74_mapping_serial", -1))
        threading.Thread(
            target=self._v142_mapping_monitor,
            args=(token, serial),
            name="AspiradoraAIMappingMonitorV142",
            daemon=True,
        ).start()
        return True

    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started":
            result = super()._handle_ui_event(kind, payload)
            self._v142_start_mapping_ai()
            return result

        if kind == "plan_job_done":
            result = super()._handle_ui_event(kind, payload)
            if self._v142_room_context is not None:
                self._v142_finish_room_pass(True)
            return result

        if kind == "plan_job_error":
            result = super()._handle_ui_event(kind, payload)
            if self._v142_room_context is not None:
                self._v142_finish_room_pass(False)
            return result

        if kind == "v107_final_grid_done":
            result = super()._handle_ui_event(kind, payload)
            if self._v142_ai is not None:
                metrics = dict(self._v142_mapping_diag or {})
                metrics["final_grid_saved"] = bool(
                    getattr(self, "_v107_final_saved", False)
                )
                metrics["serial"] = int(
                    getattr(self, "_v74_mapping_serial", -1)
                )
                self._v142_ai.record_mapping_pattern(metrics)
                self._v142_refresh_ai_summary()
            return result

        return super()._handle_ui_event(kind, payload)

    # ======================================================= diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        summary = self._v142_refresh_ai_summary()
        lines = [
            "DIAGNÓSTICO V142-IA ACTIVO · aprendizaje adaptativo",
            "====================================================",
            f"memoria={summary}",
            f"habitación IA={self._v142_room_diag or '—'}",
            f"clasificador de recorrido={self._v142_mapping_diag or '—'}",
            "IA habitación: mide cobertura proxy/tiempo/fallos y repite hasta 3 pasadas si mejora",
            "IA persistente: conserva por habitación mejor puntuación y estrategia recomendada",
            "IA seguridad: dos empeoramientos consecutivos bloquean repeticiones automáticas",
            "IA mapa: clasifica expansión, bucle/espiral y atasco por trayectoria real disponible",
            "IA no inventa sensores: si Xiaomi no entrega pose/geometría suficiente, baja la confianza y no toma control por esa inferencia",
            "backup pre-IA: ramas backup-v140-pre-ia y backup-v141-pre-ia",
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

"""V159: interfaz de baja latencia sobre la navegación segura de V158."""
import queue
import threading
import time
from tkinter import messagebox

import app_v158
import app_v9
from route_learning_v157 import TrajectorySamplerV157
from targeted_v157 import TargetedRunnerV157
from whole_home_v157 import WholeHomeRunnerV157
from robot_plans import local_rect_to_device


class App(app_v158.App):
    """Mantiene V158, pero saca red/diagnóstico pesado del hilo Tk."""

    # V157 priorizó consumo mínimo y dejó hasta 250 ms de latencia artificial
    # en la cola UI, 5 s entre lecturas activas y 30 s en reposo. V159 vuelve
    # responsiva la app sin reactivar Cloud durante el recorrido.
    LOCAL_ACTIVE_POLL_MS = 1000
    LOCAL_IDLE_POLL_MS = 5000
    LOCAL_BUSY_RETRY_MS = 350
    RENDER_MIN_INTERVAL_SECONDS = 1.25
    UI_EVENT_BUDGET = 120

    DIAG_REBUILD_SECONDS = 1.5
    DIAG_WINDOW_TICK_MS = 180
    PAGE_RENDER_DEFER_MS = 80

    def __init__(self):
        self._v159_ready = False
        self._v159_diag_worker = False
        self._v159_diag_last_build = 0.0
        self._v159_diag_revision = 0
        self._v159_diag_displayed_revision = -1
        self._v159_diag_cache = (
            "V159-IA · DIAGNÓSTICO INSTANTÁNEO\n"
            "====================================\n"
            "La ventana ya está disponible. Preparando el snapshot completo en segundo plano…\n"
        )
        self._v159_page_render_job = None
        super().__init__()
        self._v159_ready = True
        # Precalienta el primer informe sin retrasar el arranque de la ventana.
        self.after(900, lambda: self._v159_request_diag_refresh(force=True))

    # ========================================================= cola UI rápida
    def _drain_ui_events(self):
        if getattr(self, "_closing", False):
            return

        processed = 0
        try:
            while processed < int(self.UI_EVENT_BUDGET):
                kind, payload = self._ui_events.get_nowait()
                self._handle_ui_event(kind, payload)
                processed += 1
                self._v96_ui_events_processed += 1
        except queue.Empty:
            pass
        except Exception:
            app_v9._save_crash_log(app_v9.traceback.format_exc())

        self._v96_ui_batches += 1
        try:
            pending = not self._ui_events.empty()
        except Exception:
            pending = False
        if pending:
            self._v96_ui_budget_hits += 1

        if not getattr(self, "_closing", False):
            # 8–25 ms mantiene reacción humana inmediata sin busy-loop.
            self.after(8 if pending else 25, self._drain_ui_events)

    # ================================================ navegación visual primero
    def show_page(self, page):
        # app_v5 programa un render a 50 ms al abrir Inicio/Mapa. Sustituimos
        # únicamente ese callback por uno diferido: primero se pinta la página,
        # después se redibuja el canvas pesado.
        sentinel = object()
        previous = self.__dict__.get("_render_maps", sentinel)
        self.__dict__["_render_maps"] = self._v159_page_render_request
        try:
            return super().show_page(page)
        finally:
            if previous is sentinel:
                self.__dict__.pop("_render_maps", None)
            else:
                self.__dict__["_render_maps"] = previous

    def _v159_page_render_request(self):
        old = self._v159_page_render_job
        if old is not None:
            try:
                self.after_cancel(old)
            except Exception:
                pass
        try:
            self._v159_page_render_job = self.after(
                self.PAGE_RENDER_DEFER_MS,
                self._v159_page_render_now,
            )
        except Exception:
            self._v159_page_render_job = None

    def _v159_page_render_now(self):
        self._v159_page_render_job = None
        if getattr(self, "_closing", False):
            return None
        # Ya restaurado el método heredado; conserva el coalescing V96/V157.
        return self._render_maps()

    # =========================================== diagnóstico cacheado/asíncrono
    def _v159_request_diag_refresh(self, force=False):
        if not self._v159_ready or getattr(self, "_closing", False):
            return False
        if self._v159_diag_worker:
            return False
        now = time.monotonic()
        if not force and now - self._v159_diag_last_build < self.DIAG_REBUILD_SECONDS:
            return False

        self._v159_diag_worker = True

        def worker():
            try:
                # Invocación explícita al constructor V158 para evitar que el
                # override cacheado de V159 se llame recursivamente.
                text = app_v158.App._diagnostic_text(self)
                error = None
            except Exception as exc:
                text = None
                error = str(exc).strip() or type(exc).__name__
            self._post_ui("v159_diag_ready", text, error, time.monotonic())

        threading.Thread(
            target=worker,
            name="V159DiagnosticSnapshot",
            daemon=True,
        ).start()
        return True

    def _diagnostic_text(self):
        # Esta función la llama la ventana cada pocos cientos de ms. Ahora es
        # O(1): devuelve memoria y solicita el recálculo pesado fuera de Tk.
        self._v159_request_diag_refresh()
        return self._v159_diag_cache

    def _refresh_map_diag_window(self):
        win = getattr(self, "_map_diag_window", None)
        box = getattr(self, "_map_diag_text", None)
        try:
            if not win or not win.winfo_exists() or not box or not box.winfo_exists():
                return
            if self._v159_diag_displayed_revision != self._v159_diag_revision:
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", self._v159_diag_cache)
                box.configure(state="disabled")
                self._v159_diag_displayed_revision = self._v159_diag_revision
            self._v159_request_diag_refresh()
            win.after(self.DIAG_WINDOW_TICK_MS, self._refresh_map_diag_window)
        except Exception:
            return

    # ====================================== limpieza global: clic no bloqueante
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

        vacuum = self.vacuum
        sampler = TrajectorySamplerV157(vacuum, sample_m=0.25)
        self._v157_whole_sampler = sampler
        self._v157_whole_active = True
        self._set_banner("Limpiar vivienda · solicitud recibida · preparando START 2/1…")

        def worker():
            try:
                core = self._fresh()
                if bool(core.diagnostic().get("active")):
                    raise RuntimeError("El robot ya está ocupado por otra acción.")

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
            except Exception as exc:
                diag = {
                    "purpose": "whole-home-v159-preflight",
                    "source": str(source),
                    "error": str(exc).strip() or type(exc).__name__,
                }
                learned = False
                learned_stats = sampler.stats()

            self._post_ui(
                "v157_whole_finished",
                dict(diag or {}),
                bool(learned),
                dict(learned_stats or {}),
            )

        threading.Thread(
            target=worker,
            name="V159WholeHome",
            daemon=True,
        ).start()
        return True

    # ==================================== habitación/zona: preflight fuera de Tk
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
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return False
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá el mapeo antes de limpiar un espacio.",
                parent=self,
            )
            return False
        if self._v157_whole_active or self._v157_target_active:
            self._set_banner("Ya hay una limpieza V157 en curso.")
            return False

        vacuum = self.vacuum
        requested_rects = [dict(item) for item in list(local_rects or [])]
        passes = ["vacuum", "mop"] if str(mode) == "vacuum_then_mop" else [str(mode)]

        self._v157_target_active = True
        self._v114_target_clean_active = True
        self._zone_job_running = True
        self._set_banner(f"{label} · solicitud recibida · preparando limpieza dirigida…")

        def worker():
            sampler = TrajectorySamplerV157(vacuum, sample_m=0.20)
            learned = False
            stats = sampler.stats()
            last_diag = {}
            try:
                plan = self._v157_plan_with_origin()
                raw_rects = [
                    local_rect_to_device(rect, plan)
                    for rect in requested_rects
                ]
                if not raw_rects:
                    raise RuntimeError("No hay superficie para limpiar.")

                core = self._fresh()
                if bool(core.diagnostic().get("active")):
                    raise RuntimeError("El robot ya está ocupado.")

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
            except Exception as exc:
                last_diag = {
                    "purpose": "targeted-v159-preflight",
                    "source": str(source),
                    "error": str(exc).strip() or type(exc).__name__,
                }

            self._post_ui(
                "v157_target_finished",
                str(label),
                dict(last_diag or {}),
                bool(learned),
                dict(stats or {}),
            )

        threading.Thread(
            target=worker,
            name="V159TargetClean",
            daemon=True,
        ).start()
        return True

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v159_diag_ready":
            text, error, built_at = payload
            self._v159_diag_worker = False
            self._v159_diag_last_build = float(built_at or time.monotonic())
            if text:
                self._v159_diag_cache = str(text)
            elif error:
                self._v159_diag_cache = (
                    "V159-IA · DIAGNÓSTICO INSTANTÁNEO\n"
                    "====================================\n"
                    "No se pudo regenerar el snapshot completo: " + str(error) + "\n"
                )
            self._v159_diag_revision += 1
            return None
        return super()._handle_ui_event(kind, payload)

    def destroy(self):
        job = getattr(self, "_v159_page_render_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._v159_page_render_job = None
        return super().destroy()

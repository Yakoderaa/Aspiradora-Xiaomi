"""V161: elimina picos periódicos de CPU sin perder aprendizaje ni respuesta UI."""
import queue
import threading
import time

import app_v159
import app_v160
import app_v9


class App(app_v160.App):
    """V160 con trabajo de fondo acotado y diagnóstico compacto."""

    # Los controles siguen siendo asíncronos/inmediatos. Estas cadencias sólo
    # afectan telemetría/render automático de fondo.
    LOCAL_ACTIVE_POLL_MS = 2000
    LOCAL_IDLE_POLL_MS = 15000
    LOCAL_BUSY_RETRY_MS = 800
    RENDER_MIN_INTERVAL_SECONDS = 2.5
    UI_EVENT_BUDGET = 100

    # El informe ya no recompone miles de puntos + todo el historial cada 1.5 s.
    DIAG_REBUILD_SECONDS = 15.0
    DIAG_WINDOW_TICK_MS = 500

    # Una sesión final necesita como máximo dos lecturas Cloud. La primera
    # geometría válida cierra inmediatamente la captura.
    FINAL_MAP_DELAYS_MS = (15000, 45000)

    def __init__(self):
        self._v161_diag_builds = 0
        self._v161_diag_last_ms = 0
        self._v161_capture_skipped_idle = 0
        self._v161_capture_stopped_success = 0
        self._v161_capture_failures_closed = 0
        super().__init__()

    # ======================================================= cola UI adaptativa
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
            # Cuando hay trabajo mantiene 8 ms; ociosa baja despertares a ~16 Hz.
            self.after(8 if pending else 60, self._drain_ui_events)

    # ====================================== captura final sólo tras sesión física
    def _v158_begin_capture(self, reason):
        # V158 podía descargar/decodificar Cloud simplemente porque la app
        # arrancaba y veía status=4. V161 exige una sesión que V160 haya marcado
        # explícitamente como finalizada.
        if not getattr(self, "_v160_pending_session", None):
            self._v161_capture_skipped_idle += 1
            return False
        return super()._v158_begin_capture(reason)

    def _v158_next_capture(self, capture, attempt):
        diag = getattr(self, "_v158_map_diag", {}) or {}

        # Una geometría válida ya fue pasada por el aprendizaje V160 y guardada.
        # Repetir el mismo pipeline de decoder no aporta votos (misma session_key)
        # y sólo consume CPU.
        if bool(diag.get("saved")):
            diag["state"] = "mapa Xiaomi guardado · captura cerrada tras primer éxito"
            diag["cpu_policy"] = "V161: no redescodificar una captura válida"
            self._v161_capture_stopped_success += 1
            self._v158_epoch += 1
            self._v158_capture = None
            self._v160_pending_session = None
            self._v160_pending_reason = None
            return None

        # Conserva un único retry si Xiaomi todavía no tenía listo el blob.
        if int(attempt) + 1 < len(self.FINAL_MAP_DELAYS_MS):
            return super()._v158_next_capture(capture, attempt)

        result = super()._v158_next_capture(capture, attempt)
        self._v161_capture_failures_closed += 1
        self._v158_epoch += 1
        self._v158_capture = None
        self._v160_pending_session = None
        self._v160_pending_reason = None
        return result

    # =============================================== diagnóstico compacto V161
    @staticmethod
    def _v161_small_capture(diag):
        diag = dict(diag or {})
        decoder = dict(diag.get("decoder") or {})
        v100 = dict(decoder.get("last_v100_diagnostics") or {})
        learning = dict(decoder.get("v160_learning") or {})
        return {
            "state": diag.get("state"),
            "reason": diag.get("reason"),
            "attempts": diag.get("attempts"),
            "successes": diag.get("successes"),
            "saved": diag.get("saved"),
            "cells": diag.get("cells"),
            "side": diag.get("side"),
            "resolution": diag.get("resolution"),
            "blob_sha12": diag.get("blob_sha12"),
            "last_error": (list(diag.get("errors") or [])[-1:] or [None])[0],
            "decode_ms": v100.get("duration_ms"),
            "decode_changed": v100.get("changed"),
            "learning": {
                "sessions": learning.get("sessions"),
                "support_needed": learning.get("support_needed"),
                "current_cells": learning.get("current_cells"),
                "learned_cells": learning.get("learned_cells"),
                "added_from_history": learning.get("added_from_history"),
            },
        }

    def _v161_compact_diagnostic_text(self):
        started = time.monotonic()
        state = dict(getattr(self, "_v158_state", {}) or {})
        path = list(state.get("path") or [])

        telemetry = {
            "status": state.get("status"),
            "fault": state.get("fault"),
            "mode": state.get("mode"),
            "sweep_type": state.get("sweep_type"),
            "robot": state.get("robot"),
            "base": state.get("base"),
            "path_points": len(path),
            "path_source": state.get("path_source"),
            "position_source": state.get("position_source"),
            "position_stale": state.get("position_stale"),
        }

        maps = []
        active_map_id = None
        try:
            active_map_id = self.local_map.active_map_id
            maps = self.local_map.list_maps()
        except Exception:
            pass

        geometry = {}
        try:
            current = next(
                (item for item in maps if str(item.get("id")) == str(active_map_id)),
                {},
            )
            geometry = {
                "map_id": active_map_id,
                "name": current.get("name"),
                "points": current.get("points"),
                "walls": current.get("walls"),
                "rooms": current.get("rooms"),
                "native_grid": current.get("native_grid"),
            }
        except Exception:
            geometry = {"map_id": active_map_id}

        route = {
            "whole_active": bool(getattr(self, "_v157_whole_active", False)),
            "target_active": bool(getattr(self, "_v157_target_active", False)),
            "mapping_active": bool(getattr(self, "mapping_active", False)),
            "guide_stats": dict((getattr(self, "_v156_guide", {}) or {}).get("stats") or {}),
            "last_progress": dict(getattr(self, "_v156_last_progress", {}) or {}),
        }

        persistent = {}
        try:
            learner = getattr(self, "_v160_map_learning", None)
            if learner is not None:
                persistent = learner.diagnostic(active_map_id)
        except Exception as exc:
            persistent = {"error": str(exc)}

        performance = {
            "LAN_polls": int(getattr(self, "_v95_local_polls_started", 0) or 0),
            "UI_events": int(getattr(self, "_v96_ui_events_processed", 0) or 0),
            "UI_batches": int(getattr(self, "_v96_ui_batches", 0) or 0),
            "renders": int(getattr(self, "_v96_render_executed", 0) or 0),
            "render_coalesced": int(getattr(self, "_v96_render_coalesced", 0) or 0),
            "poll_active_ms": int(self.LOCAL_ACTIVE_POLL_MS),
            "poll_idle_ms": int(self.LOCAL_IDLE_POLL_MS),
            "render_min_s": float(self.RENDER_MIN_INTERVAL_SECONDS),
            "diag_rebuild_s": float(self.DIAG_REBUILD_SECONDS),
            "capture_skipped_idle": int(self._v161_capture_skipped_idle),
            "capture_stopped_success": int(self._v161_capture_stopped_success),
        }

        sections = [
            "V161-IA · DIAGNÓSTICO COMPACTO / CPU SAFE\n" + "=" * 60,
            "Navegación: sin cambios respecto de V160/V159.",
            "TELEMETRÍA RESUMIDA\n" + repr(telemetry),
            "MAPA LOCAL\n" + repr(geometry),
            "CAPTURA FINAL XIAOMI\n" + repr(self._v161_small_capture(getattr(self, "_v158_map_diag", {}))),
            "APRENDIZAJE DE MAPA V160\n" + repr({
                "runtime": dict(getattr(self, "_v160_learning_diag", {}) or {}),
                "persistent": persistent,
            }),
            "RUTA / ESTADO\n" + repr(route),
            "RENDIMIENTO V161\n" + repr(performance),
            "Regla CPU V161: sin historial completo, sin trayectoria completa y sin audit log en refrescos periódicos.",
        ]
        text = "\n\n".join(sections) + "\n"
        try:
            text = self._v109_redact_ips(text)[0]
        except Exception:
            pass
        self._v161_diag_builds += 1
        self._v161_diag_last_ms = int((time.monotonic() - started) * 1000)
        return text

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
                text = self._v161_compact_diagnostic_text()
                error = None
            except Exception as exc:
                text = None
                error = str(exc).strip() or type(exc).__name__
            self._post_ui("v159_diag_ready", text, error, time.monotonic())

        threading.Thread(
            target=worker,
            name="V161CompactDiagnostic",
            daemon=True,
        ).start()
        return True

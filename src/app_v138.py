import math
import threading
import time
from tkinter import messagebox

import app_v128
import app_v137
import app_v9


class App(app_v137.App):
    """V138: reset del estado de limpieza + EDGE fábrica + whole-home V123."""

    RESET_SETTLE_SECONDS = 0.45
    EDGE_CONFIRM_TIMEOUT = 6.0
    ROOM_ESCAPE_SPAN_METERS = 3.40
    ROOM_ESCAPE_DISTANCE_METERS = 4.40
    PHASE1_FACTORY_RETRIES = 1

    def __init__(self):
        self._v138_reset_history = []
        self._v138_last_reset = {}
        self._v138_factory_edge_diag = {}
        self._v138_phase2_diag = {}
        self._v138_phase1_retry_count = 0
        self._v138_phase1_retry_running = False
        self._v138_phase1_progress = self._v138_new_progress(1)
        self._v138_phase2_progress = self._v138_new_progress(2)
        self._v138_remote_exits = 0
        self._v138_remote_exit_errors = 0
        self._v138_safe_reasserts_enabled = True
        super().__init__()

    @staticmethod
    def _v138_new_progress(phase):
        return {
            "phase": int(phase),
            "samples": 0,
            "min_x": None,
            "max_x": None,
            "min_y": None,
            "max_y": None,
            "span_x": 0.0,
            "span_y": 0.0,
            "max_distance": 0.0,
            "escaped_room": False,
            "last_status": None,
            "errors": 0,
        }

    @staticmethod
    def _v138_int(value):
        try:
            return int(value)
        except Exception:
            return None

    def _v138_read_clean_state(self, vacuum):
        try:
            values = vacuum._get_many([
                ("status", 2, 1),
                ("mode", 2, 4),
                ("sweep_type", 2, 8),
                ("repeat", 7, 1),
            ])
        except Exception as exc:
            return {
                "status": None,
                "mode": None,
                "sweep_type": None,
                "repeat": None,
                "error": str(exc).strip() or type(exc).__name__,
            }
        return {
            "status": self._v138_int(values.get("status")),
            "mode": self._v138_int(values.get("mode")),
            "sweep_type": self._v138_int(values.get("sweep_type")),
            "repeat": self._v138_int(values.get("repeat")),
            "error": None,
        }

    def _v138_wait_for_dock(self, vacuum, timeout=45.0):
        deadline = time.monotonic() + max(2.0, float(timeout))
        last_status = None
        dock_sent = False
        while time.monotonic() < deadline:
            try:
                last_status = self._v138_int(vacuum._value(2, 1))
            except Exception:
                last_status = None
            if last_status == 4:
                return True, last_status
            if not dock_sent and last_status in (0, 1, 2, 3):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception:
                    pass
            time.sleep(0.50)
        return False, last_status

    def _v138_reset_cleaning_state(self, vacuum, reason, ensure_dock=True):
        """Normaliza navegación/limpieza sin resetear cuenta, Wi-Fi ni mapas."""
        diag = {
            "reason": str(reason),
            "before": self._v138_read_clean_state(vacuum),
            "commands": [],
            "after": None,
            "dock_confirmed": False,
            "success": False,
            "error": None,
        }

        def attempt(name, func):
            row = {"name": name, "ok": False, "response": None, "error": None}
            try:
                response = func()
                row["ok"] = True
                row["response"] = repr(response)[:260]
            except Exception as exc:
                row["error"] = str(exc).strip() or type(exc).__name__
            diag["commands"].append(row)
            return row["ok"]

        try:
            try:
                vacuum.end_global_clean_guard("V138 clean-state reset")
            except Exception:
                pass
            try:
                while vacuum.targeted_clean_guard_active():
                    vacuum.end_targeted_clean()
            except Exception:
                pass

            # 7/26 clean-room-oper: 2=Stop. Detenemos objetivos que pueden
            # quedar latentes antes de volver a un estado global neutro.
            attempt(
                "room-edge-stop",
                lambda: vacuum.device.call_action_by(7, 3, ["", 2, 2]),
            )
            attempt(
                "room-global-stop",
                lambda: vacuum.device.call_action_by(7, 3, ["", 0, 2]),
            )
            attempt(
                "room-spiral-stop",
                lambda: vacuum.device.call_action_by(7, 3, ["", 4, 2]),
            )
            attempt("vacuum-stop", vacuum.stop)

            # 7/16: 5=Stop manual; 10=Exit. Salimos explícitamente del modo
            # remoto para que una maniobra de reacople no contamine EDGE.
            if attempt("remote-exit", lambda: vacuum.manual(10)):
                self._v138_remote_exits += 1
            else:
                self._v138_remote_exit_errors += 1

            # Parámetros de limpieza localizada son write-only; el vaciado es
            # best-effort. El STOP anterior ya cancela cualquier tarea activa.
            attempt(
                "clear-point",
                lambda: vacuum.device.set_property_by(9, 5, ""),
            )
            attempt(
                "clear-zone",
                lambda: vacuum.device.set_property_by(9, 2, ""),
            )

            attempt(
                "repeat-off",
                lambda: vacuum.device.set_property_by(7, 1, 0),
            )
            attempt(
                "twice-clean-off",
                lambda: vacuum.device.set_property_by(8, 10, 0),
            )
            attempt("water-off", lambda: vacuum.set_water(0))
            attempt("suction-eco", lambda: vacuum.set_suction(1))
            attempt("mode-sweep", lambda: vacuum.set_mode(0))
            attempt("sweep-neutral-global", lambda: vacuum.set_sweep_type(0))
            time.sleep(self.RESET_SETTLE_SECONDS)

            if ensure_dock:
                dock_ok, status = self._v138_wait_for_dock(vacuum)
                diag["dock_confirmed"] = bool(dock_ok)
                diag["dock_status"] = status
                if not dock_ok:
                    raise RuntimeError(
                        "V138 no confirmó status=4 en la base tras normalizar el estado"
                    )
            else:
                diag["dock_confirmed"] = None

            after = self._v138_read_clean_state(vacuum)
            diag["after"] = after
            if after.get("mode") not in (None, 0):
                raise RuntimeError(
                    f"reset dejó mode={after.get('mode')!r}; se esperaba 0"
                )
            if after.get("sweep_type") not in (None, 0):
                raise RuntimeError(
                    f"reset dejó sweep_type={after.get('sweep_type')!r}; se esperaba 0"
                )
            if after.get("repeat") not in (None, 0):
                raise RuntimeError(
                    f"reset dejó repeat={after.get('repeat')!r}; se esperaba 0"
                )

            diag["success"] = True
            return diag
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            raise
        finally:
            self._v138_last_reset = dict(diag)
            self._v138_reset_history = (
                list(self._v138_reset_history) + [dict(diag)]
            )[-8:]

    def _v138_start_factory_edge(self, vacuum, label):
        """Arranque equivalente a Limpiar bordes: sweep_type=2 + 2/3."""
        diag = {
            "route": "factory EDGE: sweep_type=2 -> 2/3 start-only-sweep",
            "label": str(label),
            "status_before": None,
            "sweep_before": None,
            "sweep_after_set": None,
            "response": None,
            "status_after": None,
            "sweep_after": None,
            "success": False,
            "error": None,
        }
        try:
            before = vacuum._get_many([
                ("status", 2, 1),
                ("sweep_type", 2, 8),
            ])
            diag["status_before"] = self._v138_int(before.get("status"))
            diag["sweep_before"] = self._v138_int(before.get("sweep_type"))

            vacuum.set_sweep_type(2)
            time.sleep(0.25)
            try:
                diag["sweep_after_set"] = self._v138_int(vacuum._value(2, 8))
            except Exception:
                pass
            if diag["sweep_after_set"] not in (None, 2):
                raise RuntimeError(
                    "El E10 no confirmó sweep_type=2 antes de iniciar EDGE"
                )

            response = vacuum._send_motor_start(
                "mapping_edge_v138/factory",
                2,
                3,
                allow_when_guarded=True,
            )
            diag["response"] = repr(response)[:500]

            deadline = time.monotonic() + self.EDGE_CONFIRM_TIMEOUT
            while time.monotonic() < deadline:
                state = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status = self._v138_int(state.get("status"))
                sweep = self._v138_int(state.get("sweep_type"))
                diag["status_after"] = status
                diag["sweep_after"] = sweep
                if status in (5, 6, 7) and sweep == 2:
                    diag["success"] = True
                    return diag
                time.sleep(0.30)

            raise RuntimeError(
                "EDGE no confirmó status activo + sweep_type=2 "
                f"(status={diag.get('status_after')!r}, "
                f"sweep={diag.get('sweep_after')!r})"
            )
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            raise
        finally:
            self._v138_factory_edge_diag = dict(diag)

    def _v138_progress_worker(self, vacuum, serial, phase):
        progress = self._v138_new_progress(phase)
        attr = (
            "_v138_phase1_progress"
            if int(phase) == 1
            else "_v138_phase2_progress"
        )
        setattr(self, attr, progress)

        while serial == int(getattr(self, "_v74_mapping_serial", -1)):
            if vacuum is not getattr(self, "vacuum", None):
                return
            if not bool(getattr(self, "mapping_active", False)):
                return
            if int(getattr(self, "mapping_phase", 0) or 0) != int(phase):
                return
            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("robot", 10, 24),
                    ("base", 10, 22),
                ])
                progress["last_status"] = self._v138_int(values.get("status"))
                robot = vacuum.parse_position(values.get("robot"))
                base = vacuum.parse_position(values.get("base"))
                if robot is not None and base is not None:
                    x = (float(robot["x"]) - float(base["x"])) * 0.10
                    y = (float(robot["y"]) - float(base["y"])) * 0.10
                    progress["samples"] += 1
                    progress["min_x"] = (
                        x if progress["min_x"] is None
                        else min(progress["min_x"], x)
                    )
                    progress["max_x"] = (
                        x if progress["max_x"] is None
                        else max(progress["max_x"], x)
                    )
                    progress["min_y"] = (
                        y if progress["min_y"] is None
                        else min(progress["min_y"], y)
                    )
                    progress["max_y"] = (
                        y if progress["max_y"] is None
                        else max(progress["max_y"], y)
                    )
                    progress["span_x"] = float(
                        progress["max_x"] - progress["min_x"]
                    )
                    progress["span_y"] = float(
                        progress["max_y"] - progress["min_y"]
                    )
                    progress["max_distance"] = max(
                        float(progress["max_distance"] or 0.0),
                        math.hypot(x, y),
                    )
                    progress["escaped_room"] = bool(
                        max(progress["span_x"], progress["span_y"])
                        >= self.ROOM_ESCAPE_SPAN_METERS
                        or progress["max_distance"]
                        >= self.ROOM_ESCAPE_DISTANCE_METERS
                    )
            except Exception:
                progress["errors"] += 1
            setattr(self, attr, dict(progress))
            time.sleep(0.75)

    def _v138_start_progress_watch(self, vacuum, serial, phase):
        if vacuum is None:
            return
        threading.Thread(
            target=self._v138_progress_worker,
            args=(vacuum, serial, int(phase)),
            name=f"AspiradoraV138ProgressP{int(phase)}",
            daemon=True,
        ).start()

    def _v138_run_with_remote_exit(self, vacuum, worker, *args):
        """Completa cada manual Stop heredado (5) con Exit remoto (10)."""
        original_manual = getattr(vacuum, "manual")

        def manual_with_exit(direction):
            result = original_manual(direction)
            if int(direction) == 5:
                try:
                    original_manual(10)
                    self._v138_remote_exits += 1
                except Exception:
                    self._v138_remote_exit_errors += 1
            return result

        vacuum.manual = manual_with_exit
        try:
            return worker(vacuum, *args)
        finally:
            vacuum.manual = original_manual

    def _v73_dock_guard_worker(self, vacuum, serial, reason):
        parent = super()._v73_dock_guard_worker
        return self._v138_run_with_remote_exit(
            vacuum,
            lambda v, ser, why: parent(v, ser, why),
            serial,
            reason,
        )

    def _v67_watch_base_worker(self, vacuum, serial):
        parent = super()._v67_watch_base_worker
        return self._v138_run_with_remote_exit(
            vacuum,
            lambda v, ser: parent(v, ser),
            serial,
        )

    def start_new_mapping(self):
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
                "Primero detené el mapeo actual.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda",
            "V138 normaliza primero el estado de limpieza del E10 sin borrar "
            "Wi-Fi ni mapas.\n\n"
            "Paso 1 usa el aspirado por bordes estándar del robot.\n"
            "Paso 2 usa whole-home V123.\n\n"
            "El Paso 2 sólo se habilita si el perímetro demuestra que salió "
            "de la habitación inicial.",
            parent=self,
        )
        if not ok:
            return

        self._v138_phase1_retry_count = 0
        self._v138_phase1_retry_running = False
        self._v138_phase1_progress = self._v138_new_progress(1)
        self._v138_phase2_progress = self._v138_new_progress(2)
        self._v137_phase1_diag = {}
        self._v137_phase2_diag = {}
        self._v137_phase1_starts = 1
        self._v137_phase2_starts = 0
        self._v137_manual_cancel = False
        self._v136_manual_abort = False
        self._v137_flow = "edge-reset"

        self._v121_stage = "edge"
        self._v121_phase2_requested = False
        self._v121_phase2_started = False
        self._v121_phase2_departed = False
        self._v121_phase2_attempts = 0
        self._v121_phase2_errors = 0
        self._v121_edge_dock_suppressed_closes = 0
        self._v121_final_reads_suppressed = 0
        self._v121_invalid_final_grids_rejected = 0
        self._v121_phase2_diag = {}

        self._v74_reset_session()
        self._v73_session_phase = 1
        try:
            self._v131_capture_prestart_pose()
        except Exception:
            pass

        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(
                before,
                "10/24 antes de reset+EDGE V138",
            )

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 1
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner(
            "Mapeando · Paso 1/2: normalizando estado de limpieza…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            diag = {
                "route": "V138 reset -> build-map -> EDGE fábrica",
                "reset": None,
                "build": None,
                "edge": None,
                "success": False,
                "error": None,
            }
            try:
                reset_diag = self._v138_reset_cleaning_state(
                    vacuum,
                    "pre-mapeo Paso 1",
                    ensure_dock=True,
                )
                diag["reset"] = dict(reset_diag or {})

                build_diag = vacuum.arm_new_map(1)
                diag["build"] = dict(build_diag or {})
                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                edge_diag = self._v138_start_factory_edge(
                    vacuum,
                    "inicio Paso 1",
                )
                diag["edge"] = dict(edge_diag or {})
                diag["success"] = bool(edge_diag.get("success"))
                self._v137_phase1_diag = dict(diag)
                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": dict(edge_diag or {}),
                    "reset": dict(reset_diag or {}),
                }
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v137_phase1_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    diag["error"],
                )

        threading.Thread(
            target=worker,
            name="AspiradoraFactoryEdgeV138",
            daemon=True,
        ).start()

    def _v138_retry_factory_edge(self, vacuum, serial):
        if self._v138_phase1_retry_running:
            return False
        if self._v138_phase1_retry_count >= self.PHASE1_FACTORY_RETRIES:
            return False

        self._v138_phase1_retry_running = True
        self._v138_phase1_retry_count += 1
        attempt = self._v138_phase1_retry_count
        self._v138_phase1_progress = self._v138_new_progress(1)
        self._v137_flow = "edge-retry"
        self._set_banner(
            f"Paso 1 no salió de la habitación · reinicio limpio "
            f"{attempt}/{self.PHASE1_FACTORY_RETRIES}."
        )

        def worker():
            try:
                self._v138_reset_cleaning_state(
                    vacuum,
                    f"retry EDGE {attempt}",
                    ensure_dock=True,
                )
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
                self._v138_start_factory_edge(vacuum, f"retry {attempt}")
                self._v138_phase1_retry_running = False
                self._v137_flow = "edge"
                self._v138_start_progress_watch(vacuum, serial, 1)
                self._set_banner(
                    "Mapeando · Paso 1/2: bordes reintentados desde estado limpio."
                )
            except Exception as exc:
                self._v138_phase1_retry_running = False
                self._post_ui(
                    "v138_phase1_retry_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraFactoryEdgeRetryV138",
            daemon=True,
        ).start()
        return True

    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if vacuum is not getattr(self, "vacuum", None):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if self._v121_phase2_requested or self._v138_phase1_retry_running:
            return False

        if self._v137_manual_cancel or self._v136_manual_abort:
            return super()._v121_request_phase2(
                vacuum,
                serial,
                source,
                sweep_type,
            )

        progress = dict(self._v138_phase1_progress or {})
        if not bool(progress.get("escaped_room")):
            if self._v138_retry_factory_edge(vacuum, serial):
                return False

            self._v137_flow = "edge-failed-room"
            self._v74_watch_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "Paso 1 finalizó sin salir de la habitación inicial · "
                "proceso finalizó. Paso 2 no fue iniciado."
            )
            return False

        self._v121_phase2_requested = True
        self._v121_stage = "transition"
        self._v137_flow = "transition-reset"
        self.mapping_phase = 2
        self.mapping_transitioning = True
        self.mapping_step1_complete = True
        self._v73_session_phase = 2
        self._set_banner(
            "Perímetro completo · normalizando estado antes del Paso 2…"
        )

        self._v121_phase2_attempts += 1
        self._v137_phase2_starts += 1
        requested_at = time.monotonic()

        def worker():
            diag = {
                "source": str(source),
                "edge_sweep_type": sweep_type,
                "requested_at": round(requested_at, 3),
                "arm_new_map_called": False,
                "reset": None,
                "method": "reset V138 -> whole-home V123",
                "success": False,
                "error": None,
            }
            try:
                reset_diag = self._v138_reset_cleaning_state(
                    vacuum,
                    "transición Paso 1 -> Paso 2",
                    ensure_dock=True,
                )
                diag["reset"] = dict(reset_diag or {})
                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                response = vacuum.start_mapping_whole_home(
                    confirm_timeout=self.PHASE2_CONFIRM_TIMEOUT
                )
                native = dict(
                    getattr(
                        vacuum,
                        "_last_mapping_whole_home_diag",
                        {},
                    )
                    or {}
                )
                diag.update({
                    "status_before": native.get("status_before"),
                    "status_after": native.get("status_after"),
                    "sweep_type_after": native.get("sweep_type_after"),
                    "response": native.get(
                        "response",
                        repr(response)[:500],
                    ),
                    "success": bool(native.get("success")),
                    "native": native,
                })
                if not diag["success"]:
                    raise RuntimeError(
                        native.get("error")
                        or "whole-home V123 no confirmó movimiento físico"
                    )

                self._v138_phase2_diag = dict(diag)
                self._v137_phase2_diag = dict(diag)
                self._post_ui("v121_phase2_started", serial, diag)
            except Exception as exc:
                self._v121_phase2_errors += 1
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v138_phase2_diag = dict(diag)
                self._v137_phase2_diag = dict(diag)
                self._post_ui("v121_phase2_error", serial, diag)

        threading.Thread(
            target=worker,
            name="AspiradoraWholeHomeResetV138",
            daemon=True,
        ).start()
        return True

    def _v127_try_phase2_recovery(self, reason):
        # Recupera V128: sólo reafirma whole-home 7/3; no usa control remoto.
        if not self._v138_safe_reasserts_enabled:
            return False
        return app_v128.App._v127_try_phase2_recovery(self, reason)

    def _handle_ui_event(self, kind, payload):
        if kind == "v138_phase1_retry_error":
            serial, message = payload
            if int(serial) != int(getattr(self, "_v74_mapping_serial", -1)):
                return None
            self._v137_flow = "edge-retry-error"
            self._v74_watch_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "Paso 1 no pudo reiniciarse · proceso finalizó con error."
            )
            messagebox.showerror("Mapeo", str(message), parent=self)
            return None

        result = super()._handle_ui_event(kind, payload)

        if kind == "v74_mapping_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._v137_flow = "edge"
            self._v121_stage = "edge"
            self.mapping_phase = 1
            self._v73_session_phase = 1
            self._v138_phase1_progress = self._v138_new_progress(1)
            self._v138_start_progress_watch(
                getattr(self, "vacuum", None),
                int(getattr(self, "_v74_mapping_serial", -1)),
                1,
            )
            self._set_banner(
                "Mapeando · Paso 1/2: aspirado por bordes de fábrica activo."
            )
            return result

        if kind == "v121_phase2_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._v137_flow = "global"
            self._v73_session_phase = 2
            self._v138_phase2_progress = self._v138_new_progress(2)
            self._v138_start_progress_watch(
                getattr(self, "vacuum", None),
                int(getattr(self, "_v74_mapping_serial", -1)),
                2,
            )
            self._set_banner(
                "Mapeando · Paso 2/2: toda la vivienda desde estado limpio."
            )
            return result

        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V138 ACTIVO · reset frío + EDGE fábrica",
            "====================================================",
            (
                f"flujo={self._v137_flow} · remote exits OK="
                f"{self._v138_remote_exits} · "
                f"errores={self._v138_remote_exit_errors}"
            ),
            f"último reset={self._v138_last_reset or '—'}",
            f"historial reset={self._v138_reset_history or '—'}",
            f"EDGE fábrica={self._v138_factory_edge_diag or '—'}",
            f"progreso Paso1={self._v138_phase1_progress or '—'}",
            (
                f"reintentos Paso1={self._v138_phase1_retry_count}/"
                f"{self.PHASE1_FACTORY_RETRIES}"
            ),
            f"Paso2={self._v138_phase2_diag or '—'}",
            f"progreso Paso2={self._v138_phase2_progress or '—'}",
            (
                "reset V138: room STOP -> vacuum STOP -> remote Exit -> "
                "targets vacíos -> repeat=0 -> twice-clean=0 -> mode=0 -> sweep=0"
            ),
            (
                "ruta Paso1 V138: build-map único -> sweep_type=2 -> "
                "2/3 start-only-sweep (EDGE fábrica)"
            ),
            (
                "gate Paso1 V138: no habilita Paso2 hasta superar habitación "
                "inicial; un retry limpio máximo"
            ),
            (
                "ruta Paso2 V138: reset sin nuevo build-map -> whole-home V123 "
                "7/3 -> 2/3 sólo si sigue dock"
            ),
            (
                "antiatasco Paso2 V138: V128 seguro, sólo reafirma 7/3; "
                "sin STOP/manual/remote"
            ),
            (
                "regla V138: cada manual Stop (5) de reacople se completa "
                "con Exit remoto (10)"
            ),
            "regla V138: no ejecuta factory reset completo ni borra Wi-Fi",
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

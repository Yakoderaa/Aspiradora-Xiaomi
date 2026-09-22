import ast
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v137
import app_v140
import app_v9


class App(app_v140.App):
    """V141: EDGE Vacuum 2/1, sin reset automático, diagnóstico realmente borrable."""

    EDGE_CONFIRM_TIMEOUT = 7.0
    EDGE_SETTLE_SECONDS = 1.20

    def __init__(self):
        self._v141_edge_diag = {}
        self._v141_diag_capture = False
        self._v141_diag_events = []
        self._v141_diag_session = 0
        self._v141_diag_started_at = 0.0
        self._v141_edge_watch_serial = 0
        super().__init__()

    # ======================================== reset profundo: parser correcto
    @staticmethod
    def _v140_parse_order_ids(order_data):
        """Extrae únicamente order-id (primer campo) de cada reserva B112."""
        if order_data is None:
            return []

        rows = order_data
        if isinstance(rows, str):
            text = rows.strip()
            if not text:
                return []
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, (list, tuple)):
                    rows = parsed
                else:
                    rows = [text]
            except Exception:
                rows = [text]
        elif not isinstance(rows, (list, tuple)):
            rows = [rows]

        found = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                if not row:
                    continue
                first = row[0]
            else:
                first = str(row).strip().split(",", 1)[0].strip()
            try:
                order_id = int(first)
            except Exception:
                continue
            if 0 <= order_id <= 100 and order_id not in found:
                found.append(order_id)
        return found

    # ================================================ diagnóstico por sesión
    def _v141_log(self, event, **data):
        if not self._v141_diag_capture:
            return
        age = max(0.0, time.monotonic() - self._v141_diag_started_at)
        detail = " · ".join(
            f"{key}={value!r}" for key, value in data.items()
            if value is not None
        )
        line = f"+{age:7.2f}s · {event}"
        if detail:
            line += " · " + detail
        self._v141_diag_events.append(line)
        self._v141_diag_events = self._v141_diag_events[-350:]

    def _v141_diag_text(self):
        age = max(
            0.0,
            time.monotonic() - float(self._v141_diag_started_at or 0.0),
        )
        lines = [
            "DIAGNÓSTICO V141 · SESIÓN NUEVA",
            "================================",
            f"sesión={self._v141_diag_session} · edad={age:.1f}s",
            "El historial anterior fue borrado de esta captura.",
            "",
        ]
        if self._v141_diag_events:
            lines.extend(self._v141_diag_events)
        else:
            lines.append("Sin actividad nueva desde Borrar diagnóstico.")

        lines.extend([
            "",
            "ESTADO V141",
            "-----------",
            f"EDGE último={self._v141_edge_diag or '—'}",
            f"fase1={getattr(self, '_v137_phase1_diag', {}) or '—'}",
            f"fase2={getattr(self, '_v137_phase2_diag', {}) or '—'}",
            (
                "ruta Paso1: arm_new_map(1) -> preparar ECO -> "
                "sweep_type=2 -> 2/1 start-sweep"
            ),
            "prohibido Paso1: 7/3 set-room-clean y 2/3 start-only-sweep",
            "reset automático al iniciar mapa: NO",
            "",
        ])
        return "\n".join(lines)

    def _diagnostic_text(self):
        if self._v141_diag_capture:
            return self._v141_diag_text()

        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V141 ACTIVO · EDGE Vacuum 2/1",
            "==========================================",
            f"EDGE último={self._v141_edge_diag or '—'}",
            "Paso1: sin reset automático; reset profundo sólo desde Ajustes",
            "Paso1: arm_new_map(1) -> ECO -> sweep_type=2 -> 2/1 start-sweep",
            "Paso1: 7/3 y 2/3 prohibidos",
            "Borrar diagnóstico: vacía la captura y crea una sesión independiente",
            "",
            "",
        ]
        return "\n".join(lines) + inherited

    def _v139_confirm_clear_diagnostics(self):
        ok = messagebox.askyesno(
            "Borrar diagnóstico",
            "¿Querés borrar completamente el diagnóstico visible y empezar "
            "una captura nueva?\n\n"
            "No modifica el mapa ni envía comandos a la aspiradora.",
            parent=getattr(self, "_map_diag_window", self),
        )
        if not ok:
            return False

        self._v141_diag_session += 1
        self._v141_diag_started_at = time.monotonic()
        self._v141_diag_events = []
        self._v141_diag_capture = True

        # Desactivamos la lógica diferencial V139: V141 usa una captura
        # independiente y realmente vacía.
        self._v139_diag_baseline = {}
        self._v139_diag_clear_count = self._v141_diag_session
        self._v139_diag_cleared_at = self._v141_diag_started_at

        try:
            box = getattr(self, "_map_diag_text", None)
            if box is not None and box.winfo_exists():
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", self._v141_diag_text())
                box.configure(state="disabled")
        except Exception:
            pass

        self._set_banner(
            "Diagnóstico borrado · captura V141 vacía y lista para una prueba nueva."
        )
        return True

    # ============================================== EDGE nativo Vacuum 2/1
    def _v138_start_factory_edge(self, vacuum, label):
        """V141: usa el start-sweep nativo después de fijar sweep-type=2."""
        diag = {
            "route": "V141 EDGE Vacuum: sweep_type=2 -> 2/1 start-sweep",
            "label": str(label),
            "status_before": None,
            "sweep_before": None,
            "sweep_after_set": None,
            "response": None,
            "status_after": None,
            "sweep_after": None,
            "success": False,
            "movement_commands": 0,
            "room_clean_7_3_sent": False,
            "start_only_2_3_sent": False,
            "error": None,
        }
        self._v141_log("EDGE preparando", label=str(label))
        try:
            before = vacuum._get_many([
                ("status", 2, 1),
                ("sweep_type", 2, 8),
            ])
            diag["status_before"] = self._v138_int(before.get("status"))
            diag["sweep_before"] = self._v138_int(before.get("sweep_type"))

            # Preparación histórica V64, pero el movimiento lo inicia 2/1.
            vacuum._prepare_mapping_vacuum()
            try:
                vacuum.device.set_property_by(7, 1, 0)
            except Exception:
                pass
            vacuum.set_sweep_type(2)
            time.sleep(self.EDGE_SETTLE_SECONDS)

            try:
                diag["sweep_after_set"] = self._v138_int(
                    vacuum._value(2, 8)
                )
            except Exception:
                pass
            if diag["sweep_after_set"] not in (None, 2):
                raise RuntimeError(
                    "El E10 no confirmó sweep_type=2 antes de START EDGE"
                )

            self._v141_log(
                "sweep_type EDGE confirmado",
                status=diag["status_before"],
                sweep_type=diag["sweep_after_set"],
            )

            response = vacuum._send_motor_start(
                "mapping_edge_v141/vacuum-start-sweep",
                2,
                1,
                allow_when_guarded=True,
            )
            diag["movement_commands"] = 1
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
                if status in (5, 6, 7):
                    diag["success"] = True
                    self._v141_edge_diag = dict(diag)
                    self._v139_edge_diag = dict(diag)
                    self._v138_factory_edge_diag = dict(diag)
                    self._v141_log(
                        "EDGE iniciado",
                        command="2/1",
                        status=status,
                        sweep_type=sweep,
                    )
                    return diag
                time.sleep(0.30)

            raise RuntimeError(
                "2/1 EDGE no confirmó movimiento físico "
                f"(status={diag.get('status_after')!r}, "
                f"sweep={diag.get('sweep_after')!r})"
            )
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._v141_log("EDGE error", error=diag["error"])
            raise
        finally:
            self._v141_edge_diag = dict(diag)
            self._v139_edge_diag = dict(diag)
            self._v138_factory_edge_diag = dict(diag)

    def _v141_watch_edge_state(self, vacuum, serial):
        self._v141_edge_watch_serial += 1
        token = self._v141_edge_watch_serial
        last = object()

        while token == self._v141_edge_watch_serial:
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return
            if vacuum is not getattr(self, "vacuum", None):
                return
            if not bool(getattr(self, "mapping_active", False)):
                return
            if int(getattr(self, "mapping_phase", 0) or 0) != 1:
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                    ("robot", 10, 24),
                    ("base", 10, 22),
                ])
                current = (
                    self._v138_int(values.get("status")),
                    self._v138_int(values.get("sweep_type")),
                    repr(values.get("robot")),
                    repr(values.get("base")),
                )
                if current != last:
                    self._v141_log(
                        "telemetría Paso1",
                        status=current[0],
                        sweep_type=current[1],
                        robot=current[2],
                        base=current[3],
                    )
                    last = current
            except Exception as exc:
                self._v141_log(
                    "telemetría Paso1 error",
                    error=str(exc).strip() or type(exc).__name__,
                )
            time.sleep(0.80)

    # =============================================== Mapear vivienda V141
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
            "V141 no ejecuta ningún restablecimiento automático antes de mapear.\n\n"
            "Si querés un reset profundo, hacelo antes desde "
            "Ajustes → Mantenimiento avanzado.\n\n"
            "Paso 1 usa EDGE nativo: sweep_type=2 + start-sweep 2/1. "
            "No usa 7/3 ni 2/3.",
            parent=self,
        )
        if not ok:
            return

        self._v141_log("Mapear vivienda confirmado")
        self._v141_edge_diag = {}
        self._v139_edge_diag = {}
        self._v138_factory_edge_diag = {}

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
        self._v137_flow = "edge-v141"

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
                "10/24 antes de EDGE Vacuum V141",
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
            "Mapeando · Paso 1/2: iniciando aspirado por bordes nativo…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            diag = {
                "route": "V141 sin reset -> arm_new_map(1) -> EDGE Vacuum 2/1",
                "reset": "NO",
                "build": None,
                "edge": None,
                "success": False,
                "error": None,
            }
            try:
                self._v141_log("arm_new_map iniciando", mode=1)
                build_diag = vacuum.arm_new_map(1)
                diag["build"] = dict(build_diag or {})
                self._v141_log(
                    "arm_new_map terminado",
                    success=bool((build_diag or {}).get("success")),
                    winner=(build_diag or {}).get("winner"),
                )

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                edge_diag = self._v138_start_factory_edge(
                    vacuum,
                    "inicio Paso 1 V141",
                )
                diag["edge"] = dict(edge_diag or {})
                diag["success"] = bool(edge_diag.get("success"))
                self._v137_phase1_diag = dict(diag)
                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": dict(edge_diag or {}),
                    "reset": "NO",
                }
                self._post_ui("v74_mapping_started", serial)

                threading.Thread(
                    target=self._v141_watch_edge_state,
                    args=(vacuum, serial),
                    name="AspiradoraEdgeTelemetryV141",
                    daemon=True,
                ).start()
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v137_phase1_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._v141_log("Paso1 error", error=diag["error"])
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    diag["error"],
                )

        threading.Thread(
            target=worker,
            name="AspiradoraNativeEdgeV141",
            daemon=True,
        ).start()

    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        # 10/24 está congelado en algunas sesiones B112. No usamos el gate
        # V138 de "salió de la habitación" porque produciría falsos fallos.
        self._v141_log(
            "Paso1 final detectado",
            source=str(source),
            sweep_type=sweep_type,
        )
        result = app_v137.App._v121_request_phase2(
            self,
            vacuum,
            serial,
            source,
            sweep_type,
        )
        self._v141_log("solicitud Paso2", accepted=bool(result))
        return result

    def dock(self):
        self._v141_log(
            "Volver a base solicitado",
            phase=int(getattr(self, "mapping_phase", 0) or 0),
        )
        return super().dock()

    def _handle_ui_event(self, kind, payload):
        if kind == "v140_reset_done":
            self._v141_log("reset profundo finalizado", success=True)
        elif kind == "v140_reset_error":
            diag = payload[0] if payload else {}
            self._v141_log(
                "reset profundo finalizado",
                success=False,
                error=(diag or {}).get("error"),
            )
        elif kind == "v121_phase2_started":
            self._v141_log("Paso2 iniciado")
        elif kind == "v121_phase2_error":
            self._v141_log("Paso2 error", payload=repr(payload)[:500])
        return super()._handle_ui_event(kind, payload)


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

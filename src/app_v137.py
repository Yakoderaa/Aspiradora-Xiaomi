import threading
import time
from tkinter import messagebox

import app_v136
import app_v9


class App(app_v136.App):
    """V137: comportamiento físico V123 restaurado sobre la app moderna."""

    def __init__(self):
        self._v137_phase1_diag = {}
        self._v137_phase2_diag = {}
        self._v137_phase1_starts = 0
        self._v137_phase2_starts = 0
        self._v137_manual_cancel = False
        self._v137_flow = "idle"
        super().__init__()

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
            "V137 restaura el comportamiento físico de V123, la etapa en la "
            "que el recorrido de la vivienda funcionaba y el problema pendiente "
            "era el mapa.\n\n"
            "Paso 1: perímetro/exploración V121.\n"
            "Paso 2: whole-home V123 por 7/3 y sólo usa 2/3 si el E10 queda "
            "todavía en la base.\n\n"
            "Se conservan la interfaz, pose, captura final y reacople actuales.",
            parent=self,
        )
        if not ok:
            return

        self._v137_phase1_diag = {}
        self._v137_phase2_diag = {}
        self._v137_phase1_starts = 0
        self._v137_phase2_starts = 0
        self._v137_manual_cancel = False
        self._v136_manual_abort = False
        self._v137_flow = "edge"

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

        # V123 partía de esta sesión V121. Conservamos los contadores/pose
        # actuales, pero no usamos el watcher EDGE V68 de V136.
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
                "10/24 antes de fase 1 V137/V123",
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
            "Mapeando · Paso 1/2: perímetro V123 de toda la vivienda…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}
        self._v137_phase1_starts += 1

        def worker():
            diag = {
                "route": "V123 exacto: arm_new_map(1) -> start_mapping_exploration()",
                "build": None,
                "exploration": None,
                "success": False,
                "error": None,
            }
            try:
                # Secuencia exacta usada por V121/V123.
                build_diag = vacuum.arm_new_map(1)
                diag["build"] = dict(build_diag or {})

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                response = vacuum.start_mapping_exploration(
                    confirm_timeout=5.0
                )
                exploration = dict(
                    getattr(
                        vacuum,
                        "_last_mapping_exploration_diag",
                        {},
                    )
                    or {}
                )
                diag["exploration"] = exploration
                diag["response"] = repr(response)[:500]
                diag["success"] = bool(
                    exploration.get("success", True)
                )

                self._v137_phase1_diag = dict(diag)
                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": exploration,
                }
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v137_phase1_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._v120_last_start_diag = {
                    "build": dict(
                        getattr(vacuum, "last_map_build_diag", {}) or {}
                    ),
                    "exploration": dict(
                        getattr(
                            vacuum,
                            "_last_mapping_exploration_diag",
                            {},
                        )
                        or {}
                    ),
                    "error": diag["error"],
                }
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    diag["error"],
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapPhase1V123Restored",
            daemon=True,
        ).start()

    def dock(self):
        # Volver a base durante Paso 1 significa cancelar la prueba; un dock
        # manual nunca puede convertirse accidentalmente en inicio de Paso 2.
        if (
            bool(getattr(self, "mapping_active", False))
            and str(getattr(self, "_v121_stage", "")) == "edge"
        ):
            self._v137_manual_cancel = True
            self._v136_manual_abort = True
            self._v137_flow = "manual_return"
            self._set_banner(
                "Paso 1 cancelado manualmente · volviendo a la base. "
                "Paso 2 cancelado."
            )
        return super().dock()

    def _v121_request_phase2(
        self,
        vacuum,
        serial,
        source,
        sweep_type=None,
    ):
        """V137: restauración literal de V122/V123 para Fase 2."""
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if vacuum is not getattr(self, "vacuum", None):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if self._v121_phase2_requested:
            return False

        if self._v137_manual_cancel or self._v136_manual_abort:
            self._v137_flow = "cancelled"
            self._v74_watch_active = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step1_complete = False
            self.mapping_step2_complete = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "Mapeo cancelado manualmente · proceso finalizó en la base."
            )
            return False

        self._v121_phase2_requested = True
        self._v121_stage = "transition"
        self._v137_flow = "transition"
        self.mapping_phase = 2
        self.mapping_transitioning = True
        self.mapping_step1_complete = True

        self._set_banner(
            "Perímetro completo · Paso 2/2: iniciando toda la vivienda "
            "con la ruta V123…"
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
                "method": "V123 whole-home 7/3 ['',0,1] + 2/3 sólo si sigue dock",
                "status_before": None,
                "status_after": None,
                "sweep_type_after": None,
                "response": None,
                "success": False,
                "error": None,
            }
            try:
                try:
                    before = vacuum._get_many([
                        ("status", 2, 1),
                        ("sweep_type", 2, 8),
                    ])
                    diag["status_before"] = before.get("status")
                except Exception as exc:
                    diag["before_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                # Ésta es la corrección V123 que sustituyó
                # start_mapping_interior(): whole-home 7/3, con 2/3 solamente
                # como trigger si el firmware acepta 7/3 pero sigue en dock.
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

                self._v137_phase2_diag = dict(diag)
                self._post_ui(
                    "v121_phase2_started",
                    serial,
                    diag,
                )
            except Exception as exc:
                self._v121_phase2_errors += 1
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v137_phase2_diag = dict(diag)
                self._post_ui(
                    "v121_phase2_error",
                    serial,
                    diag,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapWholeHomeV123Restored",
            daemon=True,
        ).start()
        return True

    def _handle_ui_event(self, kind, payload):
        # Dejamos que V121 maneje sus eventos y luego corregimos únicamente
        # textos/diagnóstico que V135/V136 podrían haber dejado heredados.
        result = super()._handle_ui_event(kind, payload)

        if kind == "v74_mapping_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._v137_flow = "edge"
            self._v121_stage = "edge"
            self.mapping_phase = 1
            self._set_banner(
                "Mapeando · Paso 1/2: perímetro V123 activo. "
                "Dejá que el E10 termine y vuelva a la base por sí solo."
            )
            return result

        if kind == "v121_phase2_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._v137_flow = "global"
            self._set_banner(
                "Mapeando · Paso 2/2: toda la vivienda con whole-home V123."
            )
            return result

        if kind == "v121_phase2_error":
            self._v137_flow = "phase2_error"
            return result

        if kind == "v107_final_grid_done":
            if bool(getattr(self, "_v107_final_saved", False)):
                self._v137_flow = "complete"
            return result

        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        native_whole = (
            dict(
                getattr(
                    vacuum,
                    "_last_mapping_whole_home_diag",
                    {},
                )
                or {}
            )
            if vacuum is not None
            else {}
        )
        lines = [
            "DIAGNÓSTICO V137 ACTIVO · movimiento físico V123 restaurado",
            "==============================================================",
            f"flujo actual={self._v137_flow}",
            (
                "inicios: Paso1="
                f"{self._v137_phase1_starts} · Paso2="
                f"{self._v137_phase2_starts}"
            ),
            f"Paso1 V123={self._v137_phase1_diag or '—'}",
            f"Paso2 V123 app={self._v137_phase2_diag or '—'}",
            f"Paso2 V123 E10={native_whole or '—'}",
            f"cancelación manual={self._v137_manual_cancel}",
            "ruta Paso1 V137: arm_new_map(1) -> start_mapping_exploration() de V121/V123",
            "ruta Paso2 V137: 7/3 ['',0,1] -> espera -> 2/3 sólo si sigue físicamente en status=4",
            "regla V137: NO usa start_mapping_interior() para Paso2",
            "regla V137: NO usa watcher EDGE V68; el dock natural del perímetro dispara la transición V121",
            "regla V137: no hay segundo build-map entre Paso1 y Paso2",
            "regla V137: Volver a base durante Paso1 cancela Paso2",
            "regla V137: UI, pose, mapa final, habitaciones y reacople siguen siendo los actuales",
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

import threading
import time
from tkinter import messagebox

import app_v134
import app_v9


class App(app_v134.App):
    """V135: EDGE físico V87 sin build-map previo; Paso 2 bloqueado al dock."""

    def __init__(self):
        self._v135_edge_diag = {}
        self._v135_edge_starts = 0
        self._v135_phase1_finished = False
        self._v135_phase2_blocked = 0
        self._v135_build_before_edge = False
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
            "V135 prueba el recorrido de bordes nativo que funcionaba antes.\n\n"
            "Paso 1: aspirar bordes de verdad, SIN armar build-map antes y "
            "SIN ningún segundo comando de inicio.\n\n"
            "Al volver a la base, la prueba se detendrá ahí y NO iniciará "
            "automáticamente el Paso 2. Así validamos el borde físico sin "
            "mezclarlo con otro recorrido.",
            parent=self,
        )
        if not ok:
            return

        self._v135_edge_diag = {}
        self._v135_edge_starts = 0
        self._v135_phase1_finished = False
        self._v135_phase2_blocked = 0
        self._v135_build_before_edge = False

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
        self._v131_capture_prestart_pose()

        before = self._v71_debug_raw_pose()
        if before is not None:
            # Conserva la corrección V130 que sustituye el 10/24 viejo por
            # charging_base 10/22 como origen físico.
            self._v71_set_origin(
                before,
                "10/24 antes de fase 1 perímetro V121",
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
            "Mapeando · Paso 1: preparando EDGE nativo sin build-map previo…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            diag = {
                "route": "V87 físico: mode=0 -> sweep_type=2 -> 2/3",
                "build_map_before_edge": False,
                "status_before": None,
                "sweep_type_before": None,
                "response": None,
                "status_after": None,
                "sweep_type_after": None,
                "success": False,
                "extra_start_sent": False,
                "fallback": None,
                "error": None,
            }
            try:
                # IMPORTANTE V135: no arm_new_map() antes del EDGE.
                self._v135_build_before_edge = False

                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                try:
                    before_state = vacuum._get_many([
                        ("status", 2, 1),
                        ("sweep_type", 2, 8),
                    ])
                    diag["status_before"] = self._v67_int(
                        before_state.get("status")
                    )
                    diag["sweep_type_before"] = self._v67_int(
                        before_state.get("sweep_type")
                    )
                except Exception as exc:
                    diag["before_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                # Replica el viejo start_edge(0): modo normal, EDGE=2 y un
                # único start-only-sweep 2/3. ECO/agua=0 no alteran la ruta.
                try:
                    vacuum.set_water(0)
                except Exception as exc:
                    diag["water_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )
                try:
                    vacuum.set_suction(1)
                except Exception as exc:
                    diag["suction_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                vacuum.set_mode(0)
                vacuum.set_sweep_type(2)

                self._v135_edge_starts += 1
                self._v131_edge_primary_starts += 1
                response = vacuum._send_motor_start(
                    "mapping_edge_v135/native-v87",
                    2,
                    3,
                    allow_when_guarded=True,
                )
                diag["response"] = repr(response)[:500]

                deadline = time.monotonic() + 5.0
                while True:
                    try:
                        state = vacuum._get_many([
                            ("status", 2, 1),
                            ("sweep_type", 2, 8),
                        ])
                        status = self._v67_int(state.get("status"))
                        sweep = self._v67_int(state.get("sweep_type"))
                        diag["status_after"] = status
                        diag["sweep_type_after"] = sweep
                        if status in (5, 6, 7):
                            diag["success"] = True
                            break
                    except Exception as exc:
                        diag["readback_error"] = (
                            str(exc).strip() or type(exc).__name__
                        )

                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.30)

                if not diag["success"]:
                    raise RuntimeError(
                        "V135: EDGE nativo no confirmó salida física "
                        f"(status={diag.get('status_after')!r}, "
                        f"sweep_type={diag.get('sweep_type_after')!r})."
                    )

                self._v135_edge_diag = dict(diag)
                self._v131_edge_diag = dict(diag)
                vacuum._last_mapping_exploration_diag = dict(diag)
                self._v120_last_start_diag = {
                    "build": "NO ejecutado antes de EDGE",
                    "exploration": dict(diag),
                }
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._v135_edge_diag = dict(diag)
                self._v131_edge_diag = dict(diag)
                vacuum._last_mapping_exploration_diag = dict(diag)
                self._v120_mapping_start_errors += 1
                self._v120_last_start_diag = {
                    "build": "NO ejecutado antes de EDGE",
                    "exploration": dict(diag),
                    "error": diag["error"],
                }
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    diag["error"],
                )

        threading.Thread(
            target=worker,
            name="AspiradoraEdgeNativeV135",
            daemon=True,
        ).start()

    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        """V135: el primer dock termina la prueba; jamás arranca Fase 2 solo."""
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if vacuum is not getattr(self, "vacuum", None):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False

        self._v135_phase2_blocked += 1
        self._v135_phase1_finished = True
        self._v121_stage = "edge_validated"
        self._v74_watch_active = False
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False
        self._auto_step2_pending = False
        self._auto_step2_scheduled = False

        try:
            self._sync_mapping_step_buttons()
            self._render_maps()
        except Exception:
            pass

        self._set_banner(
            "Paso 1 finalizado · proceso finalizó en la base. "
            "V135 no inicia Paso 2 automáticamente; EDGE listo para validar."
        )
        return False

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind == "v74_mapping_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._set_banner(
                "Mapeando · Paso 1: aspirado por bordes nativo activo · "
                "sin build-map previo y sin segundo START."
            )
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V135 ACTIVO · EDGE físico sin build-map previo",
            "===========================================================",
            f"inicios EDGE nativo={self._v135_edge_starts}",
            f"último EDGE={self._v135_edge_diag or '—'}",
            (
                "build-map antes de EDGE="
                f"{self._v135_build_before_edge} · "
                "Paso1 finalizado="
                f"{self._v135_phase1_finished}"
            ),
            (
                "arranques Fase2 bloqueados al dock="
                f"{self._v135_phase2_blocked}"
            ),
            "ruta V135: mode=0 -> sweep_type=2 -> UNA sola acción 2/3",
            "regla V135: arm_new_map/build-map está prohibido antes del EDGE",
            "regla V135: el Paso 1 no usa 7/3, 2/1 ni fallback",
            "regla V135: al primer dock se termina la prueba; no hay segundo aspirado automático",
            "regla V135: conserva pose V131, reacople V133 y toda la UI/mapa V134",
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

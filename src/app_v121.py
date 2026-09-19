import threading
import time
from tkinter import messagebox

import app_v120
import app_v9


class App(app_v120.App):
    """V121: perímetro primero, interior después, un solo build-map."""

    PHASE2_CONFIRM_TIMEOUT = 6.0

    def __init__(self):
        self._v121_stage = "idle"
        self._v121_phase2_requested = False
        self._v121_phase2_started = False
        self._v121_phase2_departed = False
        self._v121_phase2_attempts = 0
        self._v121_phase2_errors = 0
        self._v121_edge_dock_suppressed_closes = 0
        self._v121_final_reads_suppressed = 0
        self._v121_invalid_final_grids_rejected = 0
        self._v121_phase2_diag = {}
        super().__init__()

    # ====================================================== inicio 2 fases
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
            "Se va a borrar el mapa local seleccionado y comenzar un mapeo nuevo.\n\n"
            "V121 usa dos fases dentro de la misma sesión Xiaomi:\n"
            "1) recorre el perímetro completo para descubrir puertas y límites;\n"
            "2) al volver a la base, inicia el barrido global/interior SIN "
            "crear otro mapa nuevo.\n\n"
            "La planta sólo se guarda al terminar la fase 2 y únicamente si "
            "el grid Xiaomi final supera la validación geométrica.\n\n"
            "Dejá abiertas todas las puertas y empezá con el robot acoplado.",
            parent=self,
        )
        if not ok:
            return

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
        before = self._v71_debug_raw_pose()
        if before is not None:
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
            "Mapeando · Fase 1/2: preparando perímetro de toda la vivienda…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            try:
                build_diag = vacuum.arm_new_map(1)
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
                vacuum.start_mapping_exploration(confirm_timeout=5.0)
                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": dict(
                        getattr(
                            vacuum,
                            "_last_mapping_exploration_diag",
                            {},
                        )
                        or {}
                    ),
                }
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
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
                    "error": str(exc).strip() or type(exc).__name__,
                }
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapPhase1V121",
            daemon=True,
        ).start()

    # ============================================== watcher sin cierre fase 1
    def _v74_watch_mapping_worker(self, vacuum, serial):
        edge_seen_active = False
        global_seen_active = False

        while (
            serial == self._v74_mapping_serial
            and bool(getattr(self, "_v74_watch_active", False))
        ):
            if vacuum is not self.vacuum:
                return
            if not bool(getattr(self, "mapping_active", False)):
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("fault", 2, 2),
                    ("sweep_type", 2, 8),
                ])
                status = self._v67_int(values.get("status"))
                fault = self._v67_int(values.get("fault"))
                sweep_type = self._v67_int(values.get("sweep_type"))
            except Exception:
                time.sleep(self.STATUS_POLL_SECONDS)
                continue

            self._v74_last_status = status
            stage = str(getattr(self, "_v121_stage", "idle"))

            if stage == "edge":
                if status in (5, 6, 7):
                    edge_seen_active = True
                # V120 demostró que Edge vuelve físicamente al dock. Ese dock
                # es transición de fase, NO fin de mapeo.
                if edge_seen_active and fault in (None, 0) and status == 4:
                    self._v121_request_phase2(
                        vacuum,
                        serial,
                        source="watcher status=4",
                        sweep_type=sweep_type,
                    )

            elif stage == "transition":
                # Mientras se confirma la salida de fase 2, status=4 sigue
                # siendo el dock intermedio.
                pass

            elif stage == "global":
                if status in (5, 6, 7):
                    global_seen_active = True
                    self._v121_phase2_departed = True
                # El cierre final lo hace V84 al confirmar status=4. No
                # anticipamos el fin con status=3 para no capturar un mapa
                # mientras todavía está regresando.
                if global_seen_active and status == 3:
                    try:
                        self._set_banner(
                            "Fase 2/2 completa · volviendo a la base para "
                            "capturar el mapa Xiaomi final…"
                        )
                    except Exception:
                        pass

            time.sleep(self.STATUS_POLL_SECONDS)

    # =============================================== transición Edge → Global
    def _v121_request_phase2(self, vacuum, serial, source, sweep_type=None):
        if serial != int(getattr(self, "_v74_mapping_serial", -1)):
            return False
        if vacuum is not getattr(self, "vacuum", None):
            return False
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if self._v121_phase2_requested:
            return False

        self._v121_phase2_requested = True
        self._v121_stage = "transition"
        self.mapping_phase = 2
        self.mapping_transitioning = True
        self.mapping_step1_complete = True

        try:
            self._set_banner(
                "Perímetro completo · Fase 2/2: preparando barrido interior "
                "sobre el MISMO mapa Xiaomi…"
            )
        except Exception:
            pass

        self._v121_phase2_attempts += 1
        requested_at = time.monotonic()

        def worker():
            diag = {
                "source": str(source),
                "edge_sweep_type": sweep_type,
                "requested_at": round(requested_at, 3),
                "arm_new_map_called": False,
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

                # Reset de telemetría local solamente. NO arm_new_map().
                try:
                    vacuum.reset_live_path_session()
                except Exception as exc:
                    diag["path_reset_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                # El método ya existente sólo prepara ECO/agua=0,
                # sweep-type=0 y un START global. No crea un mapa nuevo.
                response = vacuum.start_mapping_interior()
                diag["response"] = repr(response)[:500]

                deadline = time.monotonic() + float(
                    self.PHASE2_CONFIRM_TIMEOUT
                )
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
                            self._post_ui(
                                "v121_phase2_started",
                                serial,
                                diag,
                            )
                            return
                    except Exception as exc:
                        diag["readback_error"] = (
                            str(exc).strip() or type(exc).__name__
                        )

                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.35)

                raise RuntimeError(
                    "El E10 no confirmó salida física para la fase 2 "
                    f"(status={diag.get('status_after')!r}, "
                    f"sweep-type={diag.get('sweep_type_after')!r})."
                )
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._post_ui(
                    "v121_phase2_error",
                    serial,
                    diag,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapPhase2V121",
            daemon=True,
        ).start()
        return True

    # ====================================== status=4 intermedio no cierra mapa
    def _v84_close_mapping_on_dock(self):
        stage = str(getattr(self, "_v121_stage", "idle"))
        if (
            bool(getattr(self, "mapping_active", False))
            and stage in ("edge", "transition")
        ):
            self._v121_edge_dock_suppressed_closes += 1
            if stage == "edge" and getattr(self, "vacuum", None) is not None:
                self._v121_request_phase2(
                    self.vacuum,
                    int(getattr(self, "_v74_mapping_serial", 0) or 0),
                    source="V84 status=4",
                    sweep_type=2,
                )
            self._v84_last_close_reason = (
                "V121: dock intermedio de Fase 1; cierre suprimido"
            )
            return True
        return super()._v84_close_mapping_on_dock()

    # Las lecturas finales sólo pertenecen al segundo regreso al dock.
    def _v93_schedule_final_reads(self):
        stage = str(getattr(self, "_v121_stage", "idle"))
        if (
            bool(getattr(self, "mapping_active", False))
            and stage in ("edge", "transition")
        ):
            self._v121_final_reads_suppressed += 1
            return False
        return super()._v93_schedule_final_reads()

    # =============================== jamás guardar un frame final inválido
    def _v107_choose_final_grid(self, grids):
        valid = []
        for grid in list(grids or []):
            if not isinstance(grid, dict):
                continue
            metrics = dict(grid.get("metrics") or {})
            if bool(metrics.get("valid")):
                valid.append(grid)
            else:
                self._v121_invalid_final_grids_rejected += 1

        if not valid:
            self._v107_final_candidates = 0
            self._v107_final_unique = 0
            return None, (
                "V121 rechazó todos los frames: ningún grid Xiaomi final "
                "superó la validación espacial"
            )
        return super()._v107_choose_final_grid(valid)

    # =========================================================== UI/eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started":
            self._v121_stage = "edge"
            result = super()._handle_ui_event(kind, payload)
            if bool(getattr(self, "mapping_active", False)):
                self.mapping_phase = 1
                self._set_banner(
                    "Mapeando · Fase 1/2: perímetro de toda la vivienda…"
                )
            return result

        if kind == "v121_phase2_started":
            serial = int(payload[0])
            diag = dict(payload[1] or {})
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._v121_phase2_diag = diag
            self._v121_stage = "global"
            self._v121_phase2_started = True
            self._v121_phase2_departed = True
            self.mapping_phase = 2
            self.mapping_transitioning = False
            self.mapping_step1_complete = True
            self.mapping_step2_complete = False

            # El status=4 anterior era un dock intermedio. Liberamos el latch
            # para que V84 pueda observar la nueva salida y luego el dock final.
            self._v84_dock_latched = False
            self._v84_returning = False
            self._v81_dock_confirmed = False
            self._v81_dock_timeout = False
            self._v73_dock_failed = False

            # Las métricas de cobertura corresponden ahora al barrido global.
            self._v74_started_at = time.monotonic()
            self._v74_last_discovery_at = self._v74_started_at
            self._v74_coverage_cells = set()
            self._v74_finish_requested = False
            self._v74_finish_reason = None
            self._v74_return_samples = 0

            self._set_banner(
                "Mapeando · Fase 2/2: interior/global sobre el mismo mapa "
                "Xiaomi · esperando final físico."
            )
            self._sync_mapping_step_buttons()
            return None

        if kind == "v121_phase2_error":
            serial = int(payload[0])
            diag = dict(payload[1] or {})
            if serial != int(getattr(self, "_v74_mapping_serial", -1)):
                return None

            self._v121_phase2_errors += 1
            self._v121_phase2_diag = diag
            self._v121_stage = "error"
            self._v74_watch_active = False
            self._v74_finish_requested = True
            self._v74_finish_reason = (
                "Fase 2 no iniciada: " + str(diag.get("error") or "error")
            )
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._set_banner(
                "El perímetro terminó, pero el E10 no inició la Fase 2. "
                "No se guardó el mapa parcial de 40 celdas."
            )
            return None

        if kind == "v107_final_grid_done":
            result = super()._handle_ui_event(kind, payload)
            if bool(getattr(self, "_v107_final_saved", False)):
                self._v121_stage = "complete"
                self.mapping_step2_complete = True
            return result

        return super()._handle_ui_event(kind, payload)

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        label = getattr(self, "map_status_label", None)
        if label is None:
            return result
        if bool(getattr(self, "_v93_finalizing", False)):
            return result
        if not bool(getattr(self, "mapping_active", False)):
            return result

        stage = str(getattr(self, "_v121_stage", "idle"))
        text = None
        if stage == "edge":
            text = "Mapeando · Fase 1/2: perímetro completo de la vivienda"
        elif stage == "transition":
            text = "Perímetro terminado · preparando Fase 2/2 interior"
        elif stage == "global":
            text = "Mapeando · Fase 2/2: interior/global"
        if text:
            try:
                label.configure(text=text, fg="#16a34a")
                self._v93_last_status_text = text
            except Exception:
                pass
        return result

    # ========================================================= diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V121 ACTIVO · perímetro → interior · mismo build-map",
            "==================================================================",
            (
                f"fase={self._v121_stage} · fase2 solicitada="
                f"{self._v121_phase2_requested} · iniciada="
                f"{self._v121_phase2_started} · salida confirmada="
                f"{self._v121_phase2_departed}"
            ),
            (
                f"fase2 intentos/errores="
                f"{self._v121_phase2_attempts}/{self._v121_phase2_errors}"
            ),
            f"fase2 diag={self._v121_phase2_diag or '—'}",
            (
                f"cierres status=4 de Fase 1 suprimidos="
                f"{self._v121_edge_dock_suppressed_closes} · "
                f"capturas finales prematuras suprimidas="
                f"{self._v121_final_reads_suppressed}"
            ),
            (
                f"frames finales inválidos rechazados="
                f"{self._v121_invalid_final_grids_rejected}"
            ),
            "regla V121: build-map-ii se ejecuta UNA sola vez, antes del perímetro",
            "regla V121: el primer status=4 es transición Edge→Global, no fin de mapa",
            "regla V121: Fase 2 usa start_mapping_interior sin arm_new_map y conserva la misma sesión",
            "regla V121: sólo el dock posterior a Fase 2 habilita las 3 lecturas finales Xiaomi",
            "regla V121: un grid con metrics.valid=False jamás se persiste como mapa final",
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

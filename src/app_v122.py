import threading
import time

import app_v121
import app_v9


class App(app_v121.App):
    """V122: Fase 2 whole-home por servicio 7/3, no start-sweep 2/1."""

    def __init__(self):
        self._v122_phase2_whole_home_starts = 0
        self._v122_phase2_whole_home_errors = 0
        self._v122_last_phase2_diag = {}
        super().__init__()

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
                "Perímetro completo · Fase 2/2: iniciando toda la vivienda "
                "sobre el MISMO mapa Xiaomi…"
            )
        except Exception:
            pass

        self._v121_phase2_attempts += 1
        self._v122_phase2_whole_home_starts += 1
        requested_at = time.monotonic()

        def worker():
            diag = {
                "source": str(source),
                "edge_sweep_type": sweep_type,
                "requested_at": round(requested_at, 3),
                "arm_new_map_called": False,
                "method": "7/3 set-room-clean ['', 0, 1]",
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

                # V122: NO usa start_mapping_interior(), porque esa ruta
                # termina en start-sweep 2/1 y fue la que quedó oscilando
                # dentro de la habitación de la base. Usamos la acción
                # whole-home de Sweep, análoga a la Edge que sí recorrió
                # físicamente toda la casa en V120/V121.
                response = vacuum.start_mapping_whole_home(
                    confirm_timeout=self.PHASE2_CONFIRM_TIMEOUT
                )
                native = dict(
                    getattr(vacuum, "_last_mapping_whole_home_diag", {}) or {}
                )
                diag.update({
                    "status_after": native.get("status_after"),
                    "sweep_type_after": native.get("sweep_type_after"),
                    "response": native.get("response", repr(response)[:500]),
                    "success": bool(native.get("success")),
                    "native": native,
                })

                if not diag["success"]:
                    raise RuntimeError(
                        native.get("error")
                        or "whole-home V122 no confirmó movimiento físico"
                    )

                self._post_ui(
                    "v121_phase2_started",
                    serial,
                    diag,
                )
            except Exception as exc:
                self._v122_phase2_whole_home_errors += 1
                diag["error"] = str(exc).strip() or type(exc).__name__
                self._post_ui(
                    "v121_phase2_error",
                    serial,
                    diag,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapWholeHomeV122",
            daemon=True,
        ).start()
        return True

    def _handle_ui_event(self, kind, payload):
        if kind == "v121_phase2_started":
            try:
                self._v122_last_phase2_diag = dict(payload[1] or {})
            except Exception:
                self._v122_last_phase2_diag = {}
            result = super()._handle_ui_event(kind, payload)
            if bool(getattr(self, "mapping_active", False)):
                self._set_banner(
                    "Mapeando · Fase 2/2: toda la vivienda (Sweep 7/3) "
                    "sobre el mismo mapa Xiaomi."
                )
            return result
        if kind == "v121_phase2_error":
            try:
                self._v122_last_phase2_diag = dict(payload[1] or {})
            except Exception:
                self._v122_last_phase2_diag = {}
            return super()._handle_ui_event(kind, payload)
        return super()._handle_ui_event(kind, payload)

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        if (
            bool(getattr(self, "mapping_active", False))
            and str(getattr(self, "_v121_stage", "")) == "global"
            and not bool(getattr(self, "_v93_finalizing", False))
        ):
            label = getattr(self, "map_status_label", None)
            if label is not None:
                text = "Mapeando · Fase 2/2: toda la vivienda"
                try:
                    label.configure(text=text, fg="#16a34a")
                    self._v93_last_status_text = text
                except Exception:
                    pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        native = (
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
            "DIAGNÓSTICO V122 ACTIVO · Fase 2 whole-home por Sweep 7/3",
            "================================================================",
            (
                f"inicios whole-home={self._v122_phase2_whole_home_starts} · "
                f"errores={self._v122_phase2_whole_home_errors}"
            ),
            f"fase2 app={self._v122_last_phase2_diag or '—'}",
            f"fase2 E10={native or '—'}",
            "ruta V122 Fase 2: sweep-type=0 -> 7/3 ['', 0, 1]",
            "regla V122: la Fase 2 NO usa start_mapping_interior ni start-sweep 2/1/2/3",
            "regla V122: ids vacíos + modo normal 0 = toda la vivienda; conserva el único build-map de Fase 1",
            "regla V122: no se usa recovery STOP/manual/restart para corregir el corredor observado en V121",
            "regla V122: V121 conserva dock intermedio, segundo dock final y rechazo de grids inválidos",
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

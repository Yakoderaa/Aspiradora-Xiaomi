import time

import app_v133
import app_v9


class App(app_v133.App):
    """V134: restaura el EDGE probado de V64/V68, sin segundo START."""

    def __init__(self):
        self._v134_edge_starts = 0
        self._v134_edge_diag = {}
        self._v134_non_edge_streak_started = None
        super().__init__()

    def _v131_start_edge_exploration(self, vacuum, confirm_timeout=5.0):
        """Paso 1 V134: V64/V68 exacto alrededor del build ya armado por V121.

        V121 ejecuta arm_new_map(1) una sola vez antes de entrar aquí.
        Esta función reproduce la parte física de V64:
          ECO + agua 0 -> repetición 0 -> sweep_type=2 -> 7/3 ['',2,1]
        No emite 2/1, 2/3 ni ningún fallback de movimiento.
        """
        vacuum._reject_mapping_during_targeted_clean(
            "start_mapping_exploration V134"
        )
        vacuum._prepare_mapping_vacuum()

        diag = {
            "route": "V64/V68: ECO -> repeat=0 -> sweep_type=2 -> 7/3 ['',2,1]",
            "status_before": None,
            "sweep_type_before": None,
            "response": None,
            "status_after": None,
            "sweep_type_after": None,
            "success": False,
            "single_motion_command": True,
            "generic_starts_disabled": ["2/1", "2/3"],
            "fallback": None,
            "error": None,
        }

        try:
            before = vacuum._get_many([
                ("status", 2, 1),
                ("sweep_type", 2, 8),
            ])
            diag["status_before"] = self._v67_int(before.get("status"))
            diag["sweep_type_before"] = self._v67_int(before.get("sweep_type"))
        except Exception as exc:
            diag["before_error"] = str(exc).strip() or type(exc).__name__

        try:
            vacuum.device.set_property_by(7, 1, 0)
        except Exception as exc:
            diag["repeat_reset_error"] = str(exc).strip() or type(exc).__name__

        try:
            vacuum.set_sweep_type(2)
        except Exception as exc:
            diag["sweep_type_set_error"] = str(exc).strip() or type(exc).__name__

        try:
            self._v134_edge_starts += 1
            self._v131_edge_primary_starts += 1
            response = vacuum.device.call_action_by(7, 3, ["", 2, 1])
            diag["response"] = repr(response)[:500]
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._v134_edge_diag = dict(diag)
            self._v131_edge_diag = dict(diag)
            vacuum._last_mapping_exploration_diag = dict(diag)
            raise

        # Sólo confirmamos que físicamente salió. No añadimos otro START.
        deadline = time.monotonic() + max(0.8, float(confirm_timeout or 0.0))
        last_status = None
        last_sweep = None
        while True:
            try:
                state = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                last_status = self._v67_int(state.get("status"))
                last_sweep = self._v67_int(state.get("sweep_type"))
                diag["status_after"] = last_status
                diag["sweep_type_after"] = last_sweep
                if last_status in (5, 6, 7):
                    diag["success"] = True
                    self._v134_edge_diag = dict(diag)
                    self._v131_edge_diag = dict(diag)
                    vacuum._last_mapping_exploration_diag = dict(diag)
                    return response
            except Exception as exc:
                diag["readback_error"] = str(exc).strip() or type(exc).__name__

            if time.monotonic() >= deadline:
                break
            time.sleep(0.30)

        diag["error"] = (
            "V134: la única acción EDGE 7/3 no produjo salida física "
            f"(status={last_status!r}, sweep_type={last_sweep!r}). "
            "No se lanzó ningún START alternativo."
        )
        self._v134_edge_diag = dict(diag)
        self._v131_edge_diag = dict(diag)
        vacuum._last_mapping_exploration_diag = dict(diag)
        raise RuntimeError(diag["error"])

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind == "v74_mapping_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            self._set_banner(
                "Mapeando · Fase 1/2: EDGE nativo V64/V68 · "
                "una sola orden de bordes, sin START global."
            )
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V134 ACTIVO · EDGE V64/V68 restaurado",
            "===================================================",
            f"inicios EDGE 7/3={self._v134_edge_starts}",
            f"último EDGE V134={self._v134_edge_diag or '—'}",
            "ruta V134: build-map único V121 -> ECO/agua=0 -> repeat=0 -> sweep_type=2 -> 7/3 ['',2,1]",
            "regla V134: el Paso 1 emite UNA sola orden de movimiento",
            "regla V134: 2/1 y 2/3 están prohibidos durante el arranque del Paso 1",
            "regla V134: no existe fallback automático; un fallo EDGE se informa sin convertirlo en limpieza global",
            "regla V134: conserva V133 para reacople progresivo, pose inicial, UI y resto del pipeline Xiaomi",
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

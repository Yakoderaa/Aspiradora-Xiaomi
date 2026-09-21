import app_v131
import app_v9


class App(app_v131.App):
    """V132: prueba EDGE por START genérico 2/1, sin rutas ya descartadas."""

    def __init__(self):
        self._v132_edge_starts = 0
        self._v132_edge_diag = {}
        super().__init__()

    def _v131_start_edge_exploration(self, vacuum, confirm_timeout=5.0):
        """V132: sweep_type=2 -> acción genérica 2/1.

        V130 demostró físicamente que 7/3 ['',2,1] inicia limpieza normal.
        V131 demostró físicamente que 2/3 con sweep_type=2 también inicia
        limpieza normal. V132 prueba la única ruta START aún no ensayada como
        primaria: Sweep 2/1, sin fallback a las dos rutas descartadas.
        """
        vacuum._reject_mapping_during_targeted_clean(
            "start_mapping_exploration V132"
        )
        vacuum._prepare_mapping_vacuum()

        diag = {
            "route": "sweep_type=2 -> 2/1 start-sweep",
            "status_before": None,
            "sweep_type_before": None,
            "response": None,
            "error": None,
            "status_after": None,
            "sweep_type_after": None,
            "started_by": None,
            "success": False,
            "known_bad_routes_disabled": ["7/3 ['',2,1]", "2/3"],
        }

        try:
            before_status, before_sweep = self._v131_read_edge_state(vacuum)
            diag["status_before"] = before_status
            diag["sweep_type_before"] = before_sweep
        except Exception as exc:
            diag["before_error"] = str(exc).strip() or type(exc).__name__

        try:
            vacuum.device.set_property_by(7, 1, 0)
        except Exception as exc:
            diag["repeat_reset_error"] = (
                str(exc).strip() or type(exc).__name__
            )

        vacuum.set_sweep_type(2)

        try:
            self._v132_edge_starts += 1
            self._v131_edge_primary_starts += 1
            diag["response"] = repr(
                vacuum._send_motor_start(
                    "mapping_edge_v132/start-sweep",
                    2,
                    1,
                    allow_when_guarded=True,
                )
            )[:500]
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._v132_edge_diag = dict(diag)
            self._v131_edge_diag = dict(diag)
            vacuum._last_mapping_exploration_diag = dict(diag)
            raise

        ok, status, sweep = self._v131_wait_edge_start(
            vacuum,
            confirm_timeout,
        )
        diag["status_after"] = status
        diag["sweep_type_after"] = sweep
        if ok:
            diag["success"] = True
            diag["started_by"] = "2/1 start-sweep"
            self._v132_edge_diag = dict(diag)
            self._v131_edge_diag = dict(diag)
            vacuum._last_mapping_exploration_diag = dict(diag)
            return diag["response"]

        diag["error"] = (
            "V132: el E10 no confirmó START EDGE seguro por 2/1 "
            f"(status={status!r}, sweep-type={sweep!r}). "
            "No se ejecutó fallback a 2/3 ni 7/3."
        )
        self._v132_edge_diag = dict(diag)
        self._v131_edge_diag = dict(diag)
        vacuum._last_mapping_exploration_diag = dict(diag)
        raise RuntimeError(diag["error"])

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V132 ACTIVO · EDGE por START 2/1",
            "==============================================",
            (
                f"intentos 2/1={self._v132_edge_starts} · "
                f"último={self._v132_edge_diag or '—'}"
            ),
            "ruta V132: sweep_type=2 -> 2/1 start-sweep",
            "rutas descartadas por prueba física: 7/3 ['',2,1] y 2/3",
            "regla V132: no existe fallback automático a una ruta ya observada como limpieza normal",
            "regla V132: el resto de V131, incluida pose provisional y reacople con carrera, queda intacto",
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

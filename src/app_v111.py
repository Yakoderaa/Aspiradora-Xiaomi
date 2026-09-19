import math

import app_v109
import app_v110
import app_v91
import app_v97
import app_v9
from xiaomi_e10_map_v111 import XiaomiE10MapV111


class App(app_v110.App):
    """V111: área de sesión retenida + diagnóstico completo compatible."""

    def __init__(self):
        self._v111_area_raw_max = 0
        self._v111_area_m2_max = 0.0
        self._v111_area_samples = 0
        self._v111_area_zero_samples = 0
        self._v111_floor_calls = 0
        super().__init__()

    # ================================================= diagnóstico compatible
    @classmethod
    def _v87_floor_cells(cls, snapshot=None):
        """Respeta el contrato classmethod de V87/V91/V97.

        V107 cambió este método a instancia y V110 intentó aceptar snapshot=None,
        pero las llamadas classmethod heredadas terminaron pasando el dict como
        self. V111 vuelve al contrato original y sólo usa helpers puros.
        """
        snap = snapshot if isinstance(snapshot, dict) else {}

        try:
            metrics = app_v97.App._v97_geometry_metrics.__func__(cls, snap)
        except Exception:
            metrics = {"mature": False}

        if not bool(metrics.get("mature")):
            try:
                return set(
                    app_v97.App._v97_trace_cells.__func__(cls, snap) or set()
                )
            except Exception:
                return set()

        try:
            return set(
                app_v91.App._v87_floor_cells.__func__(cls, snap) or set()
            )
        except Exception:
            return set()

    # ============================================== área acumulada de sesión
    def _v74_reset_session(self):
        result = super()._v74_reset_session()
        self._v111_area_raw_max = 0
        self._v111_area_m2_max = 0.0
        self._v111_area_samples = 0
        self._v111_area_zero_samples = 0

        client = getattr(self, "_v40_client", None)
        if isinstance(client, XiaomiE10MapV111):
            try:
                client.set_v111_area_raw(0, None)
            except Exception:
                pass
        return result

    def _v111_capture_area(self, status):
        try:
            raw = max(
                0,
                int(getattr(status, "cleaning_area_raw", 0) or 0),
            )
        except Exception:
            raw = 0

        try:
            area_m2 = max(
                0.0,
                float(getattr(status, "cleaning_area", 0.0) or 0.0),
            )
        except Exception:
            area_m2 = 0.0

        if raw > 0:
            self._v111_area_samples += 1
            self._v111_area_raw_max = max(
                int(self._v111_area_raw_max),
                raw,
            )
        else:
            self._v111_area_zero_samples += 1

        if area_m2 > 0.0 and math.isfinite(area_m2):
            self._v111_area_m2_max = max(
                float(self._v111_area_m2_max),
                area_m2,
            )

    def _render_status(self, status):
        # Capturamos antes y después de V110; V110 puede reflejar el valor
        # instantáneo, mientras V111 mantiene el máximo de la sesión.
        self._v111_capture_area(status)
        result = super()._render_status(status)

        # Nunca permitir que un 0 del dock reemplace el área ya observada.
        if self._v111_area_raw_max > 0:
            self._v110_cleaning_area_raw = int(self._v111_area_raw_max)
        if self._v111_area_m2_max > 0.0:
            self._v110_cleaning_area_m2 = float(self._v111_area_m2_max)

        client = getattr(self, "_v40_client", None)
        if isinstance(client, XiaomiE10MapV111):
            try:
                client.set_v111_area_raw(
                    self._v111_area_raw_max,
                    self._v111_area_m2_max,
                )
            except Exception:
                pass
        return result

    # ======================================================== cliente V111
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV111)
        ):
            self._v40_client = XiaomiE10MapV111(vacuum, settings)
            self._v40_client_vacuum = vacuum

        try:
            points = (
                list(self.local_map.snapshot().get("points") or [])
                if self.local_map
                else []
            )
            self._v40_client.set_v109_reference_path(points)
        except Exception:
            pass

        try:
            self._v40_client.set_v111_area_raw(
                self._v111_area_raw_max,
                self._v111_area_m2_max,
            )
        except Exception:
            pass
        return self._v40_client

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        map_diag = (
            dict(getattr(client, "last_v111_diagnostics", {}) or {})
            if isinstance(client, XiaomiE10MapV111)
            else {}
        )

        inferred = map_diag.get("target_m2")
        grid_m2 = map_diag.get("grid_m2")
        rel_error = map_diag.get("relative_error")
        inferred_scale = map_diag.get("inferred_scale")
        reference = map_diag.get("reference_path_m2")

        lines = [
            "DIAGNÓSTICO V111 ACTIVO · área retenida + F12 completo",
            "========================================================",
            (
                f"área sesión: raw máximo={self._v111_area_raw_max} · "
                f"m² presentado máximo={self._v111_area_m2_max:.2f} · "
                f"muestras útiles={self._v111_area_samples} · "
                f"ceros={self._v111_area_zero_samples}"
            ),
            (
                f"inferencia área B112: factor={inferred_scale if inferred_scale is not None else '—'} · "
                f"trayectoria≈{float(reference):.2f} m²"
                if reference is not None
                else "inferencia área B112: trayectoria≈—"
            ),
            (
                f"objetivo final={float(inferred):.2f} m² · "
                f"grid elegido={float(grid_m2):.2f} m² · "
                f"error={float(rel_error):.1%}"
                if inferred is not None and grid_m2 is not None and rel_error is not None
                else "objetivo/grid final: todavía sin captura V111"
            ),
            (
                f"gate área final: aceptado={map_diag.get('accepted','—')} · "
                f"motivo={map_diag.get('reject_reason') or '—'}"
            ),
            (
                "regla V111: el máximo de cleaning-area sobrevive retorno/dock "
                "y alimenta las tres lecturas finales"
            ),
            (
                "regla V111: _v87_floor_cells vuelve a ser classmethod; "
                "F12 no debe caer al diagnóstico de emergencia por snapshot"
            ),
            (
                "regla V111: si ningún candidato final se acerca al área física "
                "dentro del 42%, no se publica una planta que sabemos incorrecta"
            ),
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

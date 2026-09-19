import app_v91
from xiaomi_e10_map_v92 import XiaomiE10MapV92


class App(app_v91.App):
    """V92: búsqueda de layout 2bpp + acumulación temporal del grid B112."""

    def __init__(self):
        self._v92_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV92(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def start_new_mapping(self):
        client = getattr(self, "_v40_client", None)
        if client is not None and hasattr(client, "reset_v92_accumulator"):
            try:
                client.reset_v92_accumulator("Mapear vivienda")
            except Exception:
                pass
        return super().start_new_mapping()

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            if client is not None:
                self._v92_diag = dict(
                    getattr(client, "last_v92_diagnostics", {}) or {}
                )
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        diag = dict(
            getattr(client, "last_v92_diagnostics", {}) or self._v92_diag or {}
        )
        current = dict(diag.get("current_best") or {})
        accumulated = dict(diag.get("accum_best") or {})
        selected = dict(diag.get("selected") or {})
        top = list(diag.get("top") or [])

        def desc(item):
            if not item:
                return "—"
            return (
                f"{item.get('label', '—')} · válido={bool(item.get('valid'))} · "
                f"nonzero={item.get('nonzero', '—')} · comp={item.get('components', '—')} · "
                f"mayor={item.get('largest', '—')} · ratio={item.get('largest_ratio', '—')} · "
                f"ady={item.get('adjacency_ratio', '—')} · "
                f"baseΔ={item.get('base_distance', '—')}"
            )

        top_lines = []
        for index, item in enumerate(top[:5], 1):
            top_lines.append(f"    #{index} {desc(item)}")
        if not top_lines:
            top_lines.append("    —")

        lines = [
            "DIAGNÓSTICO V92 ACTIVO · layouts 2bpp + acumulación de frames",
            "================================================================",
            (
                "frames: "
                f"únicos={diag.get('unique_frames', 0)} · "
                f"hashes={diag.get('unique_hashes', 0)} · "
                f"nuevo={bool(diag.get('new_frame'))} · "
                f"resets={diag.get('reset_count', 0)}"
            ),
            (
                "base para grid: "
                f"{diag.get('base_cell', '—')} · "
                f"fallback 60_60={bool(diag.get('base_fallback'))}"
            ),
            f"mejor frame: {desc(current)}",
            f"mejor acumulado: {desc(accumulated)}",
            f"seleccionado: {desc(selected)}",
            (
                "búsqueda: "
                f"28 layouts físicos × 7 máscaras = "
                f"{diag.get('candidate_count', 0)} candidatos/frame · "
                f"acumulados={diag.get('accum_candidate_count', 0)}"
            ),
            "top candidatos V92:",
            *top_lines,
            "regla V92: prueba h4, v4 y bloque 2x2 con las 24 permutaciones locales",
            "regla V92: cada hash nuevo se une por candidato; un delta aislado no tiene que parecer un mapa completo",
            "regla V92: V57 sigue siendo el gate final; ningún acumulado se muestra si continúa fragmentado",
            "regla V92: 255_255 no puede usarse como base del grid; se corrige a 60_60 sólo para geometría",
            "",
            "",
        ]
        return "\n".join(lines) + inherited

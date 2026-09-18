import app_v62
from xiaomi_e10_map_v62 import XiaomiE10MapV62


class App(app_v62.App):
    """V63: la ruta EDGE real también queda detrás del gate de persistencia."""

    def __init__(self):
        self._v63_diag = {}
        super().__init__()

    def _diagnostic_text(self):
        vacuum = getattr(self, "vacuum", None)
        direct = dict(getattr(vacuum, "last_map_persistence_diag", {}) or {}) if vacuum else {}
        client = getattr(self, "_v40_client", None)
        client_diag = dict(getattr(client, "last_v62_diagnostics", {}) or {}) if client else {}
        write = direct or dict(client_diag.get("persistence_write") or {})
        attempts = list(write.get("attempts") or [])
        inherited = super()._diagnostic_text()

        lines = [
            "DIAGNÓSTICO V63 ACTIVO · gate remember-state en EDGE real",
            "=========================================================",
            f"controlador activo: {type(vacuum).__name__ if vacuum is not None else '—'}",
            "ruta Paso 1: XiaomiE10Live → XiaomiE10Edge.start_mapping_perimeter → _prepare_mapping_vacuum",
            f"remember-state solicitado: {write.get('desired')!r} · antes={write.get('before')!r} · después={write.get('after')!r}",
            f"persistencia confirmada antes de EDGE: {bool(write.get('success')) if write else '—'}",
            "intentos directos 10/1 del controlador:",
        ]
        if attempts:
            for item in attempts[-6:]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "    "
                    + f"#{item.get('attempt', '—')} {item.get('strategy') or item.get('stage') or '—'}"
                    + f" · code={item.get('code')!r}"
                    + (f" · readback={item.get('readback')!r}" if "readback" in item else "")
                    + f" · verified={bool(item.get('verified'))}"
                    + (f" · error={item.get('error')}" if item.get("error") else "")
                    + (f" · verify_error={item.get('verify_error')}" if item.get("verify_error") else "")
                )
        else:
            lines.append("    — todavía no hubo un intento de Paso 1 en esta sesión")

        lines.extend([
            "regla V63: la acción EDGE 7/3 es inalcanzable hasta que 10/1 lea exactamente 1",
            "regla V63: si 10/1 falla, tampoco se tocan agua/succión/modo ni sweep-type para iniciar el recorrido",
            "corrección diagnóstico: 10/23 se muestra como map-uploads (0=Upload, 1=Do Not Upload)",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

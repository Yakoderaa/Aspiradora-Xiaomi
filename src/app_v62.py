import app_v61
from xiaomi_e10_map_v62 import XiaomiE10MapV62


class App(app_v61.App):
    """V62 histórico: diagnóstico de una hipótesis de remember-state, supersedida por V64."""

    def __init__(self):
        self._v62_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV62(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v62_diag = dict(
                getattr(client, "last_v62_diagnostics", {}) or
                getattr(client, "last_v61_diagnostics", {}) or {}
            )
        diag = dict(self._v62_diag or {})
        inherited = super()._diagnostic_text()
        write = dict(diag.get("persistence_write") or {})
        attempts = list(write.get("attempts") or [])

        lines = [
            "DIAGNÓSTICO V62 HISTÓRICO · hipótesis remember-state supersedida por V64",
            "===========================================================================",
            f"fix parser V61 _result_rows: {bool(diag.get('v62_result_rows_fixed'))}",
            f"remember-state solicitado: {write.get('desired')!r} · antes={write.get('before')!r} · después={write.get('after')!r}",
            f"remember-state verificado: {bool(write.get('success')) if write else '—'}",
            "intentos setter 10/1:",
        ]
        if attempts:
            for item in attempts[-6:]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "    "
                    + f"#{item.get('attempt', '—')} {item.get('strategy') or item.get('stage') or '—'}"
                    + f" · code={item.get('code')!r}"
                    + (f" · readback={item.get('readback')!r}" if 'readback' in item else "")
                    + f" · verified={bool(item.get('verified'))}"
                    + (f" · error={item.get('error')}" if item.get('error') else "")
                    + (f" · verify_error={item.get('verify_error')}" if item.get('verify_error') else "")
                )
        else:
            lines.append("    — todavía no se intentó cambiar 10/1 en esta sesión")

        lines.extend([
            "corrección V64: 10/1 ya NO es gate; Paso 1 usa build-map-ii 10/17",
            "regla CI V62: cualquier smoke test con código distinto de 0 cancela el build y bloquea la release",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import app_v58
from xiaomi_e10_map_v59 import XiaomiE10MapV59


class App(app_v58.App):
    """V59: todas las rutas conocidas compiten; gana el primer mapa válido."""

    def __init__(self):
        self._v59_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV59(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    @staticmethod
    def _method_line(item):
        if not isinstance(item, dict):
            return "—"
        status = item.get("status") or ("OK" if item.get("ok") else "FAIL")
        extras = []
        for key, label in (
            ("duration_ms", "ms"),
            ("bytes", "B"),
            ("sha12", "sha12"),
            ("endpoint", "endpoint"),
            ("decoder", "decoder"),
            ("refs", "refs"),
        ):
            value = item.get(key)
            if value not in (None, "", [], {}):
                extras.append(f"{label}={value}")
        if item.get("error"):
            extras.append(f"error={item.get('error')}")
        return f"{status} · {item.get('method') or '—'}" + (
            " · " + " · ".join(extras) if extras else ""
        )

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v59_diag = dict(
                getattr(client, "last_v59_diagnostics", {}) or {}
            )
        diag = dict(self._v59_diag or {})
        inherited = super()._diagnostic_text()

        methods = list(diag.get("methods") or [])
        winner = diag.get("winner") or "—"
        winner_meta = dict(diag.get("winner_meta") or {})
        started = diag.get("started_at")
        finished = diag.get("finished_at")
        elapsed = None
        try:
            if started:
                elapsed = round(float((finished or started) - started), 2)
        except Exception:
            elapsed = None

        lines = [
            "DIAGNÓSTICO V59 ACTIVO · competencia total de métodos",
            "=======================================================",
            f"fase: {diag.get('phase') or '—'} · GANADOR: {winner}",
            f"candidatos FDS: {int(diag.get('candidate_refs', 0) or 0)} · "
            f"map-ids: {diag.get('map_ids') or []} · tiempo cerrado={elapsed!r}s",
            f"meta ganador: {winner_meta or {}}",
            "métodos:",
        ]
        if methods:
            for item in methods[-80:]:
                lines.append("    " + self._method_line(item))
        else:
            lines.append("    —")
        lines.extend([
            "regla V59: múltiples rutas corren en paralelo; el primer mapa que pasa un decoder/validación gana y se cachea",
            "",
        ])
        return "\n".join(lines) + "\n" + inherited


if __name__ == "__main__":
    app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

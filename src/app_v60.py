import app_v58
import app_v59
from xiaomi_e10_map_v60 import XiaomiE10MapV60


class App(app_v59.App):
    """V60: B112 estructurado, LAN serial y diagnóstico sin falsos refs."""

    def __init__(self):
        self._v60_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV60(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    @staticmethod
    def _method_line_v60(item):
        if not isinstance(item, dict):
            return "—"
        status = item.get("status") or ("OK" if item.get("ok") else "FAIL")
        extras = []
        for key, label in (
            ("duration_ms", "ms"),
            ("out_piids", "out"),
            ("map_id", "map_id"),
            ("map_type", "type"),
            ("timestamp", "timestamp"),
            ("renew_map", "renew"),
            ("map_ids", "map_ids"),
            ("map_count", "maps"),
            ("refs", "refs"),
            ("bytes", "B"),
            ("sha12", "sha12"),
            ("endpoint", "endpoint"),
            ("changed", "changed"),
            ("known_stale", "known_stale"),
        ):
            value = item.get(key)
            if value not in (None, "", [], {}):
                extras.append(f"{label}={value}")

        piid4 = item.get("piid4")
        if isinstance(piid4, dict):
            shape = piid4.get("shape") or {}
            extras.append(
                "piid4="
                + f"{shape.get('kind', '—')}"
                + (f"/len={shape.get('len')}" if shape.get("len") is not None else "")
                + f"/json={bool(piid4.get('json'))}"
                + f"/valid_maps={int(piid4.get('valid_maps', 0) or 0)}"
            )

        if item.get("error"):
            extras.append(f"error={item.get('error')}")
        return f"{status} · {item.get('method') or '—'}" + (
            " · " + " · ".join(extras) if extras else ""
        )

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v60_diag = dict(
                getattr(client, "last_v60_diagnostics", {}) or {}
            )
        diag = dict(self._v60_diag or {})

        # Saltamos deliberadamente el bloque V59: era el diagnóstico que
        # convertía metadatos como piid=4/hello/cloud en referencias FDS.
        inherited = app_v58.App._diagnostic_text(self)

        methods = list(diag.get("methods") or [])
        winner = diag.get("winner") or "—"
        started = diag.get("started_at")
        finished = diag.get("finished_at")
        elapsed = None
        try:
            if started:
                elapsed = round(float((finished or time.time()) - started), 2)
        except Exception:
            elapsed = None

        lines = [
            "DIAGNÓSTICO V60 ACTIVO · B112 estructurado / LAN serial",
            "========================================================",
            f"fase: {diag.get('phase') or '—'} · GANADOR: {winner}",
            "corrección V59: piid=4 es el CAMPO map-list, no un map-id; "
            f"corregido={bool(diag.get('false_v59_mapid4_fixed'))}",
            f"LAN serializado: {bool(diag.get('lan_serialized'))} · "
            f"map-ids válidos: {diag.get('map_ids') or []}",
            f"candidatos FDS estructurados: {int(diag.get('candidate_refs', 0) or 0)} · "
            f"tiempo={elapsed!r}s",
            f"meta ganador: {diag.get('winner_meta') or {}}",
            "métodos:",
        ]
        if methods:
            for item in methods[-70:]:
                lines.append("    " + self._method_line_v60(item))
        else:
            lines.append("    —")

        map_list = diag.get("map_list") or []
        if map_list:
            lines.append("10/1 map-list exacto:")
            for item in map_list:
                if not isinstance(item, dict):
                    continue
                if item.get("error"):
                    lines.append(
                        f"    {item.get('transport')}: error={item.get('error')}"
                    )
                    continue
                p4 = item.get("piid4") or {}
                shape = p4.get("shape") or {}
                lines.append(
                    "    "
                    + f"{item.get('transport')}: out={item.get('out_piids') or []} · "
                    + f"piid4={shape.get('kind', '—')}"
                    + (f"/len={shape.get('len')}" if shape.get("len") is not None else "")
                    + f" · json={bool(p4.get('json'))} · "
                    + f"map_ids={item.get('map_ids') or []}"
                )

        lines.extend([
            "seguridad diagnóstico: URLs FDS firmadas, firmas, expiraciones e identificadores de ruta se ocultan",
            "regla V60: sólo PIID 4 parseado como lista real crea map-ids; "
            "acciones usan exclusivamente PIID 6/7/18/21",
            "",
        ])
        return "\n".join(lines) + "\n" + inherited


# import tardío para no ensuciar el arranque principal
import time


if __name__ == "__main__":
    app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

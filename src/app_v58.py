import app_v57
from xiaomi_e10_map_v58 import XiaomiE10MapV58


class App(app_v57.App):
    """V58: eventos Cloud sin UID + MIoT actions Cloud + candidatos FDS."""

    def __init__(self):
        self._v58_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV58(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            self._v58_diag = dict(
                getattr(client, "last_v58_diagnostics", {}) or {}
            ) if client else {}
        return result

    @staticmethod
    def _fmt_queries(event_queries):
        if not isinstance(event_queries, dict):
            return "—"
        parts = []
        for key, value in event_queries.items():
            if key == "error":
                parts.append(f"error={value}")
                continue
            if not isinstance(value, list):
                continue
            ok = sum(1 for item in value if isinstance(item, dict) and item.get("ok"))
            records = sum(
                int(item.get("records", 0) or 0)
                for item in value
                if isinstance(item, dict)
            )
            errs = [
                str(item.get("error"))
                for item in value
                if isinstance(item, dict) and not item.get("ok") and item.get("error")
            ]
            text = f"{key}: {ok}/{len(value)} rutas OK · records={records}"
            if errs:
                text += f" · err={errs[0][:90]}"
            parts.append(text)
        return " | ".join(parts) or "—"

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v58_diag = dict(
                getattr(client, "last_v58_diagnostics", {}) or {}
            )
        diag = dict(self._v58_diag or {})
        inherited = super()._diagnostic_text()

        attempts = list(diag.get("attempts") or [])
        attempt_lines = []
        for item in attempts:
            if not isinstance(item, dict):
                continue
            attempt_lines.append(
                "    "
                + f"{item.get('transport') or '?'} {item.get('action') or '?'}"
                + f" · endpoint={item.get('endpoint') or 'LAN'}"
                + f" · ok={bool(item.get('ok'))}"
                + f" · code={item.get('code')!r}"
                + f" · map_id={item.get('map_id')!r}"
                + f" · type={item.get('map_type')!r}"
                + f" · timestamp={item.get('timestamp')!r}"
                + f" · renew={item.get('renew_map')!r}"
                + f" · refs={len(item.get('refs') or [])}"
                + (
                    f" · error={item.get('error')}"
                    if item.get("error")
                    else ""
                )
            )

        probes = list(diag.get("candidate_probes") or [])
        probe_lines = []
        for item in probes[-12:]:
            if not isinstance(item, dict):
                continue
            probe_lines.append(
                "    "
                + f"{item.get('source') or '?'}"
                + f" · kind={item.get('reference_kind') or '?'}"
                + f" · HTTP={item.get('http')!r}"
                + f" · bytes={int(item.get('bytes', 0) or 0)}"
                + f" · sha12={item.get('sha12') or '—'}"
                + f" · changed={bool(item.get('changed'))}"
                + f" · ok={bool(item.get('ok'))}"
                + f" · decoder={item.get('decoder') or '—'}"
                + (
                    f" · error={item.get('error')}"
                    if item.get("error")
                    else ""
                )
            )

        events = list(diag.get("events") or [])
        event_text = ", ".join(
            f"{e.get('key')}@{int(float(e.get('time') or 0))}"
            f"(id={e.get('map_id')!r},ts={e.get('timestamp')!r})"
            for e in events[:8]
            if isinstance(e, dict)
        ) or "—"

        clean = diag.get("clean_end")
        fresh = dict(diag.get("fresh_meta") or {})
        lines = [
            "DIAGNÓSTICO V58 ACTIVO · Cloud realtime + eventos sin UID",
            "==========================================================",
            f"hash base: {diag.get('baseline_hash') or '—'} · hash final: {diag.get('hash_after') or '—'} · ganador: {diag.get('winner') or '—'}",
            f"eventos encontrados: {event_text}",
            f"consultas eventos: {self._fmt_queries(diag.get('event_queries'))}",
            f"clean-end durante refresh: {clean if clean is not None else '—'}",
            f"mapa fresco cacheado: fuente={fresh.get('source') or '—'} · endpoint={fresh.get('endpoint') or '—'} · "
            f"bytes={int(fresh.get('bytes', 0) or 0)} · sha12={fresh.get('sha12') or '—'} · decoder={fresh.get('decoder') or '—'}",
            "acciones LAN + Cloud:",
            *(attempt_lines or ["    —"]),
            "candidatos FDS probados:",
            *(probe_lines or ["    —"]),
            "regla: se prueban eventos con/sin UID; ningún identificador se imprime completo en diagnóstico",
            "",
        ]
        return "\n".join(lines) + "\n" + inherited


if __name__ == "__main__":
    app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

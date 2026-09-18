import time

import app_v60
from xiaomi_e10_map_v61 import XiaomiE10MapV61


class App(app_v60.App):
    """V61: persistencia real del mapa B112 + sondeo condicionado por estado."""

    POST_CLEAN_SECONDS = 300.0
    POST_CLEAN_POLL_SECONDS = 3.0

    def __init__(self):
        self._v61_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV61(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v61_diag = dict(
                getattr(client, "last_v61_diagnostics", {}) or {}
            )
        diag = dict(self._v61_diag or {})
        state = dict(diag.get("state") or {})
        inherited = super()._diagnostic_text()

        remember = state.get("remember_state")
        remember_text = (
            "1 (informativo; V64 no lo fuerza)"
            if remember == 1
            else "0 (informativo; V64 no lo fuerza)"
            if remember == 0
            else "desconocido"
        )
        privacy = state.get("map_privacy")
        privacy_text = (
            "Enable / permite mapa"
            if privacy == 0
            else "DisEnable / bloquea mapa"
            if privacy == 1
            else "desconocido"
        )

        lines = [
            "DIAGNÓSTICO V61 ACTIVO · persistencia de mapa B112",
            "=====================================================",
            f"estado B112: {state.get('status') or '—'}",
            f"remember-state 10/1: {remember!r} · {remember_text}",
            f"cur-map-id 10/2: {state.get('cur_map_id')!r} · map-num 10/3: {state.get('map_num')!r}",
            f"build-map 10/14: {state.get('build_map')!r} · has-new-map 10/19: {state.get('has_new_map')!r}",
            f"map-privacy 10/23: {privacy!r} · {privacy_text}",
            f"mapa guardado: {bool(state.get('saved_map'))} · pendiente: {bool(state.get('pending_map'))}",
            f"upload realtime permitido: {bool(state.get('allow_realtime_upload'))} · omitido={bool(diag.get('skip_realtime_upload'))}",
            f"motivo omisión: {diag.get('skip_reason') or '—'}",
            "corrección V64: en xiaomi.vacuum.b112, 10/23 es map-privacy (0=Enable, 1=DisEnable)",
            "corrección V64: remember-state 10/1 queda sólo como telemetría; no se fuerza a 1",
            "regla FDS: se permite realtime con mapa guardado, pendiente o build-map activo; clean-end sigue como ruta final",
        ]

        transports = list(diag.get("transports") or [])
        if transports:
            lines.append("lectura de estado:")
            for item in transports:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "    "
                    + f"{item.get('source') or '—'} · ok={bool(item.get('ok'))}"
                    + f" · campos={int(item.get('count', 0) or 0)}"
                    + f" · ms={int(item.get('duration_ms', 0) or 0)}"
                    + (f" · error={item.get('error')}" if item.get("error") else "")
                )

        record = diag.get("record_map")
        if isinstance(record, dict):
            lines.append(
                "clean-end final: "
                + f"éxito={bool(record.get('success'))}"
                + f" · candidatos={record.get('candidates', record.get('records', 0))!r}"
            )

        lines.extend(["", ""])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

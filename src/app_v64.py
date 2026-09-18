import app_v63
from xiaomi_e10_map_v64 import XiaomiE10MapV64


class App(app_v63.App):
    """V64: creación de mapa mediante acciones oficiales del B112."""

    def __init__(self):
        self._v64_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV64(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _diagnostic_text(self):
        vacuum = getattr(self, "vacuum", None)
        build = dict(getattr(vacuum, "last_map_build_diag", {}) or {}) if vacuum else {}
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v64_diag = dict(
                getattr(client, "last_v64_diagnostics", {})
                or getattr(client, "last_v62_diagnostics", {})
                or {}
            )
        diag = dict(self._v64_diag or {})
        state = dict(diag.get("state") or {})
        attempts = list(build.get("attempts") or diag.get("build_request", {}).get("attempts") or [])
        inherited = super()._diagnostic_text()

        privacy = state.get("map_privacy")
        privacy_text = (
            "Enable / permite mapas" if privacy == 0
            else "DisEnable / bloquea mapas" if privacy == 1
            else "desconocido"
        )

        lines = [
            "DIAGNÓSTICO V64 ACTIVO · build-map oficial xiaomi.vacuum.b112",
            "==============================================================",
            f"controlador activo: {type(vacuum).__name__ if vacuum is not None else '—'}",
            "Paso 1: 10/17 build-map-ii(mode=1) → preparación ECO → EDGE 7/3",
            "fallback documentado: 10/11 build-new-map(mode=1), sólo si 10/17 es rechazado",
            f"build solicitado: {build.get('requested_mode')!r} · éxito={bool(build.get('success')) if build else '—'} · ganador={build.get('winner') or '—'}",
            f"build-map 10/14: {state.get('build_map')!r} · has-new-map 10/19: {state.get('has_new_map')!r}",
            f"cur-map-id 10/2: {state.get('cur_map_id')!r} · map-num 10/3: {state.get('map_num')!r}",
            f"map-privacy 10/23: {privacy!r} · {privacy_text}",
            f"remember-state 10/1: {state.get('remember_state')!r} · informativo, V64 no lo escribe",
            f"build armado: {bool(state.get('build_armed'))} · realtime permitido: {bool(state.get('allow_realtime_upload'))}",
            "intentos build-map:",
        ]

        if attempts:
            for item in attempts[-4:]:
                if not isinstance(item, dict):
                    continue
                ts = item.get("timestamp")
                lines.append(
                    "    "
                    + f"10/{item.get('aiid', '—')} {item.get('action') or '—'}"
                    + f" · code={item.get('code')!r}"
                    + f" · timestamp={'sí' if ts is not None else '—'}"
                    + f" · build-readback={item.get('build_map_readback')!r}"
                    + f" · privacy={item.get('map_privacy_readback')!r}"
                    + f" · accepted={bool(item.get('accepted'))}"
                    + (f" · error={item.get('error')}" if item.get("error") else "")
                    + (f" · readback_error={item.get('readback_error')}" if item.get("readback_error") else "")
                )
        else:
            lines.append("    — todavía no se intentó crear un mapa en esta sesión")

        lines.extend([
            "regla V64: no se fuerza remember-state=1",
            "regla V64: 10/23 vuelve a su semántica exacta B112 map-privacy (0=Enable, 1=DisEnable)",
            "regla V64: si el robot rechaza 10/17 y 10/11, EDGE no arranca",
            "regla V64: con build armado/build-map activo se habilita la búsqueda realtime aunque cur-map-id siga en 0",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

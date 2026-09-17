import threading

import app_v51
from xiaomi_e10_probe_v52 import XiaomiE10ProbeV52


class App(app_v51.App):
    """V52: consulta 10/12 con el rango uint32 completo documentado."""

    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10ProbeV52(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui("connect_error", str(exc).strip() or "El robot no respondió correctamente.", quiet)

        threading.Thread(target=worker, daemon=True).start()

    def _diagnostic_text(self):
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        probe = dict(state.get("v52_full_range_probe") or {})
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V52 ACTIVO · get-cur-path con rango uint32 oficial\n"
            "================================================================\n"
            "acción: 10/12 get-cur-path · sólo lectura de trayectoria\n"
            f"rango oficial probado: {probe.get('range') or (0, 4294967295)} · "
            f"intentado: {bool(probe.get('attempted'))} · intentos: {int(probe.get('attempts', 0) or 0)}\n"
            f"code: {probe.get('code')!r} · salida: {probe.get('output_kind') or '—'} "
            f"({int(probe.get('output_length', 0) or 0)} unidades)\n"
            f"puntos interpretados: {int(probe.get('points', 0) or 0)} · "
            f"X/Y distintos: {int(probe.get('distinct_xy', 0) or 0)} · "
            f"trayectoria aceptada: {bool(probe.get('accepted'))}\n"
            f"error rango completo: {probe.get('error') or '—'}\n"
            f"fallback heredado usado: {bool(probe.get('fallback_used'))} · "
            f"rango fallback: {probe.get('fallback_range') or '—'}\n"
            "regla visual: una muestra aislada no confirma movimiento; se requieren al menos dos X/Y distintos\n"
            "seguridad: V52 no toca 10/23 ni reactiva 10/18, 10/15 o 10/6; V51/V45 siguen controlando uploads\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

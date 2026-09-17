import threading

import app_v54
from xiaomi_e10_probe_v55 import XiaomiE10ProbeV55


class App(app_v54.App):
    """V55: mapa operativo con movimiento/recorrido temporal confirmado de 10/24."""

    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10ProbeV55(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(
                        f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10."
                    )
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui(
                    "connect_error",
                    str(exc).strip() or "El robot no respondió correctamente.",
                    quiet,
                )

        threading.Thread(target=worker, daemon=True).start()

    def _diagnostic_text(self):
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        live = dict(state.get("v55_live_track") or {})
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V55 ACTIVO · recorrido operativo por 10/24\n"
            "=======================================================\n"
            "modo principal: cambios temporales X/Y reales de robot-location 10/24\n"
            f"movimiento confirmado: {bool(live.get('motion_confirmed'))} · "
            f"cambios X/Y: {int(live.get('xy_changes', 0) or 0)}\n"
            f"puntos vivos persistentes: {int(live.get('points', 0) or 0)} · "
            f"nuevos última lectura: {int(live.get('new_points', 0) or 0)}\n"
            f"última pose 10/24: {live.get('last_pose')!r}\n"
            f"lecturas 10/12 omitidas del loop: {int(live.get('action_reads_skipped', 0) or 0)}\n"
            f"fuente trayectoria efectiva: {state.get('path_source') or '—'}\n"
            f"fuente posición efectiva: {state.get('position_source') or '—'}\n"
            "regla: la primera muestra aislada no mueve; el segundo X/Y distinto confirma movimiento y arranca la polilínea\n"
            "seguridad: cambios de base no cuentan; V45 conserva sentinelas/guardas y V55 no reactiva uploads inseguros\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

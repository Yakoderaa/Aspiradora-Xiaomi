import threading
import time

import app_v46
from xiaomi_e10_map_v47 import XiaomiE10MapV47


class App(app_v46.App):
    """V47: habilita temporalmente 10/23 para recibir trayectoria Cloud.

    El diagnóstico de V46 mostró consultas correctas a get_user_device_data
    pero cero registros mientras map-privacy=1. En el B112, 10/23 usa
    0=Enable y 1=DisEnable para la publicación de datos de mapa. V47 espera a
    que ese permiso esté habilitado antes de consultar el historial 10.5.

    La restauración del valor original al terminar el mapeo o cerrar la app se
    hereda de V41. Las protecciones de V45/V46 se conservan sin cambios.
    """

    PRIVACY_RETRY_SECONDS = 4.0

    def __init__(self):
        self._v47_privacy_worker = False
        self._v47_privacy_ready = False
        self._v47_privacy_phase = None
        self._v47_privacy_before = None
        self._v47_privacy_after = None
        self._v47_privacy_attempts = 0
        self._v47_privacy_successes = 0
        self._v47_privacy_error = None
        self._v47_privacy_last_attempt = 0.0
        super().__init__()

    # -------------------------------------------------------- cliente Cloud/mapa
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV47(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # ------------------------------------------------------- permiso map-privacy
    def _v47_reset_privacy_phase(self, phase):
        self._v47_privacy_phase = int(phase or 0)
        self._v47_privacy_ready = False
        self._v47_privacy_before = None
        self._v47_privacy_after = None
        self._v47_privacy_error = None
        self._v47_privacy_last_attempt = 0.0

    def _v47_prepare_map_privacy_async(self, phase):
        if not self.mapping_active or not self.vacuum or self._v47_privacy_worker:
            return
        phase = int(phase or 0)
        if phase not in (1, 2):
            return

        now = time.monotonic()
        if now - float(self._v47_privacy_last_attempt or 0.0) < self.PRIVACY_RETRY_SECONDS:
            return
        self._v47_privacy_last_attempt = now
        self._v47_privacy_worker = True
        self._v47_privacy_attempts += 1

        try:
            client = self._v40_map_client(self.vacuum, dict(self.settings or {}))
        except Exception as exc:
            self._v47_privacy_worker = False
            self._v47_privacy_error = str(exc).strip() or type(exc).__name__
            return

        def worker():
            try:
                before = client.map_privacy_state()
                ok = bool(client.enable_map_upload_temporarily())
                after = client.map_privacy_state()
                self._post_ui(
                    "v47_privacy_ready",
                    {
                        "phase": phase,
                        "before": before,
                        "after": after,
                        "ok": ok,
                        "temporary": bool(client.privacy_temporarily_enabled),
                        "original": client.privacy_original,
                    },
                )
            except Exception as exc:
                self._post_ui(
                    "v47_privacy_error",
                    {"phase": phase, "error": str(exc).strip() or type(exc).__name__},
                )

        threading.Thread(target=worker, daemon=True).start()

    def _v47_begin_phase(self, phase):
        self._v47_reset_privacy_phase(phase)
        self._v47_prepare_map_privacy_async(phase)

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if getattr(self, "mapping_active", False):
            self._v47_begin_phase(getattr(self, "mapping_phase", 1))
        return result

    def start_interior_mapping(self):
        result = super().start_interior_mapping()
        if getattr(self, "mapping_active", False):
            self._v47_begin_phase(getattr(self, "mapping_phase", 2))
        return result

    # V46 no consulta historial hasta que 10/23 permite publicarlo.
    def _maybe_poll_cloud_position(self):
        if self.mapping_active and self.vacuum:
            phase = int(getattr(self, "mapping_phase", 0) or 0)
            if phase in (1, 2):
                if self._v47_privacy_phase != phase:
                    self._v47_reset_privacy_phase(phase)
                if not self._v47_privacy_ready:
                    self._v47_prepare_map_privacy_async(phase)
                    return
        return super()._maybe_poll_cloud_position()

    # ------------------------------------------------------------- eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v47_privacy_ready":
            self._v47_privacy_worker = False
            info = payload[0] if payload else {}
            phase = int(info.get("phase", 0) or 0)
            self._v47_privacy_before = info.get("before")
            self._v47_privacy_after = info.get("after")
            ok = bool(info.get("ok"))
            current_phase = int(getattr(self, "mapping_phase", 0) or 0)
            if ok and phase == current_phase and getattr(self, "mapping_active", False):
                self._v47_privacy_ready = True
                self._v47_privacy_successes += 1
                self._v47_privacy_error = None
                # La ventana temporal del historial empieza cuando Cloud quedó
                # habilitado, evitando mezclar frames de una fase anterior.
                self._v46_reset_history_phase(phase)
            else:
                self._v47_privacy_ready = False
                if not ok:
                    self._v47_privacy_error = (
                        f"No se pudo habilitar map-uploads 10/23 (antes={info.get('before')!r}, "
                        f"después={info.get('after')!r})."
                    )
            return

        if kind == "v47_privacy_error":
            self._v47_privacy_worker = False
            info = payload[0] if payload else {}
            self._v47_privacy_ready = False
            self._v47_privacy_error = str(info.get("error") or "Error al preparar map-uploads 10/23")
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        original = getattr(client, "privacy_original", None) if client else None
        temporary = bool(getattr(client, "privacy_temporarily_enabled", False)) if client else False
        return (
            "DIAGNÓSTICO V47 ACTIVO · subida Cloud temporal 10/23\n"
            "===================================================\n"
            "regla B112: map-uploads 0=Upload · 1=Do Not Upload\n"
            f"fase preparada: {self._v47_privacy_phase!r} · listo para historial: {self._v47_privacy_ready}\n"
            f"10/23 antes: {self._v47_privacy_before!r} · después: {self._v47_privacy_after!r}\n"
            f"valor original preservado: {original!r} · cambio temporal activo: {temporary}\n"
            f"intentos: {self._v47_privacy_attempts} · éxitos: {self._v47_privacy_successes}\n"
            f"error permiso: {self._v47_privacy_error or '—'}\n"
            f"restauraciones heredadas V41: {int(getattr(self, '_v41_privacy_restore_count', 0) or 0)}\n"
            "seguridad: V47 no reactiva 10/18, 10/15 ni 10/6; V45 sigue controlando uploads por map_id\n"
            "restauración: al terminar/cancelar el mapeo o cerrar la app se repone el valor original\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

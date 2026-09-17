import threading
import time

import app_v40
from xiaomi_e10_map_v41 import XiaomiE10MapV41


class App(app_v40.App):
    """v41: agota rutas de upload, claves y formatos antes de rendirse."""

    CLOUD_FILE_POLL_SECONDS = 1.35
    CLOUD_UPLOAD_INTERVAL_SECONDS = 4.0
    CLOUD_UPLOAD_SETTLE_SECONDS = 0.9

    def __init__(self):
        self._v41_last_mapping_active = False
        self._v41_key_diag = {}
        self._v41_slot_diag = {}
        self._v41_upload_diag = {}
        self._v41_blob_hash = None
        self._v41_blob_hash_changes = 0
        self._v41_winning_decoder = None
        self._v41_decode_attempts = 0
        self._v41_privacy_restore_count = 0
        self._v41_map_error = None
        super().__init__()
        self.after(800, self._v41_mapping_state_watch)

    # ------------------------------------------------------------ cliente mapa
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV41(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v41_capture_client_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is None:
            return
        self._v41_key_diag = dict(getattr(client, "last_key_diagnostics", {}) or {})
        self._v41_slot_diag = dict(getattr(client, "last_slot_diagnostics", {}) or {})
        self._v41_upload_diag = dict(getattr(client, "last_upload_diagnostics", {}) or {})
        self._v41_decode_attempts = int(getattr(client, "decode_attempts", 0) or 0)

    # ---------------------------------------------- privacidad temporal/restore
    def _v41_restore_privacy_async(self):
        client = getattr(self, "_v40_client", None)
        if client is None:
            return

        def worker():
            try:
                restored = client.restore_map_privacy()
                if restored:
                    self._post_ui("v41_privacy_restored")
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _v41_mapping_state_watch(self):
        try:
            active = bool(getattr(self, "mapping_active", False))
            if self._v41_last_mapping_active and not active:
                self._v41_restore_privacy_async()
            self._v41_last_mapping_active = active
            self.after(900, self._v41_mapping_state_watch)
        except Exception:
            pass

    def destroy(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            try:
                client.restore_map_privacy()
            except Exception:
                pass
        return super().destroy()

    # ------------------------------------------------------------- eventos mapa
    def _handle_ui_event(self, kind, payload):
        if kind == "v41_privacy_restored":
            self._v41_privacy_restore_count += 1
            return

        if kind == "cloud_ijai_map_state_v40":
            snapshot = payload[0] if payload else None
            if snapshot is not None:
                self._v41_winning_decoder = getattr(snapshot, "crypto_mode", None)
                self._v41_decode_attempts = int(getattr(snapshot, "decode_attempts", 0) or 0)
                new_hash = getattr(snapshot, "blob_sha256", None)
                if new_hash:
                    if self._v41_blob_hash is not None and new_hash != self._v41_blob_hash:
                        self._v41_blob_hash_changes += 1
                    self._v41_blob_hash = new_hash
                self._v41_map_error = None
            self._v41_capture_client_diag()
            return super()._handle_ui_event(kind, payload)

        if kind == "cloud_ijai_map_error_v40":
            self._v41_map_error = str(payload[0]) if payload else "Error de mapa v41"
            self._v41_capture_client_diag()
            return super()._handle_ui_event(kind, payload)

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _v41_actions_text(info):
        attempts = list((info or {}).get("attempts") or [])
        if not attempts:
            return "—"
        parts = []
        for item in attempts:
            action = item.get("action") or "?"
            label = item.get("label") or ""
            if item.get("ok"):
                out = item.get("out") or {}
                parts.append(f"{action} OK ({label}) out={out!r}")
            else:
                parts.append(f"{action} ERROR ({label}) {item.get('error') or ''}")
        return "\n    ".join(parts)

    @staticmethod
    def _v41_sources(diag, key):
        values = list((diag or {}).get(key) or [])
        return ", ".join(values) if values else "—"

    def _diagnostic_text(self):
        self._v41_capture_client_diag()
        inherited = super()._diagnostic_text()
        key = self._v41_key_diag
        slots = self._v41_slot_diag
        upload = self._v41_upload_diag
        client = getattr(self, "_v40_client", None)
        privacy_original = getattr(client, "privacy_original", None) if client else None
        privacy_temp = bool(getattr(client, "privacy_temporarily_enabled", False)) if client else False
        privacy_now = None
        if client is not None:
            try:
                privacy_now = client.map_privacy_state()
            except Exception:
                pass

        return (
            "DIAGNÓSTICO V41 ACTIVO · búsqueda exhaustiva E10\n"
            "=================================================\n"
            "upload realtime: 10/18 + 10/15(type=0) + 10/6(type=0); por map-id sólo si id>0\n"
            f"map_id detectado: {upload.get('map_id')!r} · mapas listados: {upload.get('map_list_count', 0)}\n"
            f"map-privacy original: {privacy_original!r} · actual: {privacy_now!r} · habilitada temporalmente: {privacy_temp}\n"
            f"restauraciones de privacidad: {self._v41_privacy_restore_count}\n"
            f"acciones de subida:\n    {self._v41_actions_text(upload)}\n"
            f"candidatos wifi_sn: {key.get('wifi_count', 0)} · fuentes: {self._v41_sources(key, 'wifi_sources')}\n"
            f"candidatos MAC: {key.get('mac_count', 0)} · fuentes: {self._v41_sources(key, 'mac_sources')}\n"
            f"candidatos owner: {key.get('owner_count', 0)} · fuentes: {self._v41_sources(key, 'owner_sources')}\n"
            f"candidatos DID: {key.get('did_count', 0)} · fuentes: {self._v41_sources(key, 'did_sources')}\n"
            f"claves derivadas únicas: {key.get('derived_key_count', 0)}\n"
            f"slots Cloud (HTTP/bytes/hash12/endpoint): {slots!r}\n"
            f"intentos de decodificación/validación: {self._v41_decode_attempts}\n"
            f"decoder ganador: {self._v41_winning_decoder or '—'}\n"
            f"hash blob actual: {(self._v41_blob_hash or '—')[:16]} · cambios de blob: {self._v41_blob_hash_changes}\n"
            f"último error exhaustivo: {self._v41_map_error or '—'}\n"
            "validación: sólo se acepta una variante si produce RobotMap protobuf coherente\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

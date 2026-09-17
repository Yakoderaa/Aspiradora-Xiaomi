import app_v42
from xiaomi_e10_map_v43 import XiaomiE10MapV43


class App(app_v42.App):
    """v43: ruta Xiaomi-JSON específica del E10, con IJAI como fallback."""

    def __init__(self):
        self._v43_xiaomi_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV43(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v43_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v43_xiaomi_diag = dict(getattr(client, "last_xiaomi_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v43_capture_diag()
        return result

    @staticmethod
    def _v40_detect_scale(snapshot):
        # Xiaomi JSON expresa resolución/origen/posición en la misma base métrica
        # del mapa y la resolución se define en mm/píxel. Convertimos a metros.
        if str(getattr(snapshot, "crypto_mode", "")).startswith("Xiaomi JSON"):
            return 0.001
        return app_v42.app_v41.app_v40.App._v40_detect_scale(snapshot)

    def _diagnostic_text(self):
        self._v43_capture_diag()
        diag = self._v43_xiaomi_diag
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V43 ACTIVO · Xiaomi JSON exacto para B112\n"
            "====================================================\n"
            "ruta primaria: ciphertext -> hex STR -> AES-CBC Xiaomi -> zlib -> JSON\n"
            "modelo corto: se prueba primero MODEL[-16:] para obtener clave AES válida\n"
            f"ruta elegida: {diag.get('route') or '—'}\n"
            f"intentos Xiaomi JSON: {diag.get('attempts', 0)}\n"
            f"descifrados correctos: {diag.get('decrypt_ok', 0)}\n"
            f"JSON válidos: {diag.get('json_ok', 0)}\n"
            f"renderer correctos: {diag.get('parse_ok', 0)}\n"
            f"mapa Xiaomi validado: {bool(diag.get('winner', False))}\n"
            f"clave modelo ganadora: {diag.get('winner_model_key') or '—'}\n"
            f"variante blob ganadora: {diag.get('winner_blob_variant') or '—'}\n"
            f"hash12 descifrado: {diag.get('decrypted_sha12') or '—'} · bytes: {diag.get('decrypted_bytes', 0)}\n"
            f"map_id JSON: {diag.get('map_id')!r} · resolution: {diag.get('resolution')!r}\n"
            f"position JSON cruda: {diag.get('robot')!r}\n"
            f"base JSON cruda: {diag.get('base')!r}\n"
            f"path JSON: {diag.get('path_count', 0)} puntos · imagen: {bool(diag.get('image', False))}\n"
            f"campos JSON detectados: {diag.get('payload_keys') or []}\n"
            f"último error decrypt: {diag.get('last_decrypt_error') or '—'}\n"
            f"último error JSON: {diag.get('last_json_error') or '—'}\n"
            f"último error renderer: {diag.get('last_parse_error') or '—'}\n"
            f"fallback IJAI: {diag.get('fallback_ijai') or ('no necesario' if diag.get('winner') else '—')}\n"
            "escala Xiaomi JSON: milímetros -> metros (0.001)\n"
            "nota: V43 conserva V42/V41 automáticamente si el blob no fuese Xiaomi JSON\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

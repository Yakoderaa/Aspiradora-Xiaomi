import app_v41
from xiaomi_e10_map_v42 import XiaomiE10MapV42


class App(app_v41.App):
    """v42: corrige la capa de validación/parseo del blob IJAI del E10."""

    def __init__(self):
        self._v42_native_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV42(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v42_capture_native_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v42_native_diag = dict(getattr(client, "last_native_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v42_capture_native_diag()
        return result

    @staticmethod
    def _v42_source_text(sources):
        if not isinstance(sources, dict) or not sources:
            return "—"
        return (
            f"wifi={sources.get('wifi_source') or '—'} · "
            f"owner={sources.get('owner_source') or '—'} · "
            f"did={sources.get('did_source') or '—'} · "
            f"mac={sources.get('mac_source') or '—'}"
        )

    def _diagnostic_text(self):
        self._v42_capture_native_diag()
        diag = self._v42_native_diag
        inherited = super()._diagnostic_text()
        winner = bool(diag.get("winner"))
        return (
            "DIAGNÓSTICO V42 ACTIVO · IJAI binario nativo\n"
            "===============================================\n"
            "corrección V42: unpack_map() + parse() del paquete IJAI; NO validación protobuf\n"
            f"wifi_sn estrictos (16–24, uppercase): {diag.get('strict_wifi_count', 0)}\n"
            f"intentos parser nativo: {diag.get('attempts', 0)}\n"
            f"unpack_map correctos: {diag.get('unpack_ok', 0)}\n"
            f"parse correctos: {diag.get('parse_ok', 0)}\n"
            f"mapa nativo validado: {winner}\n"
            f"variante blob ganadora: {diag.get('winner_blob_variant') or '—'}\n"
            f"fuentes ganadoras: {self._v42_source_text(diag.get('winner_sources'))}\n"
            f"hash12 descifrado: {diag.get('unpacked_sha12') or '—'} · bytes: {diag.get('decrypted_bytes', 0)}\n"
            f"vacuum_position nativa: {diag.get('robot')!r}\n"
            f"charger nativa: {diag.get('base')!r}\n"
            f"path nativo: {diag.get('path_count', 0)} puntos · imagen: {bool(diag.get('image', False))}\n"
            f"fallback V41: {diag.get('legacy_fallback') or ('no necesario' if winner else '—')}\n"
            "seguridad diagnóstico: URLs FDS firmadas se omiten\n"
            "nota: las líneas V40/V41 heredadas que dicen 'protobuf' son históricas; V42 usa el binario real del parser\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

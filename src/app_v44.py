import app_v43
from xiaomi_e10_map_v44 import XiaomiE10MapV44


class App(app_v43.App):
    """v44: acepta el wifi_sn real de Xiaomi/IJAI aunque contenga '/'."""

    def __init__(self):
        self._v44_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV44(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v44_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v44_diag = dict(getattr(client, "last_v44_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v44_capture_diag()
        return result

    def _diagnostic_text(self):
        self._v44_capture_diag()
        diag = self._v44_diag
        inherited = super()._diagnostic_text()
        shapes = diag.get("wifi_shapes") or []
        shapes_text = ", ".join(
            f"{x.get('source')}[len={x.get('length')}, slash={x.get('slash')}, sha8={x.get('sha8')}]"
            for x in shapes
        ) or "—"
        v42 = diag.get("v42_native") or {}
        slots = diag.get("slots") or {}
        return (
            "DIAGNÓSTICO V44 ACTIVO · wifi_sn real IJAI\n"
            "===========================================\n"
            "hallazgo aplicado: serial Wi-Fi flexible 10–25 caracteres; '/' permitido y priorizado\n"
            "familia B112: IJAI sigue disponible con unpack_map() oficial; Xiaomi JSON queda como fallback\n"
            f"ruta: {diag.get('route') or '—'}\n"
            f"seriales estrictos: {diag.get('strict_wifi_count', 0)} · con '/': {diag.get('slash_wifi_count', 0)}\n"
            f"formas serial (sin mostrar valores): {shapes_text}\n"
            f"fuentes owner: {diag.get('owner_sources') or []}\n"
            f"fuentes DID: {diag.get('did_sources') or []}\n"
            f"fuentes MAC: {diag.get('mac_sources') or []}\n"
            f"mapa abierto: {bool(diag.get('success', False))}\n"
            f"decoder ganador: {diag.get('crypto_mode') or '—'}\n"
            f"wifi ganador: {diag.get('winner_wifi_source') or '—'} · longitud {diag.get('winner_wifi_length', 0)}\n"
            f"owner ganador: {diag.get('winner_owner_source') or '—'}\n"
            f"DID ganador: {diag.get('winner_did_source') or '—'}\n"
            f"MAC ganadora: {diag.get('winner_mac_source') or '—'}\n"
            f"blob: {diag.get('raw_bytes', 0)} bytes · sha12 {diag.get('blob_sha12') or '—'}\n"
            f"prefijo cifrado hex: {diag.get('raw_prefix_hex') or '—'}\n"
            f"descifrado: {diag.get('decrypted_bytes', 0)} bytes\n"
            f"V42 unpack correctos: {v42.get('unpack_ok', 0)} · protobuf correctos: {v42.get('protobuf_ok', 0)}\n"
            f"slots finales: {slots}\n"
            f"error V44: {diag.get('error') or '—'}\n"
            "seguridad: serial/UID/DID/MAC reales no se imprimen; sólo fuente/longitud/hash corto\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

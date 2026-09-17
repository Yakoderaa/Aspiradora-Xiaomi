import app_v52
from xiaomi_e10_map_v53 import XiaomiE10MapV53


class App(app_v52.App):
    """V53: fingerprint del blob clásico y dos derivaciones IJAI conocidas."""

    def __init__(self):
        self._v53_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV53(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v53_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v53_diag = dict(getattr(client, "last_v53_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v53_capture_diag()
        return result

    @staticmethod
    def _source_text(values):
        return ", ".join(str(value) for value in list(values or [])[:12]) or "—"

    @staticmethod
    def _mode_text(info):
        data = dict(info or {})
        return (
            f"intentos={int(data.get('attempts', 0) or 0)} · "
            f"padding={int(data.get('padding_ok', 0) or 0)} · "
            f"hex={int(data.get('hex_ok', 0) or 0)} · "
            f"json={int(data.get('json_ok', 0) or 0)} · "
            f"protobuf={int(data.get('protobuf_ok', 0) or 0)}"
        )

    def _diagnostic_text(self):
        self._v53_capture_diag()
        diag = dict(self._v53_diag or {})
        fingerprint = dict(diag.get("fingerprint") or {})
        runtime = dict(diag.get("parser_runtime") or {})
        material = dict(diag.get("key_material") or {})
        trial = dict(diag.get("trial") or {})
        modes = dict(trial.get("modes") or {})
        inherited = super()._diagnostic_text()

        return (
            "DIAGNÓSTICO V53 ACTIVO · fingerprint del blob clásico\n"
            "======================================================\n"
            f"ruta: {diag.get('route') or '—'} · éxito: {bool(diag.get('success'))} · fallback V51: {bool(diag.get('fallback_v51'))}\n"
            f"parser IJAI runtime: versión={runtime.get('version') or '—'} · b112 usa MD5 hex según paquete: {runtime.get('b112_hex_mode')!r}\n"
            f"slot 0 clásico: HTTP {diag.get('http')!r} · endpoint={diag.get('endpoint') or '—'} · "
            f"bytes={int(fingerprint.get('bytes', 0) or 0)} · sha12={fingerprint.get('sha12') or '—'}\n"
            f"fingerprint: block16={bool(fingerprint.get('block16'))} · entropía={fingerprint.get('entropy')!r} bits/B · "
            f"ASCII={fingerprint.get('ascii_ratio')!r} · magic={fingerprint.get('magic') or '—'}\n"
            f"bloques 16B: total={int(fingerprint.get('blocks', 0) or 0)} · únicos={int(fingerprint.get('unique_blocks', 0) or 0)} · "
            f"repetidos={int(fingerprint.get('repeated_blocks', 0) or 0)} · máximo repetición={int(fingerprint.get('max_block_repeat', 0) or 0)}\n"
            f"prefijo cifrado 16B: {fingerprint.get('prefix_hex') or '—'}\n"
            f"sin descifrar: json={bool(fingerprint.get('raw_json'))} · zlib={bool(fingerprint.get('raw_zlib'))} · "
            f"protobuf_score={fingerprint.get('raw_protobuf_score')!r}\n"
            f"material clave: wifi={int(material.get('wifi_count', 0) or 0)} · owner={int(material.get('owner_count', 0) or 0)} · "
            f"DID={int(material.get('did_count', 0) or 0)} · MAC={int(material.get('mac_count', 0) or 0)}\n"
            f"fuentes wifi: {self._source_text(material.get('wifi_sources'))}\n"
            f"fuentes owner: {self._source_text(material.get('owner_sources'))}\n"
            f"IJAI central16 ASCII: {self._mode_text(modes.get('md5-central16-ascii'))}\n"
            f"IJAI MD5 hex completo: {self._mode_text(modes.get('md5-full-hex-bytes'))}\n"
            f"variantes ciphertext: {self._source_text(trial.get('cipher_variants'))}\n"
            f"ganador: {trial.get('winner_mode') or '—'} · variante={trial.get('winner_cipher_variant') or '—'} · "
            f"payload={trial.get('winner_payload_label') or '—'} · score={trial.get('winner_score')!r}\n"
            f"error V53: {diag.get('error') or '—'} · fallback error: {diag.get('fallback_error') or '—'}\n"
            "seguridad: V53 sólo descarga/analiza el slot 0 clásico; no ejecuta acciones ni modifica propiedades del robot\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import app_v53
from xiaomi_e10_map_v54 import XiaomiE10MapV54


class App(app_v53.App):
    """V54: identifica el payload real después del candidato AES+hex de V53."""

    def __init__(self):
        self._v54_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV54(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v54_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v54_diag = dict(getattr(client, "last_v54_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v54_capture_diag()
        return result

    @staticmethod
    def _list_text(values):
        return ", ".join(str(value) for value in list(values or [])[:12]) or "—"

    @staticmethod
    def _compression_text(items):
        parts = []
        for item in list(items or []):
            name = item.get("name") or "?"
            if not item.get("ok"):
                parts.append(f"{name}=NO({item.get('error') or 'error'})")
                continue
            wire = dict(item.get("wire") or {})
            parts.append(
                f"{name}=OK bytes={int(item.get('bytes', 0) or 0)} "
                f"magic={item.get('magic') or '—'} "
                f"RobotMap={item.get('robotmap_score')!r} "
                f"wire={bool(wire.get('valid'))}"
            )
        return " · ".join(parts) or "—"

    @staticmethod
    def _candidate_summary(candidate):
        c = dict(candidate or {})
        src = dict(c.get("sources") or {})
        post = dict(c.get("posthex") or {})
        wire = dict(post.get("wire") or {})
        return (
            f"modo={c.get('mode') or '—'} · variante={c.get('cipher_variant') or '—'} · "
            f"wifi={src.get('wifi_source') or '—'}(len={int(src.get('wifi_len', 0) or 0)}) · "
            f"owner={src.get('owner_source') or '—'} · DID={src.get('did_source') or '—'} · MAC={src.get('mac_source') or '—'}\n"
            f"    plaintext hex: {int(c.get('plain_bytes', 0) or 0)} B · sha12={c.get('plain_sha12') or '—'}\n"
            f"    post-hex: {int(post.get('bytes', 0) or 0)} B · sha12={post.get('sha12') or '—'} · "
            f"magic={post.get('magic') or '—'} · entropía={post.get('entropy')!r} · ASCII={post.get('ascii_ratio')!r}\n"
            f"    prefijo={post.get('prefix_hex') or '—'} · sufijo={post.get('suffix_hex') or '—'}\n"
            f"    bytes dominantes: {App._list_text(post.get('top_bytes'))} · "
            f"00={post.get('zero_ratio')!r} · ff={post.get('ff_ratio')!r} · 80={post.get('byte80_ratio')!r}\n"
            f"    bloques post-hex: total={int(post.get('blocks', 0) or 0)} · únicos={int(post.get('unique_blocks', 0) or 0)} · "
            f"repetidos={int(post.get('repeated_blocks', 0) or 0)} · max={int(post.get('max_block_repeat', 0) or 0)}\n"
            f"    JSON={bool(post.get('json'))} · RobotMap={post.get('robotmap_score')!r} · "
            f"protobuf genérico={bool(wire.get('valid'))} · campos={int(wire.get('fields', 0) or 0)} · "
            f"consumido={wire.get('consumed_ratio')!r}\n"
            f"    field numbers: {App._list_text(wire.get('field_numbers'))} · wire types: {App._list_text(wire.get('wire_types'))}\n"
            f"    compresión: {App._compression_text(c.get('compression'))}"
        )

    def _diagnostic_text(self):
        self._v54_capture_diag()
        diag = dict(self._v54_diag or {})
        probe = dict(diag.get("probe") or {})
        candidates = list(probe.get("candidates") or [])
        inherited = super()._diagnostic_text()

        lines = [
            "DIAGNÓSTICO V54 ACTIVO · candidato post-hex del blob clásico",
            "============================================================",
            f"ruta: {diag.get('route') or '—'} · fallback V53: {bool(diag.get('fallback_v53'))}",
            f"slot 0: HTTP {diag.get('http')!r} · endpoint={diag.get('endpoint') or '—'} · "
            f"bytes={int(diag.get('blob_bytes', 0) or 0)} · sha12={diag.get('blob_sha12') or '—'}",
            f"frescura: lecturas={int(diag.get('reads', 0) or 0)} · hashes únicos={int(diag.get('unique_hashes', 0) or 0)} · "
            f"cambios de hash={int(diag.get('hash_changes', 0) or 0)}",
            f"intentos por modo: {probe.get('attempts') or {}}",
            f"candidatos padding+hex: {int(probe.get('candidate_count', 0) or 0)} · "
            f"variantes ciphertext: {self._list_text(probe.get('cipher_variants'))}",
        ]

        if candidates:
            for index, candidate in enumerate(candidates[:4], start=1):
                lines.append(f"candidato #{index}: {self._candidate_summary(candidate)}")
        else:
            lines.append("candidatos: —")

        lines.extend([
            f"error V54: {diag.get('error') or '—'} · fallback error: {diag.get('fallback_error') or '—'}",
            "seguridad: V54 sólo lee/analiza el archivo Cloud; no ejecuta acciones, no modifica propiedades y no mueve el robot por una muestra parcial",
            "",
        ])
        return "\n".join(lines) + "\n" + inherited


if __name__ == "__main__":
    app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

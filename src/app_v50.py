import app_v49
from xiaomi_e10_map_v50 import XiaomiE10MapV50


class App(app_v49.App):
    """V50: captura la respuesta directa de get_interim_file_url_pro."""

    def __init__(self):
        self._v50_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV50(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v50_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v50_diag = dict(getattr(client, "last_v50_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v50_capture_diag()
        return result

    @staticmethod
    def _v50_candidate_text(candidates):
        parts = []
        for item in list(candidates or [])[:8]:
            if not isinstance(item, dict):
                continue
            parts.append(
                f"{item.get('label')}: {item.get('bytes', 0)}B · "
                f"sha12={item.get('sha12') or '—'} · {item.get('magic') or '—'} · "
                f"block16={bool(item.get('block16'))}"
            )
        return " | ".join(parts) or "—"

    @staticmethod
    def _v50_trials_text(trials):
        parts = []
        for item in list(trials or [])[:8]:
            if not isinstance(item, dict):
                continue
            if item.get("decoder") == "ijai":
                parts.append(
                    f"{item.get('candidate')}→IJAI[a={item.get('attempts', 0)},"
                    f"u={item.get('unpack_ok', 0)},p={item.get('protobuf_ok', 0)}]"
                )
            else:
                parts.append(
                    f"{item.get('candidate')}→Xiaomi[a={item.get('attempts', 0)},"
                    f"d={item.get('decrypt_ok', 0)},j={item.get('json_ok', 0)}]"
                )
        return " | ".join(parts) or "—"

    def _diagnostic_text(self):
        self._v50_capture_diag()
        diag = self._v50_diag
        inherited = super()._diagnostic_text()
        slots = diag.get("pro_slots") or {}
        slot_lines = []
        for slot in ("0", "1"):
            info = slots.get(slot) or {}
            slot_lines.append(
                f"_pro slot {slot}: ok={bool(info.get('ok'))} · response={info.get('response_kind') or '—'} · "
                f"parsed={info.get('parsed_kind') or '—'} · version={info.get('version')} · "
                f"url={bool(info.get('url_present'))} · candidatos={info.get('candidate_count', 0)} · "
                f"error={info.get('error') or '—'}"
            )
            slot_lines.append("    candidatos: " + self._v50_candidate_text(info.get("candidates")))
            slot_lines.append("    decoders: " + self._v50_trials_text(info.get("decoder_trials")))

        return (
            "DIAGNÓSTICO V50 ACTIVO · payload directo get_interim_file_url_pro\n"
            "===============================================================\n"
            f"ruta: {diag.get('route') or '—'}\n"
            f"éxito directo: {bool(diag.get('success'))} · ganador slot: {diag.get('winner_slot') or '—'} · "
            f"decoder: {diag.get('winner_decoder') or '—'} · candidato: {diag.get('winner_candidate') or '—'}\n"
            f"IJAI directo: intentos={diag.get('native_attempts', 0)} · unpack={diag.get('native_unpack_ok', 0)} · "
            f"protobuf={diag.get('native_protobuf_ok', 0)}\n"
            f"Xiaomi directo: intentos={diag.get('xiaomi_attempts', 0)} · decrypt={diag.get('xiaomi_decrypt_ok', 0)} · "
            f"json={diag.get('xiaomi_json_ok', 0)}\n"
            f"fallback clásico: {bool(diag.get('fallback_classic'))} · resultado={diag.get('fallback_result') or '—'}\n"
            + "\n".join(slot_lines)
            + "\nseguridad: no se muestran payloads, URLs firmadas, seriales, UID, DID ni MAC; sólo forma/tamaño/hash corto\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

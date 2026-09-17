import app_v50
from xiaomi_e10_map_v51 import XiaomiE10MapV51


class App(app_v50.App):
    """V51: restaura la base segura V47/V45 y revela el esquema _pro."""

    def __init__(self):
        self._v51_diag = {}
        super().__init__()

    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV51(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v51_capture_diag(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v51_diag = dict(getattr(client, "last_v51_diagnostics", {}) or {})

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v51_capture_diag()
        return result

    @staticmethod
    def _schema_text(items):
        values = [str(item) for item in list(items or [])[:18] if item]
        return " | ".join(values) or "—"

    @staticmethod
    def _meta_text(items):
        parts = []
        for item in list(items or [])[:8]:
            if not isinstance(item, dict):
                continue
            parts.append(
                f"{item.get('label')}: {item.get('bytes', 0)}B · "
                f"sha12={item.get('sha12') or '—'} · {item.get('magic') or '—'} · "
                f"block16={bool(item.get('block16'))}"
            )
        return " | ".join(parts) or "—"

    @staticmethod
    def _download_text(items):
        parts = []
        for item in list(items or [])[:6]:
            if not isinstance(item, dict):
                continue
            if item.get("error"):
                parts.append(f"{item.get('path') or '?'}→error={item.get('error')}")
            else:
                parts.append(
                    f"{item.get('path') or '?'}→HTTP {item.get('http')} · "
                    f"{item.get('bytes', 0)}B · sha12={item.get('sha12') or '—'} · "
                    f"{item.get('magic') or '—'}"
                )
        return " | ".join(parts) or "—"

    @staticmethod
    def _trial_text(items):
        parts = []
        for item in list(items or [])[:8]:
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
        self._v51_capture_diag()
        diag = self._v51_diag

        # Saltamos el bloque V50 porque V51 reemplaza ese cliente; conservamos
        # V49 y todo el diagnóstico anterior para comparar comportamiento.
        inherited = app_v50.app_v49.App._diagnostic_text(self)

        slots = diag.get("pro_slots") or {}
        lines = []
        for slot in ("0", "1"):
            info = slots.get(slot) or {}
            lines.append(
                f"_pro slot {slot}: transporte={bool(info.get('transport_ok'))} · "
                f"app_ok={bool(info.get('application_ok'))} · code={info.get('app_code')} · "
                f"response={info.get('response_kind') or '—'} · parsed={info.get('parsed_kind') or '—'} · "
                f"result={info.get('result_kind') or '—'} · URLs={info.get('url_count', 0)} · "
                f"candidatos={info.get('candidate_count_after_download', info.get('candidate_count', 0))}"
            )
            lines.append(
                "    claves top: " + (", ".join(info.get("top_keys") or []) or "—")
                + " · result: " + (", ".join(info.get("result_keys") or []) or "—")
            )
            lines.append(f"    mensaje saneado: {info.get('message') or '—'} · error: {info.get('error') or '—'}")
            lines.append("    esquema: " + self._schema_text(info.get("schema")))
            lines.append("    rutas URL: " + (", ".join(info.get("url_paths") or []) or "—"))
            lines.append("    descargas: " + self._download_text(info.get("downloads")))
            lines.append("    candidatos: " + self._meta_text(info.get("candidate_meta_after_download") or info.get("candidates")))
            lines.append("    decoders: " + self._trial_text(info.get("decoder_trials")))

        return (
            "DIAGNÓSTICO V51 ACTIVO · _pro profundo + restauración de seguridad\n"
            "================================================================\n"
            f"ruta: {diag.get('route') or '—'}\n"
            f"base segura: {diag.get('safe_base') or 'V47->V45->V44'} · "
            f"10/18,10/15,10/6 bloqueados: {bool(diag.get('unsafe_actions_blocked', True))}\n"
            f"éxito _pro: {bool(diag.get('success'))} · ganador slot: {diag.get('winner_slot') or '—'} · "
            f"decoder: {diag.get('winner_decoder') or '—'} · candidato: {diag.get('winner_candidate') or '—'}\n"
            f"IJAI: intentos={diag.get('native_attempts', 0)} · unpack={diag.get('native_unpack_ok', 0)} · "
            f"protobuf={diag.get('native_protobuf_ok', 0)}\n"
            f"Xiaomi: intentos={diag.get('xiaomi_attempts', 0)} · decrypt={diag.get('xiaomi_decrypt_ok', 0)} · "
            f"json={diag.get('xiaomi_json_ok', 0)}\n"
            f"fallback clásico seguro: {bool(diag.get('fallback_classic'))} · "
            f"resultado={diag.get('fallback_result') or '—'}\n"
            + "\n".join(lines)
            + "\nseguridad: URLs y payloads nunca se imprimen; claves muestran sólo nombres/tipos/tamaños. "
              "La cadena V47/V45 impide reactivar uploads no documentados.\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

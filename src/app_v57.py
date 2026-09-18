import threading
import time

import app_v56
from xiaomi_e10_map_v57 import XiaomiE10MapV57


class App(app_v56.App):
    """V57: mapa realtime por eventos + mapa final por clean-end/record-map-url."""

    POST_CLEAN_SECONDS = 180.0
    POST_CLEAN_POLL_SECONDS = 4.0

    def __init__(self):
        self._v57_diag = {}
        self._v57_post_clean_until = 0.0
        super().__init__()

    # -------------------------------------------------------- cliente Cloud
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV57(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # --------------------------------------------------------- polling Cloud
    def _v38_maybe_poll_map_file(self):
        """Sondea durante la limpieza y 3 min después para capturar clean-end."""
        if not self.vacuum:
            return
        if not self._cloud_session_ready() or self._v38_map_worker:
            return

        now = time.monotonic()
        active = bool(
            self.mapping_active
            or getattr(self, "_last_robot_status", None) in (3, 5, 6, 7)
        )
        if active:
            self._v57_post_clean_until = max(
                float(self._v57_post_clean_until or 0.0),
                now + self.POST_CLEAN_SECONDS,
            )
        post_window = now < float(self._v57_post_clean_until or 0.0)
        if not active and not post_window:
            return

        interval = (
            float(self.CLOUD_FILE_POLL_SECONDS)
            if active
            else float(self.POST_CLEAN_POLL_SECONDS)
        )
        if now - float(self._v38_map_last_at or 0.0) < interval:
            return

        self._v38_map_last_at = now
        self._v38_map_worker = True
        vacuum = self.vacuum
        settings = dict(self.settings or {})

        request_upload = bool(
            active
            and now - float(self._v40_last_upload_at or 0.0)
            >= self.CLOUD_UPLOAD_INTERVAL_SECONDS
        )
        if request_upload:
            self._v40_last_upload_at = now

        def worker():
            upload_info = None
            try:
                client = self._v40_map_client(vacuum, settings)
                if request_upload:
                    upload_info = client.request_fresh_upload()
                snapshot = client.load()
                self._post_ui("cloud_ijai_map_state_v40", snapshot, upload_info)
            except Exception as exc:
                self._post_ui(
                    "cloud_ijai_map_error_v40",
                    str(exc).strip() or "No se pudo leer el mapa del E10.",
                    upload_info,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ eventos UI
    def _handle_ui_event(self, kind, payload):
        snapshot = payload[0] if kind == "cloud_ijai_map_state_v40" and payload else None
        result = super()._handle_ui_event(kind, payload)

        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            self._v57_diag = dict(
                getattr(client, "last_v57_diagnostics", {}) or {}
            ) if client else {}

        if kind == "cloud_ijai_map_state_v40" and snapshot is not None:
            # Si V57 rechazó el falso grid V56, borra de inmediato cualquier
            # contorno persistido por la versión anterior.
            if (
                getattr(snapshot, "parser_error", None)
                == "V57: grid rechazado por incoherencia espacial"
            ):
                self._v56_grid_cells = []
                self._v56_grid_walls = []
                if self.local_map:
                    self.local_map.set_mapped_walls([])
                try:
                    self.map_status_label.configure(
                        text="Esperando mapa real de Xiaomi · grid falso descartado"
                    )
                    self.mapping_steps_info.configure(
                        text="V57: sin cuadrados sintéticos · buscando realtime/global-push o clean-end"
                    )
                except Exception:
                    pass
                self._render_maps()
            else:
                diag = dict(self._v57_diag or {})
                source = str(diag.get("source") or "")
                if source == "record-map-url":
                    try:
                        self.map_status_label.configure(
                            text="Mapa final Xiaomi recuperado desde el registro de limpieza"
                        )
                        self.mapping_steps_info.configure(
                            text="Fuente: clean-end 7/1 · record-map-url"
                        )
                    except Exception:
                        pass
        return result

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _query_summary(items):
        parts = []
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            parts.append(
                f"{item.get('label') or '?'}="
                + (
                    f"OK({int(item.get('records', 0) or 0)})"
                    if item.get("ok")
                    else f"ERR({item.get('error') or 'error'})"
                )
            )
        return " · ".join(parts) or "—"

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v57_diag = dict(
                getattr(client, "last_v57_diagnostics", {}) or {}
            )
        diag = dict(self._v57_diag or {})
        record = dict(diag.get("record_map") or {})
        hist = dict(record.get("history") or {})
        live = dict(diag.get("live_refresh") or {})
        metrics = dict(diag.get("live_grid_metrics") or {})
        inherited = super()._diagnostic_text()

        events = list(live.get("events") or [])
        event_text = ", ".join(
            f"{e.get('key')}@{int(float(e.get('time') or 0))}"
            for e in events[:8]
        ) or "—"

        lines = [
            "DIAGNÓSTICO V57 ACTIVO · mapa real sin cuadrados falsos",
            "========================================================",
            f"ruta elegida: {diag.get('route') or '—'} · éxito={bool(diag.get('success'))} · fuente={diag.get('source') or '—'}",
            "realtime: acciones oficiales + espera de propagación Cloud + eventos 10.2/10.4/10.6",
            f"hash realtime: {live.get('baseline_hash') or '—'} → {live.get('hash_after') or '—'} · "
            f"cambió={bool(live.get('changed'))} · ganador={live.get('winner') or '—'}",
            f"eventos realtime vistos: {event_text}",
            "mapa final: event 7/1 clean-end · piid 30 record-map-url",
            f"clean-end encontrado: {bool(record.get('found'))} · candidatos={int(hist.get('candidate_count', 0) or 0)} · "
            f"descarga={int(record.get('download_bytes', 0) or 0)} B · sha12={record.get('download_sha12') or '—'}",
            f"resolver record-map-url: {record.get('reference_kind') or '—'} · endpoint={record.get('resolve_endpoint') or '—'} · "
            f"éxito={bool(record.get('success'))}",
            f"consultas 7.1: {self._query_summary(hist.get('queries'))} · device-log={hist.get('device_log') or {}}",
            f"decoders mapa final: {record.get('decoders') or []}",
            f"validación grid V56: válido={bool(metrics.get('valid'))} · nonzero={int(metrics.get('nonzero', 0) or 0)} · "
            f"componentes={int(metrics.get('components', 0) or 0)} · mayor={int(metrics.get('largest', 0) or 0)} · "
            f"ratio mayor={metrics.get('largest_ratio')!r} · adyacencia={metrics.get('adjacency_ratio')!r}",
            f"ventana post-limpieza activa: {time.monotonic() < float(self._v57_post_clean_until or 0.0)}",
            "regla visual: un grid incoherente nunca se dibuja ni se persiste; se prefiere mapa real realtime/final",
            "",
        ]
        return "\n".join(lines) + "\n" + inherited


if __name__ == "__main__":
    app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

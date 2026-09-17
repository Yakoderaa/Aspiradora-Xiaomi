import threading
import time

import app_v48
from xiaomi_cloud_history_v49 import XiaomiCloudHistoryV49


class App(app_v48.App):
    """V49: progreso en vivo y timeouts para la sonda Cloud V48."""

    def __init__(self):
        self._v49_probe_current = None
        self._v49_probe_completed = 0
        self._v49_probe_planned = 20
        self._v49_probe_timeouts = 0
        self._v49_probe_last_duration = None
        self._v49_probe_elapsed = 0.0
        self._v49_probe_aborted_reason = None
        super().__init__()

    def _v48_reset_probe(self):
        super()._v48_reset_probe()
        self._v49_probe_current = None
        self._v49_probe_completed = 0
        self._v49_probe_planned = 20
        self._v49_probe_timeouts = 0
        self._v49_probe_last_duration = None
        self._v49_probe_elapsed = 0.0
        self._v49_probe_aborted_reason = None

    def _v48_start_probe(self):
        if self._v48_probe_worker or self._v48_probe_done:
            return
        if not self.mapping_active or not self.vacuum or not self._v47_privacy_ready:
            return
        if self._v46_history_worker:
            return

        self._v48_probe_worker = True
        self._v48_probe_attempts += 1
        settings = dict(self.settings or {})
        started_at = float(self._v46_phase_started_at or time.time())

        def progress(snapshot):
            self._post_ui("cloud_history_probe_progress_v49", snapshot)

        def worker():
            try:
                result = XiaomiCloudHistoryV49(settings).read_probe(
                    started_at,
                    progress_callback=progress,
                )
                self._post_ui("cloud_history_probe_v48", result)
            except Exception as exc:
                self._post_ui(
                    "cloud_history_probe_error_v48",
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_history_probe_progress_v49":
            item = payload[0] if payload else {}
            if not isinstance(item, dict):
                return
            self._v49_probe_current = item.get("current")
            self._v49_probe_completed = int(item.get("completed", 0) or 0)
            self._v49_probe_planned = int(item.get("planned", 20) or 20)
            self._v49_probe_timeouts = int(item.get("timeouts", 0) or 0)
            self._v49_probe_last_duration = item.get("last_duration")
            self._v49_probe_elapsed = float(item.get("elapsed", 0.0) or 0.0)

            # V48 sólo actualizaba estos datos al final. En V49 se reflejan en
            # vivo para que F12 muestre resultados parciales.
            self._v48_probe_plans = self._v49_probe_completed
            self._v48_probe_total_records = int(item.get("total_records", 0) or 0)
            self._v48_probe_any_history = bool(item.get("any_history"))
            partial_queries = item.get("queries")
            if isinstance(partial_queries, dict):
                self._v48_probe_queries = dict(partial_queries)
            return

        if kind == "cloud_history_probe_v48":
            result = payload[0] if payload else {}
            inherited = super()._handle_ui_event(kind, payload)
            if isinstance(result, dict):
                self._v49_probe_current = None
                self._v49_probe_completed = int(result.get("plans", 0) or 0)
                self._v49_probe_planned = int(result.get("planned", 20) or 20)
                self._v49_probe_timeouts = int(result.get("timeouts", 0) or 0)
                self._v49_probe_elapsed = float(result.get("elapsed", 0.0) or 0.0)
                self._v49_probe_aborted_reason = result.get("aborted_reason")
            return inherited

        if kind == "cloud_history_probe_error_v48":
            self._v49_probe_current = None
            return super()._handle_ui_event(kind, payload)

        return super()._handle_ui_event(kind, payload)

    @staticmethod
    def _fmt_seconds(value):
        try:
            return f"{float(value):.2f}s"
        except Exception:
            return "—"

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        current = self._v49_probe_current or "—"
        last_duration = self._fmt_seconds(self._v49_probe_last_duration)
        elapsed = self._fmt_seconds(self._v49_probe_elapsed)
        return (
            "DIAGNÓSTICO V49 ACTIVO · progreso/timeout sonda Cloud\n"
            "=====================================================\n"
            f"progreso: {self._v49_probe_completed}/{self._v49_probe_planned} · consulta actual: {current}\n"
            f"timeouts: {self._v49_probe_timeouts} · última duración: {last_duration} · tiempo total: {elapsed}\n"
            f"aborto controlado: {self._v49_probe_aborted_reason or '—'}\n"
            "timeout por variante: 7s · aborto tras 3 timeouts consecutivos\n"
            "seguridad: cada variante usa sesión Cloud aislada; V49 no altera la regla de movimiento\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import threading
import time

import app_v47
from xiaomi_cloud_history_v48 import XiaomiCloudHistoryV48
from xiaomi_e10_map_v48 import XiaomiE10MapV48


class App(app_v47.App):
    """V48: sonda de historial Cloud + restauración robusta de 10/23.

    La sonda es estrictamente de lectura. Durante los primeros segundos de cada
    fase se mantiene el polling normal de V46; luego se ejecuta una sola matriz
    de variantes para saber si el B112 guarda 10/5 bajo otra ventana, tipo,
    nombre o filtro de uid.
    """

    PROBE_DELAY_SECONDS = 8.0

    def __init__(self):
        self._v48_probe_worker = False
        self._v48_probe_done = False
        self._v48_probe_attempts = 0
        self._v48_probe_error = None
        self._v48_probe_queries = {}
        self._v48_probe_winner = None
        self._v48_probe_any_history = False
        self._v48_probe_total_records = 0
        self._v48_probe_plans = 0
        self._v48_privacy_ready_at = 0.0
        super().__init__()

    # -------------------------------------------------------- cliente mapa V48
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV48(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # --------------------------------------------------------------- fase/probe
    def _v48_reset_probe(self):
        self._v48_probe_worker = False
        self._v48_probe_done = False
        self._v48_probe_error = None
        self._v48_probe_queries = {}
        self._v48_probe_winner = None
        self._v48_probe_any_history = False
        self._v48_probe_total_records = 0
        self._v48_probe_plans = 0
        self._v48_privacy_ready_at = 0.0

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if getattr(self, "mapping_active", False):
            self._v48_reset_probe()
        return result

    def start_interior_mapping(self):
        result = super().start_interior_mapping()
        if getattr(self, "mapping_active", False):
            self._v48_reset_probe()
        return result

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

        def worker():
            try:
                result = XiaomiCloudHistoryV48(settings).read_probe(started_at)
                self._post_ui("cloud_history_probe_v48", result)
            except Exception as exc:
                self._post_ui(
                    "cloud_history_probe_error_v48",
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_poll_cloud_position(self):
        # Deja a V47 preparar 10/23 y a V46 hacer el polling normal mientras la
        # sonda todavía no corresponde.
        if not self.mapping_active or not self.vacuum:
            return

        if not self._v47_privacy_ready:
            return super()._maybe_poll_cloud_position()

        if self._v48_privacy_ready_at <= 0:
            self._v48_privacy_ready_at = time.monotonic()

        if self._v48_probe_worker:
            return

        if not self._v48_probe_done and (
            time.monotonic() - self._v48_privacy_ready_at >= self.PROBE_DELAY_SECONDS
        ):
            self._v48_start_probe()
            return

        return super()._maybe_poll_cloud_position()

    # ------------------------------------------------------------- eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v47_privacy_ready":
            result = super()._handle_ui_event(kind, payload)
            if self._v47_privacy_ready:
                self._v48_privacy_ready_at = time.monotonic()
                self._v48_probe_done = False
                self._v48_probe_error = None
            return result

        if kind == "cloud_history_probe_v48":
            self._v48_probe_worker = False
            self._v48_probe_done = True
            self._v48_probe_error = None
            result = payload[0] if payload else {}
            self._v48_probe_queries = dict(result.get("queries") or {})
            self._v48_probe_winner = result.get("winner")
            self._v48_probe_any_history = bool(result.get("any_history"))
            self._v48_probe_total_records = int(result.get("total_records", 0) or 0)
            self._v48_probe_plans = int(result.get("plans", 0) or 0)

            points = list(result.get("points") or [])
            if points:
                # Sólo puntos pertenecientes temporalmente a la fase actual
                # llegan aquí; la clase de sonda filtra los históricos viejos.
                self._v46_history_ok_reads += 1
                self._apply_history_result({
                    "queries": dict(result.get("canonical_queries") or {}),
                    "winner": result.get("winner"),
                    "points": points,
                    "records_with_path": int(result.get("records_with_path", 0) or 0),
                    "newest": result.get("newest"),
                })
            return

        if kind == "cloud_history_probe_error_v48":
            self._v48_probe_worker = False
            self._v48_probe_done = True
            self._v48_probe_error = str(payload[0]) if payload else "Error sonda Cloud V48"
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _v48_query_line(label, item):
        item = item or {}
        if not item.get("ok"):
            return f"{label}: ERROR {item.get('error') or 'sin detalle'}"
        return (
            f"{label}: records={int(item.get('records', 0) or 0)} · "
            f"path={int(item.get('records_with_path', 0) or 0)} · "
            f"pts={int(item.get('points', 0) or 0)} · "
            f"actuales={int(item.get('current_points', 0) or 0)} · "
            f"newest={item.get('newest')!r}"
        )

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        current_privacy = None
        if client is not None:
            try:
                current_privacy = client.map_privacy_state()
            except Exception:
                pass
        original = getattr(client, "privacy_original", None) if client else None
        temporary = bool(getattr(client, "privacy_temporarily_enabled", False)) if client else False

        lines = [self._v48_query_line(label, item) for label, item in self._v48_probe_queries.items()]
        matrix = "\n".join(lines) if lines else "— todavía no ejecutada —"
        return (
            "DIAGNÓSTICO V48 ACTIVO · sonda exhaustiva Cloud 10/5\n"
            "====================================================\n"
            f"sonda terminada: {self._v48_probe_done} · en curso: {self._v48_probe_worker} · intentos: {self._v48_probe_attempts}\n"
            f"variantes consultadas: {self._v48_probe_plans} · registros devueltos totales: {self._v48_probe_total_records}\n"
            f"algún historial encontrado: {self._v48_probe_any_history} · ganador actual: {self._v48_probe_winner or '—'}\n"
            f"error sonda: {self._v48_probe_error or '—'}\n"
            f"10/23 original: {original!r} · actual: {current_privacy!r} · restauración pendiente: {temporary}\n"
            "variantes: phase/24h/all · uid/no-uid · prop/event · 10.5/cleaning-path/cur-cleaning-path\n"
            "seguridad: consultas de historial son sólo lectura; históricos viejos nunca mueven el robot\n"
            "matriz:\n"
            f"{matrix}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import queue
import threading
import time
from typing import Any, Callable

from xiaomi_cloud_history_v48 import XiaomiCloudHistoryV48


ProgressCallback = Callable[[dict[str, Any]], None]


class XiaomiCloudHistoryV49(XiaomiCloudHistoryV48):
    """V49: sonda V48 observable y acotada.

    ``micloud`` no define timeout en su ``Session.post``. V48 además publicaba
    el diagnóstico recién al terminar las 20 consultas, por lo que un único
    request bloqueado se veía como ``en curso=True / variantes=0`` para siempre.

    V49 ejecuta cada variante con un cliente Cloud aislado dentro de un hilo
    daemon y espera como máximo ``REQUEST_TIMEOUT_SECONDS``. Los requests que
    exceden ese tiempo quedan abandonados de forma segura y no comparten sesión
    con las variantes siguientes. Tres timeouts consecutivos cancelan el resto
    de la matriz para evitar acumular hilos o castigar el backend.
    """

    REQUEST_TIMEOUT_SECONDS = 7.0
    MAX_CONSECUTIVE_TIMEOUTS = 3

    @staticmethod
    def _emit_progress(callback: ProgressCallback | None, snapshot: dict[str, Any]):
        if callback is None:
            return
        try:
            callback(dict(snapshot))
        except Exception:
            # El diagnóstico nunca puede romper la consulta principal.
            pass

    def _request_variant_timed(self, **kwargs) -> dict[str, Any]:
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        started = time.monotonic()

        def worker():
            try:
                # Cliente independiente por variante: si este request supera el
                # timeout, su Session no compite con la consulta siguiente.
                cloud = self._cloud()
                records = self._request_variant(cloud, **kwargs)
                try:
                    result_queue.put_nowait(("ok", records))
                except queue.Full:
                    pass
            except Exception as exc:
                try:
                    result_queue.put_nowait(("error", exc))
                except queue.Full:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        try:
            status, payload = result_queue.get(timeout=float(self.REQUEST_TIMEOUT_SECONDS))
        except queue.Empty:
            return {
                "ok": False,
                "timeout": True,
                "records": [],
                "error": f"timeout>{float(self.REQUEST_TIMEOUT_SECONDS):g}s",
                "duration": time.monotonic() - started,
            }

        duration = time.monotonic() - started
        if status == "error":
            return {
                "ok": False,
                "timeout": False,
                "records": [],
                "error": str(payload).strip() or type(payload).__name__,
                "duration": duration,
            }
        return {
            "ok": True,
            "timeout": False,
            "records": list(payload or []),
            "error": None,
            "duration": duration,
        }

    @staticmethod
    def _plans(phase_start: int, day_start: int, now: int):
        plans = []
        for include_uid in (True, False):
            for typ in ("prop", "event"):
                plans.append(("phase", include_uid, typ, "10.5", phase_start, now, False))
        for window, start, end in (("24h", day_start, now), ("all", 0, 9_999_999_999)):
            for include_uid in (True, False):
                for typ in ("prop", "event"):
                    plans.append((window, include_uid, typ, "10.5", start, end, True))
        for key in ("cleaning-path", "cur-cleaning-path"):
            for include_uid in (True, False):
                for typ in ("prop", "event"):
                    plans.append(("all", include_uid, typ, key, 0, 9_999_999_999, True))
        return plans

    def read_probe(
        self,
        phase_started_at: float,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        now = int(time.time()) + 60
        phase_start = max(0, int(float(phase_started_at or 0)))
        day_start = max(0, int(time.time()) - 86400)
        plans = self._plans(phase_start, day_start, now)

        diagnostics: dict[str, Any] = {}
        winner = None
        winner_points = []
        winner_records = 0
        winner_newest = None
        total_records = 0
        any_history = False
        timeout_count = 0
        consecutive_timeouts = 0
        completed = 0
        aborted_reason = None
        probe_started = time.monotonic()

        for index, (window, include_uid, typ, key, start, end, broad) in enumerate(plans):
            uid_label = "uid" if include_uid else "no-uid"
            label = f"{window}|{uid_label}|{typ}:{key}"
            self._emit_progress(progress_callback, {
                "stage": "request",
                "current": label,
                "completed": completed,
                "planned": len(plans),
                "timeouts": timeout_count,
                "total_records": total_records,
                "any_history": any_history,
                "elapsed": time.monotonic() - probe_started,
                "queries": diagnostics,
            })

            timed = self._request_variant_timed(
                typ=typ,
                key=key,
                time_start=start,
                time_end=end,
                include_uid=include_uid,
            )
            duration = float(timed.get("duration", 0.0) or 0.0)

            if not timed.get("ok"):
                is_timeout = bool(timed.get("timeout"))
                if is_timeout:
                    timeout_count += 1
                    consecutive_timeouts += 1
                else:
                    consecutive_timeouts = 0
                diagnostics[label] = {
                    "ok": False,
                    "records": 0,
                    "records_with_path": 0,
                    "points": 0,
                    "current_records_with_path": 0,
                    "current_points": 0,
                    "newest": None,
                    "preview": "—",
                    "error": timed.get("error") or "sin detalle",
                    "timeout": is_timeout,
                    "duration": duration,
                }
            else:
                consecutive_timeouts = 0
                records = list(timed.get("records") or [])
                total_records += len(records)
                if records:
                    any_history = True
                current_points, accepted_current, latest = self._current_points(
                    records,
                    float(phase_started_at or 0),
                    broad,
                )
                all_points, accepted_all, newest_all = self._merge_records(records, 0.0)
                diagnostics[label] = {
                    "ok": True,
                    "records": len(records),
                    "records_with_path": accepted_all,
                    "points": len(all_points),
                    "current_records_with_path": accepted_current,
                    "current_points": len(current_points),
                    "newest": newest_all if newest_all is not None else latest,
                    "preview": self._preview_record(records[0]) if records else "—",
                    "error": None,
                    "timeout": False,
                    "duration": duration,
                }
                if len(current_points) > len(winner_points):
                    winner = label
                    winner_points = current_points
                    winner_records = accepted_current
                    winner_newest = latest

            completed = index + 1
            self._emit_progress(progress_callback, {
                "stage": "complete",
                "current": label,
                "completed": completed,
                "planned": len(plans),
                "timeouts": timeout_count,
                "last_duration": duration,
                "total_records": total_records,
                "any_history": any_history,
                "elapsed": time.monotonic() - probe_started,
                "queries": diagnostics,
            })

            if consecutive_timeouts >= int(self.MAX_CONSECUTIVE_TIMEOUTS):
                aborted_reason = (
                    f"abortada tras {consecutive_timeouts} timeouts consecutivos; "
                    "las variantes restantes no se ejecutaron"
                )
                break

        canonical_queries = {}
        for typ in ("prop", "event"):
            source = diagnostics.get(f"phase|uid|{typ}:10.5") or {}
            canonical_queries[f"{typ}:10.5"] = {
                "ok": source.get("ok", False),
                "records": source.get("records", 0),
                "records_with_path": source.get("current_records_with_path", 0),
                "points": source.get("current_points", 0),
                "newest": source.get("newest"),
                "preview": source.get("preview", "—"),
                "error": source.get("error"),
            }

        return {
            "region": self.region,
            "did": self.did,
            "time_start": float(phase_started_at or 0),
            "winner": winner,
            "points": winner_points,
            "records_with_path": winner_records,
            "newest": winner_newest,
            "queries": diagnostics,
            "canonical_queries": canonical_queries,
            "total_records": total_records,
            "any_history": any_history,
            "plans": completed,
            "planned": len(plans),
            "timeouts": timeout_count,
            "aborted_reason": aborted_reason,
            "elapsed": time.monotonic() - probe_started,
        }

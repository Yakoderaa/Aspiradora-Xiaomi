import json
import time
from typing import Any

from xiaomi_cloud_history_v46 import XiaomiCloudHistoryV46


class XiaomiCloudHistoryV48(XiaomiCloudHistoryV46):
    """Sonda de sólo lectura para descubrir cómo publica 10/5 el B112.

    V47 demostró que map-privacy puede quedar en 0 y aun así
    ``get_user_device_data`` devolver cero registros para 10.5. V48 prueba un
    conjunto acotado de variantes conocidas sin ejecutar ninguna acción sobre
    el robot: distintas ventanas, con/sin uid, prop/event y nombres alternativos
    de la propiedad/evento.
    """

    ALIAS_KEYS = ("10.5", "cleaning-path", "cur-cleaning-path")

    def _request_variant(
        self,
        cloud,
        *,
        typ: str,
        key: str,
        time_start: int,
        time_end: int,
        limit: int = 20,
        include_uid: bool = True,
    ) -> list[dict[str, Any]]:
        payload = {
            "did": self.did,
            "time_end": int(time_end),
            "time_start": max(0, int(time_start)),
            "limit": max(1, min(100, int(limit))),
            "key": str(key),
            "type": str(typ),
        }
        if include_uid:
            payload["uid"] = str(self.session_data.get("user_id") or "")

        response = cloud.request_country(
            self.HISTORY_PATH,
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        decoded = self._decode_response_any(response)
        return [item for item in decoded["result"] if isinstance(item, dict)]

    @classmethod
    def _current_points(cls, records, phase_started_at: float, broad_window: bool):
        points, accepted, newest = cls._merge_records(records, phase_started_at)
        if not broad_window:
            return points, accepted, newest

        # En consultas 24h/all-time sólo una muestra con timestamp dentro de la
        # fase actual puede alimentar movimiento. Registros viejos o sin tiempo
        # sirven únicamente para diagnóstico.
        current = [
            point for point in points
            if point.get("history_time") is not None
            and float(point["history_time"]) + 0.001 >= float(phase_started_at)
        ]
        current_record_ids = {int(p.get("history_record", -1)) for p in current}
        return current, len(current_record_ids), newest

    def read_probe(self, phase_started_at: float) -> dict[str, Any]:
        cloud = self._cloud()
        now = int(time.time()) + 60
        phase_start = max(0, int(float(phase_started_at or 0)))
        day_start = max(0, int(time.time()) - 86400)

        # Orden deliberado: primero las variantes canónicas y luego aliases.
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

        diagnostics: dict[str, Any] = {}
        winner = None
        winner_points = []
        winner_records = 0
        winner_newest = None
        total_records = 0
        any_history = False

        for window, include_uid, typ, key, start, end, broad in plans:
            uid_label = "uid" if include_uid else "no-uid"
            label = f"{window}|{uid_label}|{typ}:{key}"
            try:
                records = self._request_variant(
                    cloud,
                    typ=typ,
                    key=key,
                    time_start=start,
                    time_end=end,
                    include_uid=include_uid,
                )
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
                }
                if len(current_points) > len(winner_points):
                    winner = label
                    winner_points = current_points
                    winner_records = accepted_current
                    winner_newest = latest
            except Exception as exc:
                diagnostics[label] = {
                    "ok": False,
                    "records": 0,
                    "records_with_path": 0,
                    "points": 0,
                    "current_records_with_path": 0,
                    "current_points": 0,
                    "newest": None,
                    "preview": "—",
                    "error": str(exc).strip() or type(exc).__name__,
                }

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
            "plans": len(plans),
        }

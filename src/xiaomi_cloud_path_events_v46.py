import json
import time
from typing import Any

from micloud import MiCloud

from xiaomi_e10 import XiaomiE10


class XiaomiCloudPathEventsV46:
    """Lee la trayectoria MIoT histórica que Xiaomi guarda en Cloud.

    El B112 expone 10/5 tanto como cur-cleaning-path como argumento del evento
    cleaning-path. La lectura puntual puede devolver el placeholder ``hello``;
    /user/get_user_device_data permite recuperar los frames que el teléfono usa
    de manera asíncrona sin depender de que el polling coincida con el instante
    exacto de publicación.
    """

    CANDIDATES = (
        ("10.5", "event"),
        ("10.5", "prop"),
    )

    def __init__(self, settings: dict):
        self.settings = settings or {}
        self.did = str(self.settings.get("device_did") or "").strip()
        self.region = str(self.settings.get("device_region") or "").strip() or "us"
        raw_session = self.settings.get("cloud_session") or ""
        try:
            self.session_data = json.loads(raw_session) if raw_session else {}
        except Exception as exc:
            raise RuntimeError("La sesión Xiaomi Cloud guardada no se pudo interpretar.") from exc
        if not self.did:
            raise RuntimeError("Falta el DID del E10 para consultar eventos Cloud.")

    def _cloud(self) -> MiCloud:
        data = self.session_data
        required = ("user_id", "service_token", "ssecurity")
        if not all(data.get(key) for key in required):
            raise RuntimeError("La sesión Xiaomi Cloud está incompleta.")
        cloud = MiCloud()
        cloud.user_id = data["user_id"]
        cloud.service_token = data["service_token"]
        cloud.ssecurity = data["ssecurity"]
        cloud.cuser_id = data.get("cuser_id")
        cloud.pass_token = data.get("pass_token")
        cloud.session = None
        return cloud

    @staticmethod
    def _decode_response(value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode("utf-8-sig", errors="strict")
        if isinstance(value, str):
            text = value.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            value = json.loads(text)
        if not isinstance(value, dict):
            raise RuntimeError(f"Respuesta historial Cloud inesperada: {type(value).__name__}")
        return value

    @staticmethod
    def _record_time(record):
        if not isinstance(record, dict):
            return None
        for key in ("time", "timestamp", "ts", "create_time", "created_at", "updateTime"):
            raw = record.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
                if value > 10_000_000_000:  # milisegundos
                    value /= 1000.0
                return value
            except Exception:
                continue
        return None

    @staticmethod
    def _value_candidates(value):
        """Desenvuelve value sin inventar números a partir de timestamps/metadatos."""
        out = []
        seen = set()

        def add(item, depth=0):
            if depth > 5 or item is None:
                return
            try:
                marker = repr(item)
            except Exception:
                marker = str(type(item))
            if marker in seen:
                return
            seen.add(marker)

            if isinstance(item, (bytes, bytearray, memoryview)):
                try:
                    add(bytes(item).decode("utf-8"), depth + 1)
                except Exception:
                    return
                return
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    return
                out.append(text)
                try:
                    parsed = json.loads(text)
                except Exception:
                    return
                if parsed != item:
                    add(parsed, depth + 1)
                return
            if isinstance(item, dict):
                # Sólo campos que pueden contener el payload del evento.
                for key in ("value", "values", "data", "payload", "arguments", "params", "event"):
                    if key in item:
                        add(item.get(key), depth + 1)
                return
            if isinstance(item, (list, tuple)):
                # Una lista numérica puede ser el path completo.
                if item and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in item):
                    out.append(list(item))
                    return
                for child in item:
                    add(child, depth + 1)

        add(value)
        return out

    @classmethod
    def _path_from_record(cls, record):
        if not isinstance(record, dict):
            return [], None
        raw_value = record.get("value")
        if raw_value is None:
            # Algunas variantes devuelven los argumentos en un campo distinto.
            for key in ("data", "payload", "arguments", "params"):
                if key in record:
                    raw_value = record.get(key)
                    break

        best = []
        best_raw = None
        for candidate in cls._value_candidates(raw_value):
            try:
                path = XiaomiE10.parse_trajectory(candidate)
            except Exception:
                path = []
            if len(path) > len(best):
                best = path
                best_raw = candidate
        return best, best_raw

    @staticmethod
    def _safe_raw(value, limit=220):
        if value is None:
            return None
        try:
            text = repr(value)
        except Exception:
            text = str(type(value).__name__)
        text = text.replace("\n", " ")
        return text if len(text) <= limit else text[:limit] + "…"

    def _request(self, key: str, type_: str, since_epoch: float, limit: int):
        now = int(time.time())
        start = max(0, int(float(since_epoch or 0)) - 5)
        payload = {
            "uid": str(self.session_data.get("user_id") or ""),
            "did": self.did,
            "time_start": start,
            "time_end": now + 60,
            "limit": max(1, min(100, int(limit))),
            "key": key,
            "type": type_,
        }
        response = self._cloud().request_country(
            "/user/get_user_device_data",
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        decoded = self._decode_response(response)
        code = decoded.get("code")
        if code not in (0, "0", None):
            raise RuntimeError(f"Historial Cloud {key}/{type_} rechazado: code={code}")
        result = decoded.get("result")
        if result is None:
            return [], decoded
        if isinstance(result, dict):
            for field in ("list", "data", "records", "result"):
                if isinstance(result.get(field), list):
                    return list(result[field]), decoded
            return [result], decoded
        if isinstance(result, list):
            return result, decoded
        return [], decoded

    def read_cleaning_path(self, since_epoch: float, limit: int = 40):
        attempts = []
        winner = None
        all_points = []
        seen = set()
        newest_time = None
        newest_raw = None
        stale_records = 0
        total_records = 0

        for key, type_ in self.CANDIDATES:
            try:
                records, _decoded = self._request(key, type_, since_epoch, limit)
                total_records += len(records)
                parsed_records = 0
                fresh_records = 0
                candidate_points = []

                # Orden cronológico para que merge_live_path preserve el stream.
                records = sorted(
                    records,
                    key=lambda r: self._record_time(r) if self._record_time(r) is not None else 0,
                )
                for record in records:
                    record_time = self._record_time(record)
                    if record_time is not None and float(since_epoch or 0) and record_time < float(since_epoch) - 5:
                        stale_records += 1
                        continue
                    fresh_records += 1
                    path, raw = self._path_from_record(record)
                    if not path:
                        continue
                    parsed_records += 1
                    if record_time is not None and (newest_time is None or record_time >= newest_time):
                        newest_time = record_time
                        newest_raw = raw
                    for point in path:
                        try:
                            sig = (
                                int(point.get("id", 0)),
                                round(float(point["x"]), 9),
                                round(float(point["y"]), 9),
                                round(float(point.get("phi", 0) or 0), 9),
                                int(point.get("update", 1) or 0),
                            )
                        except Exception:
                            continue
                        if sig in seen:
                            continue
                        seen.add(sig)
                        candidate_points.append(dict(point))

                attempts.append({
                    "key": key,
                    "type": type_,
                    "records": len(records),
                    "fresh": fresh_records,
                    "parsed_records": parsed_records,
                    "points": len(candidate_points),
                    "ok": True,
                })
                if candidate_points:
                    winner = (key, type_)
                    all_points.extend(candidate_points)
                    break
            except Exception as exc:
                attempts.append({
                    "key": key,
                    "type": type_,
                    "records": 0,
                    "points": 0,
                    "ok": False,
                    "error": (str(exc).strip() or type(exc).__name__)[:180],
                })

        return {
            "points": all_points,
            "winner_key": winner[0] if winner else None,
            "winner_type": winner[1] if winner else None,
            "record_count": total_records,
            "point_count": len(all_points),
            "latest_time": newest_time,
            "latest_raw": self._safe_raw(newest_raw),
            "stale_records_ignored": stale_records,
            "attempts": attempts,
            "queried_at": time.time(),
        }

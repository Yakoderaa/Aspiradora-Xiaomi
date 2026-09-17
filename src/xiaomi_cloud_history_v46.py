import json
import math
import time
from typing import Any

from xiaomi_cloud_telemetry import XiaomiCloudTelemetry
from xiaomi_e10 import XiaomiE10


class XiaomiCloudHistoryV46(XiaomiCloudTelemetry):
    """Consulta el historial que Xiaomi guarda para una propiedad/evento MIoT.

    En el B112, 10/5 (cur-cleaning-path) puede quedar en ``hello`` al leer la
    propiedad actual aunque el robot esté recorriendo la vivienda. Xiaomi Home
    también expone ``/user/get_user_device_data``; v46 consulta ahí la clave
    MIoT ``10.5`` tanto como ``prop`` (forma correcta para cur-cleaning-path)
    como ``event`` (fallback de compatibilidad con firmwares que publican el
    frame como evento).

    Esta clase es sólo lectura. No ejecuta ninguna acción sobre el robot.
    """

    HISTORY_PATH = "/user/get_user_device_data"
    PATH_KEY = "10.5"
    QUERY_TYPES = ("prop", "event")

    @staticmethod
    def _decode_response_any(response: Any) -> dict[str, Any]:
        if isinstance(response, (bytes, bytearray, memoryview)):
            try:
                response = bytes(response).decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise RuntimeError("Xiaomi Cloud devolvió historial en bytes no UTF-8.") from exc

        if isinstance(response, str):
            text = response.lstrip("\ufeff \t\r\n")
            if text.startswith("&&&START&&&"):
                text = text[len("&&&START&&&"):]
            try:
                response = json.loads(text)
            except Exception as exc:
                preview = text[:180].replace("\r", " ").replace("\n", " ")
                raise RuntimeError(f"Historial Xiaomi Cloud no JSON: {preview!r}") from exc

        if not isinstance(response, dict):
            raise RuntimeError(f"Respuesta de historial inesperada: {type(response).__name__}")

        code = response.get("code", 0)
        if code not in (0, "0", None):
            msg = response.get("message") or response.get("description") or response.get("msg") or "sin detalle"
            raise RuntimeError(f"Historial Xiaomi Cloud rechazado: code={code} · {msg}")

        result = response.get("result")
        if result is None:
            result = []
        if not isinstance(result, list):
            raise RuntimeError(f"Historial Xiaomi Cloud result={type(result).__name__}, se esperaba lista")
        return {"result": result, "code": code, "message": response.get("message") or ""}

    @staticmethod
    def _record_time(record: Any) -> float | None:
        if not isinstance(record, dict):
            return None
        for key in ("time", "timestamp", "createTime", "updateTime", "create_time"):
            value = record.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except Exception:
                continue
            if not math.isfinite(number) or number <= 0:
                continue
            # createTime suele venir en milisegundos.
            if number > 100_000_000_000:
                number /= 1000.0
            return number
        return None

    @staticmethod
    def _json_unwrap(value: Any) -> Any:
        current = value
        for _ in range(5):
            changed = False
            if isinstance(current, str):
                text = current.strip()
                if text:
                    try:
                        parsed = json.loads(text)
                    except Exception:
                        parsed = current
                    if parsed is not current and parsed != current:
                        current = parsed
                        changed = True
            if isinstance(current, list) and len(current) == 1 and isinstance(current[0], (str, list, dict)):
                current = current[0]
                changed = True
            if not changed:
                break
        return current

    @classmethod
    def _payload_candidates(cls, record: Any) -> list[Any]:
        if not isinstance(record, dict):
            return [record]

        result: list[Any] = []
        for key in ("value", "history", "data", "payload"):
            if key in record:
                result.append(cls._json_unwrap(record.get(key)))

        # Los eventos Xiaomi suelen guardar history como [{piid, value}, ...].
        # Si aparece piid=5, su value es exactamente el cur-cleaning-path.
        expanded = list(result)
        for candidate in expanded:
            if isinstance(candidate, list):
                for item in candidate:
                    if not isinstance(item, dict):
                        continue
                    try:
                        piid = int(item.get("piid"))
                    except Exception:
                        piid = None
                    if piid == 5 and "value" in item:
                        result.insert(0, cls._json_unwrap(item.get("value")))
        return result

    @classmethod
    def _points_from_record(cls, record: Any) -> list[dict[str, Any]]:
        for candidate in cls._payload_candidates(record):
            try:
                points = XiaomiE10.parse_trajectory(candidate)
            except Exception:
                points = []
            if points:
                return points
        return []

    @staticmethod
    def _preview_record(record: Any, limit: int = 190) -> str:
        try:
            if isinstance(record, dict):
                safe = {
                    key: record.get(key)
                    for key in ("time", "timestamp", "createTime", "updateTime", "value", "history")
                    if key in record
                }
                text = repr(safe)
            else:
                text = repr(record)
        except Exception:
            text = type(record).__name__
        text = text.replace("\r", " ").replace("\n", " ")
        return text if len(text) <= limit else text[:limit] + "…"

    def _request_history(self, cloud, typ: str, key: str, time_start: int, time_end: int, limit: int) -> list[dict[str, Any]]:
        payload = {
            "uid": str(self.session_data.get("user_id") or ""),
            "did": self.did,
            "time_end": int(time_end),
            "time_start": max(0, int(time_start)),
            "limit": max(1, min(200, int(limit))),
            "key": str(key),
            "type": str(typ),
        }
        response = cloud.request_country(
            self.HISTORY_PATH,
            self.region,
            {"data": json.dumps(payload, separators=(",", ":"))},
        )
        decoded = self._decode_response_any(response)
        return [item for item in decoded["result"] if isinstance(item, dict)]

    @classmethod
    def _merge_records(cls, records: list[dict[str, Any]], minimum_time: float) -> tuple[list[dict[str, Any]], int, float | None]:
        merged: list[dict[str, Any]] = []
        seen = set()
        accepted_records = 0
        newest = None

        # Ordenamos por timestamp cuando existe; para empates conservamos el
        # orden que entrega Xiaomi.
        ordered = sorted(
            enumerate(records),
            key=lambda pair: ((cls._record_time(pair[1]) or 0.0), pair[0]),
        )
        for record_index, record in ordered:
            ts = cls._record_time(record)
            if ts is not None and ts + 0.001 < minimum_time:
                continue
            points = cls._points_from_record(record)
            if not points:
                continue
            accepted_records += 1
            if ts is not None:
                newest = ts if newest is None else max(newest, ts)

            for point_index, point in enumerate(points):
                try:
                    x = float(point["x"])
                    y = float(point["y"])
                    phi = float(point.get("phi", 0) or 0)
                    pid = int(point.get("id", point_index))
                except Exception:
                    continue
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(phi)):
                    continue
                # El mismo frame puede aparecer tanto en una consulta anterior
                # como en la siguiente. Timestamp + pose-id + coordenadas evita
                # duplicarlo sin eliminar vueltas reales por el mismo lugar.
                signature = (
                    round(float(ts or 0.0), 3),
                    pid,
                    round(x, 6),
                    round(y, 6),
                    round(phi, 6),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                merged.append({
                    "id": pid,
                    "x": x,
                    "y": y,
                    "phi": phi,
                    "update": int(point.get("update", 1) or 0),
                    "history_time": ts,
                    "history_record": int(record_index),
                })

        return merged, accepted_records, newest

    def read_cleaning_path_history(self, time_start: float, limit: int = 120) -> dict[str, Any]:
        cloud = self._cloud()
        now = int(time.time()) + 30
        start = max(0, int(float(time_start or 0)))
        diagnostics: dict[str, Any] = {}
        winner = None
        winner_points: list[dict[str, Any]] = []
        winner_records = 0
        newest = None

        for typ in self.QUERY_TYPES:
            label = f"{typ}:{self.PATH_KEY}"
            try:
                records = self._request_history(cloud, typ, self.PATH_KEY, start, now, limit)
                points, accepted, latest = self._merge_records(records, float(time_start or 0))
                diagnostics[label] = {
                    "ok": True,
                    "records": len(records),
                    "records_with_path": accepted,
                    "points": len(points),
                    "newest": latest,
                    "preview": self._preview_record(records[0]) if records else "—",
                }
                if len(points) > len(winner_points):
                    winner = label
                    winner_points = points
                    winner_records = accepted
                    newest = latest
            except Exception as exc:
                diagnostics[label] = {
                    "ok": False,
                    "records": 0,
                    "records_with_path": 0,
                    "points": 0,
                    "newest": None,
                    "preview": "—",
                    "error": str(exc).strip() or type(exc).__name__,
                }

        return {
            "region": self.region,
            "did": self.did,
            "time_start": float(time_start or 0),
            "winner": winner,
            "points": winner_points,
            "records_with_path": winner_records,
            "newest": newest,
            "queries": diagnostics,
        }

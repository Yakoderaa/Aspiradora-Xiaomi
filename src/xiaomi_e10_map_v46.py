import json
from typing import Any

from xiaomi_e10_map_v44 import XiaomiE10MapV44


class XiaomiE10MapV46(XiaomiE10MapV44):
    """v46: upload realtime según el spec real del xiaomi.vacuum.b112.

    B112 sí expone 10/18 (upmapdata), 10/15 (upload-by-maptype-ii) y 10/6
    (upload-by-maptype). Los dos últimos reciben upload-type=0 para Realtime.
    Las acciones por map-id 10/14 y 10/2 sólo se usan cuando hay un id > 0.

    A diferencia de V41, primero intentamos por Xiaomi Cloud para conservar el
    code/out real de la acción. Si Cloud falla, usamos LAN como respaldo.
    """

    def __init__(self, *args, **kwargs):
        self.last_v46_upload_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def _decode_action_response(cls, response):
        try:
            decoded = cls._decode_cloud_json(response)
        except Exception:
            decoded = response if isinstance(response, dict) else {}
        if not isinstance(decoded, dict):
            return {}, None, None, {}

        top_code = decoded.get("code")
        result = decoded.get("result")
        result_code = None
        out = {}

        if isinstance(result, dict):
            result_code = result.get("code")
            for item in result.get("out") or []:
                if isinstance(item, dict) and item.get("piid") is not None:
                    out[str(item.get("piid"))] = item.get("value")
        elif isinstance(result, list):
            # Algunos servidores envuelven una única respuesta de acción.
            for row in result:
                if not isinstance(row, dict):
                    continue
                if result_code is None and row.get("code") is not None:
                    result_code = row.get("code")
                for item in row.get("out") or []:
                    if isinstance(item, dict) and item.get("piid") is not None:
                        out[str(item.get("piid"))] = item.get("value")
        return decoded, top_code, result_code, out

    def _call_cloud_action(self, aiid: int, values: list, label: str):
        payload = {
            "params": {
                "did": self.did,
                "siid": 10,
                "aiid": int(aiid),
                "in": list(values or []),
            }
        }
        try:
            response = self._cloud().request_country(
                "/miotspec/action",
                self.region,
                {"data": json.dumps(payload, separators=(",", ":"))},
            )
            _decoded, top_code, result_code, out = self._decode_action_response(response)
            codes = [c for c in (top_code, result_code) if c is not None]
            ok = all(str(c) == "0" for c in codes) if codes else bool(out) or isinstance(response, (dict, str, bytes, bytearray))
            return {
                "action": f"10/{aiid}",
                "label": label,
                "transport": "Cloud",
                "ok": bool(ok),
                "top_code": top_code,
                "result_code": result_code,
                "out": out,
            }
        except Exception as exc:
            return {
                "action": f"10/{aiid}",
                "label": label,
                "transport": "Cloud",
                "ok": False,
                "error": (str(exc).strip() or type(exc).__name__)[:180],
            }

    def _call_local_action(self, aiid: int, values: list, label: str):
        try:
            response = self.vacuum.device.call_action_by(10, int(aiid), list(values or []))
            code = response.get("code") if isinstance(response, dict) else None
            out = self._extract_action_out(response)
            ok = code in (0, "0", None)
            return {
                "action": f"10/{aiid}",
                "label": label,
                "transport": "LAN",
                "ok": bool(ok),
                "top_code": code,
                "result_code": None,
                "out": out,
            }
        except Exception as exc:
            return {
                "action": f"10/{aiid}",
                "label": label,
                "transport": "LAN",
                "ok": False,
                "error": (str(exc).strip() or type(exc).__name__)[:180],
            }

    def _call_action_resilient(self, aiid: int, values: list, label: str):
        cloud = self._call_cloud_action(aiid, values, label)
        if cloud.get("ok"):
            return cloud
        local = self._call_local_action(aiid, values, label)
        local["cloud_error"] = cloud.get("error") or (
            f"top={cloud.get('top_code')!r}, result={cloud.get('result_code')!r}"
        )
        return local

    def request_fresh_upload(self):
        # Map privacy es una propiedad real del B112: 0 permite upload, 1 lo
        # deshabilita. La clase heredada recuerda el valor para restaurarlo al
        # terminar la sesión.
        privacy_enabled = self.enable_map_upload_temporarily()
        try:
            map_id, maps = self.active_map_id()
        except Exception:
            map_id, maps = None, []

        attempts = []
        # Realtime sin map-id: rutas documentadas específicamente para B112.
        attempts.append(self._call_action_resilient(18, [], "upmapdata"))
        attempts.append(self._call_action_resilient(15, [0], "upload-by-maptype-ii · Realtime=0"))
        attempts.append(self._call_action_resilient(6, [0], "upload-by-maptype · Realtime=0"))

        # Sólo pedimos un mapa por id si existe uno real. cur-map-id=0 no es un
        # identificador válido para estas acciones.
        if map_id is not None:
            try:
                numeric_map_id = int(map_id)
            except Exception:
                numeric_map_id = 0
        else:
            numeric_map_id = 0
        if numeric_map_id > 0:
            attempts.append(self._call_action_resilient(14, [numeric_map_id], "upload-by-mapid-ii"))
            if not attempts[-1].get("ok"):
                attempts.append(self._call_action_resilient(2, [numeric_map_id], "upload-by-mapid"))

        privacy_now = self.map_privacy_state()
        outputs = {}
        for item in attempts:
            for piid, value in (item.get("out") or {}).items():
                outputs.setdefault(str(piid), []).append(value)

        result = {
            "map_id": map_id,
            "map_list_count": len(maps),
            "attempts": attempts,
            "privacy_original": self.privacy_original,
            "privacy_now": privacy_now,
            "privacy_temp": self.privacy_temporarily_enabled,
            "privacy_upload_allowed": bool(privacy_enabled or privacy_now == 0),
            "ok": any(bool(x.get("ok")) for x in attempts),
            "outputs": outputs,
            "documented_realtime": True,
        }
        self.last_upload_diagnostics = result
        self.last_v46_upload_diagnostics = dict(result)
        return result

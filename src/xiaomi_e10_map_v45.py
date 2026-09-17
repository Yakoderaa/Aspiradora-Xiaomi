from typing import Any

from xiaomi_e10_map_v44 import XiaomiE10MapV44


class XiaomiE10MapV45(XiaomiE10MapV44):
    """v45: no ejecuta acciones de upload no documentadas para B112.

    En el perfil MIoT del xiaomi.vacuum.b112 las acciones verificadas de mapa son
    upload-by-mapid (10/2) y upload-by-mapid-ii (10/14), ambas requieren un ID de
    mapa real. Con cur-map-id=0 no existe un ID válido que podamos enviar. Las
    antiguas llamadas 10/18, 10/15 y 10/6 no pertenecen a ese contrato B112 y se
    eliminan para evitar efectos laterales. Tampoco cambiamos map-privacy.
    """

    def __init__(self, *args, **kwargs):
        self.last_v45_upload_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    @staticmethod
    def _response_code(response):
        if not isinstance(response, dict):
            return None
        value = response.get("code")
        if value is None:
            return 0
        try:
            return int(value)
        except Exception:
            return value

    def enable_map_upload_temporarily(self):
        # v45 no toca privacidad. Se conserva el método por compatibilidad con
        # la cadena heredada, pero no modifica el dispositivo.
        try:
            current = self.map_privacy_state()
        except Exception:
            current = None
        if self.privacy_original is None:
            self.privacy_original = current
        self.privacy_temporarily_enabled = False
        return current == 0

    def request_fresh_upload(self):
        try:
            map_id, maps = self.active_map_id()
        except Exception:
            map_id, maps = None, []

        attempts = []
        privacy_now = None
        try:
            privacy_now = self.map_privacy_state()
        except Exception:
            pass
        if self.privacy_original is None:
            self.privacy_original = privacy_now
        self.privacy_temporarily_enabled = False

        if map_id is None or int(map_id) <= 0:
            result = {
                "map_id": map_id,
                "map_list_count": len(maps),
                "attempts": attempts,
                "privacy_original": self.privacy_original,
                "privacy_now": privacy_now,
                "privacy_temp": False,
                "ok": False,
                "skipped": True,
                "reason": "cur-map-id=0: no hay ID válido para 10/14 o 10/2; no se invocan acciones no documentadas",
            }
            self.last_upload_diagnostics = result
            self.last_v45_upload_diagnostics = dict(result)
            return result

        def call(aiid, label):
            try:
                response = self.vacuum.device.call_action_by(10, aiid, [int(map_id)])
                code = self._response_code(response)
                ok = code in (0, None)
                item = {
                    "action": f"10/{aiid}",
                    "label": label,
                    "ok": bool(ok),
                    "code": code,
                    "out": self._extract_action_out(response),
                }
                if not ok:
                    item["error"] = f"code={code}"
                attempts.append(item)
                return bool(ok)
            except Exception as exc:
                attempts.append({
                    "action": f"10/{aiid}",
                    "label": label,
                    "ok": False,
                    "error": str(exc).strip() or type(exc).__name__,
                })
                return False

        ok_ii = call(14, "upload-by-mapid-ii · B112 documentado")
        ok_old = False if ok_ii else call(2, "upload-by-mapid · B112 documentado")
        result = {
            "map_id": int(map_id),
            "map_list_count": len(maps),
            "attempts": attempts,
            "privacy_original": self.privacy_original,
            "privacy_now": privacy_now,
            "privacy_temp": False,
            "ok": bool(ok_ii or ok_old),
            "skipped": False,
            "reason": None,
        }
        self.last_upload_diagnostics = result
        self.last_v45_upload_diagnostics = dict(result)
        return result

import threading
import time

import app_v36
from xiaomi_cloud_telemetry import XiaomiCloudTelemetry
from xiaomi_e10 import XiaomiE10


class App(app_v36.App):
    """v37: lee 10/24 y propiedades de mapa directamente desde Xiaomi Cloud.

    Esta ruta evita depender de la URL del archivo de mapa. Si Cloud entrega una
    posición cambiante, reutiliza el pipeline seguro de v36 para confirmar el
    movimiento antes de dibujar trayectoria.
    """

    CLOUD_PROP_POLL_SECONDS = 2.0

    def __init__(self):
        self._v37_worker = False
        self._v37_last_at = 0.0
        self._v37_ok_reads = 0
        self._v37_error = None
        self._v37_region = None
        self._v37_raw_map_id = None
        self._v37_raw_path = None
        self._v37_raw_base = None
        self._v37_raw_robot = None
        self._v37_meta = {}
        super().__init__()

    @staticmethod
    def _xy_from_miot(value):
        parsed = XiaomiE10.parse_position(value)
        if not parsed:
            return None
        return float(parsed["x"]), float(parsed["y"])

    def _maybe_poll_cloud_position(self):
        if not self.mapping_active or not self.vacuum:
            return
        if bool(getattr(self, "_v34_motion_confirmed", False)):
            return
        if not self._cloud_session_ready() or self._v37_worker:
            return
        now = time.monotonic()
        if now - float(self._v37_last_at or 0.0) < self.CLOUD_PROP_POLL_SECONDS:
            return
        self._v37_last_at = now
        self._v37_worker = True
        settings = dict(self.settings or {})

        def worker():
            try:
                result = XiaomiCloudTelemetry(settings).read_map_properties()
                self._post_ui("cloud_miot_state", result)
            except Exception as exc:
                self._post_ui("cloud_miot_error", str(exc).strip() or "No se pudo consultar MIoT Cloud.")

        threading.Thread(target=worker, daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_miot_state":
            self._v37_worker = False
            result = payload[0] if payload else {}
            self._consume_cloud_miot_state(result)
            return
        if kind == "cloud_miot_error":
            self._v37_worker = False
            self._v37_error = str(payload[0]) if payload else "Error MIoT Cloud"
            self._v36_cloud_error = self._v37_error
            return
        return super()._handle_ui_event(kind, payload)

    def _consume_cloud_miot_state(self, result):
        values = dict((result or {}).get("values") or {})
        self._v37_meta = dict((result or {}).get("meta") or {})
        self._v37_region = (result or {}).get("region")
        self._v37_raw_map_id = values.get("cur_map_id")
        self._v37_raw_path = values.get("cur_cleaning_path")
        self._v37_raw_base = values.get("charging_base")
        self._v37_raw_robot = values.get("robot_location")
        self._v37_ok_reads += 1
        self._v37_error = None

        robot_xy = self._xy_from_miot(self._v37_raw_robot)
        base_xy = self._xy_from_miot(self._v37_raw_base)

        # Hacemos que el diagnóstico heredado de v36 refleje la fuente real.
        self._v36_cloud_map_name = "MIoT Cloud directo 10/24"
        self._v36_cloud_raw_robot = robot_xy
        self._v36_cloud_raw_base = base_xy
        self._v36_cloud_error = None

        if robot_xy is not None and base_xy is not None:
            self._consume_cloud_position(robot_xy, base_xy)

    @staticmethod
    def _meta_time(meta, key):
        item = (meta or {}).get(key) or {}
        value = item.get("updateTime")
        return "—" if value is None else str(value)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V37 ACTIVO · MIoT Xiaomi Cloud directo\n"
            "==================================================\n"
            f"región cloud: {self._v37_region or (self.settings or {}).get('device_region') or '—'}\n"
            f"consultas cloud correctas: {self._v37_ok_reads}\n"
            f"10/24 cloud crudo: {self._v37_raw_robot!r}\n"
            f"10/24 cloud updateTime: {self._meta_time(self._v37_meta, 'robot_location')}\n"
            f"10/22 cloud crudo: {self._v37_raw_base!r}\n"
            f"10/22 cloud updateTime: {self._meta_time(self._v37_meta, 'charging_base')}\n"
            f"10/5 cloud crudo: {self._v37_raw_path!r}\n"
            f"10/5 cloud updateTime: {self._meta_time(self._v37_meta, 'cur_cleaning_path')}\n"
            f"10/2 cloud crudo: {self._v37_raw_map_id!r}\n"
            f"error MIoT cloud: {self._v37_error or '—'}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

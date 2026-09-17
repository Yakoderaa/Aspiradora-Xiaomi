import math
import threading
import time

import app_v39
from xiaomi_e10_ijai_map import XiaomiE10IjaiMapClient


class App(app_v39.App):
    """v40: mapa real IJAI para xiaomi.vacuum.b112.

    El E10 no pertenece a la familia de mapas Xiaomi-JSON que intentábamos
    descifrar en v39: su archivo Cloud usa el formato IJAI (protobuf + AES-ECB
    derivado de wifi_sn/user_id/did/MAC/modelo). Esta versión usa esa ruta y,
    mientras se está mapeando, pide periódicamente al firmware una subida fresca
    del mapa para no depender de un objeto Cloud congelado.
    """

    CLOUD_FILE_POLL_SECONDS = 1.45
    CLOUD_UPLOAD_INTERVAL_SECONDS = 5.0
    CLOUD_UPLOAD_SETTLE_SECONDS = 0.65

    def __init__(self):
        self._v40_client = None
        self._v40_client_vacuum = None
        self._v40_last_upload_at = 0.0
        self._v40_upload_attempts = 0
        self._v40_last_upload = None
        self._v40_slot = None
        self._v40_endpoint = None
        self._v40_valid_slots = []
        self._v40_slot_errors = {}
        self._v40_raw_size = 0
        self._v40_decrypted_size = 0
        self._v40_raw_prefix = None
        self._v40_wifi_sn_source = None
        self._v40_wifi_sn_length = 0
        self._v40_mac_available = False
        self._v40_pose_id = None
        self._v40_upload_date = None
        self._v40_native_robot = None
        self._v40_native_base = None
        self._v40_native_path_count = 0
        self._v40_unit_scale = 1.0
        self._v40_origin_source = "—"
        self._v40_fallback_origin = None
        super().__init__()

    # -------------------------------------------------------- ventana/update
    def _manual_update_found_safe(self, update):
        # El cierre normal ya guarda geometría. Para una actualización la
        # persistimos además ANTES de lanzar el helper/instalador, evitando que
        # un cierre rápido deje el último Configure sin escribir.
        try:
            self._v38_capture_geometry(save=True)
        except Exception:
            pass
        return super()._manual_update_found_safe(update)

    # ------------------------------------------------------ cliente IJAI Cloud
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10IjaiMapClient(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def _v38_maybe_poll_map_file(self):
        """Reemplaza el sondeo JSON v39 por el mapa IJAI del E10."""
        if not self.mapping_active or not self.vacuum:
            return
        if not self._cloud_session_ready() or self._v38_map_worker:
            return
        now = time.monotonic()
        if now - float(self._v38_map_last_at or 0.0) < self.CLOUD_FILE_POLL_SECONDS:
            return

        self._v38_map_last_at = now
        self._v38_map_worker = True
        vacuum = self.vacuum
        settings = dict(self.settings or {})
        request_upload = now - float(self._v40_last_upload_at or 0.0) >= self.CLOUD_UPLOAD_INTERVAL_SECONDS
        if request_upload:
            self._v40_last_upload_at = now

        def worker():
            upload_info = None
            try:
                client = self._v40_map_client(vacuum, settings)
                if request_upload:
                    upload_info = client.request_fresh_upload()
                    if upload_info.get("ok"):
                        time.sleep(self.CLOUD_UPLOAD_SETTLE_SECONDS)
                snapshot = client.load()
                self._post_ui("cloud_ijai_map_state_v40", snapshot, upload_info)
            except Exception as exc:
                self._post_ui(
                    "cloud_ijai_map_error_v40",
                    str(exc).strip() or "No se pudo leer el mapa IJAI del E10.",
                    upload_info,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------------------------------- unidades/origen
    @staticmethod
    def _v40_detect_scale(snapshot):
        """Normaliza coordenadas del protobuf a metros sin asumir firmware."""
        values = []
        for point in (snapshot.raw_robot, snapshot.raw_base):
            if point is not None:
                try:
                    values.extend((abs(float(point[0])), abs(float(point[1]))))
                except Exception:
                    pass
        for point in list(snapshot.raw_path or [])[:32]:
            try:
                values.extend((abs(float(point[0])), abs(float(point[1]))))
            except Exception:
                pass
        maximum = max(values, default=0.0)
        # IJAI normal es metros (habitualmente decenas). Dejamos tolerancia para
        # variantes que expongan centímetros o milímetros.
        if maximum > 1000.0:
            return 0.001
        if maximum > 150.0:
            return 0.01
        return 1.0

    @staticmethod
    def _v40_scale_point(point, scale):
        if point is None:
            return None
        try:
            return float(point[0]) * scale, float(point[1]) * scale
        except Exception:
            return None

    @staticmethod
    def _v39_relative_mm(point, base):
        """En v40 las muestras ya están normalizadas a METROS."""
        if point is None or base is None:
            return None
        try:
            return {
                "x": float(point[0]) - float(base[0]),
                "y": float(point[1]) - float(base[1]),
                "angle": 0.0,
            }
        except Exception:
            return None

    def _v40_prepare_snapshot(self, snapshot):
        self._v40_native_robot = snapshot.raw_robot
        self._v40_native_base = snapshot.raw_base
        self._v40_native_path_count = len(snapshot.raw_path or [])
        scale = self._v40_detect_scale(snapshot)
        self._v40_unit_scale = scale

        snapshot.raw_robot = self._v40_scale_point(snapshot.raw_robot, scale)
        snapshot.raw_base = self._v40_scale_point(snapshot.raw_base, scale)
        snapshot.raw_path = [
            scaled
            for point in (snapshot.raw_path or [])
            if (scaled := self._v40_scale_point(point, scale)) is not None
        ]

        # Normalmente IJAI trae chargeStation. Si un firmware la omite, usamos
        # el primer punto del historial (preferible) o la primera currentPose.
        if snapshot.raw_base is None:
            if self._v40_fallback_origin is None:
                if snapshot.raw_path:
                    self._v40_fallback_origin = tuple(snapshot.raw_path[0])
                    self._v40_origin_source = "primer punto historyPose"
                elif snapshot.raw_robot is not None:
                    self._v40_fallback_origin = tuple(snapshot.raw_robot)
                    self._v40_origin_source = "primera currentPose"
            snapshot.raw_base = self._v40_fallback_origin
        else:
            self._v40_origin_source = "chargeStation IJAI"
            self._v40_fallback_origin = tuple(snapshot.raw_base)
        return snapshot

    def _v39_consume_snapshot(self, snapshot):
        return super()._v39_consume_snapshot(self._v40_prepare_snapshot(snapshot))

    # ------------------------------------------------------------ eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_ijai_map_state_v40":
            self._v38_map_worker = False
            snapshot = payload[0] if payload else None
            upload_info = payload[1] if len(payload) > 1 else None
            if upload_info is not None:
                self._v40_upload_attempts += 1
                self._v40_last_upload = upload_info
            if snapshot is None:
                return

            self._v40_slot = snapshot.slot
            self._v40_endpoint = snapshot.endpoint
            self._v40_valid_slots = list(snapshot.valid_slots or [])
            self._v40_slot_errors = dict(snapshot.slot_errors or {})
            self._v40_raw_size = int(snapshot.raw_size or 0)
            self._v40_decrypted_size = int(snapshot.decrypted_size or 0)
            self._v40_raw_prefix = snapshot.raw_prefix_hex
            self._v40_wifi_sn_source = snapshot.wifi_sn_source
            self._v40_wifi_sn_length = int(snapshot.wifi_sn_length or 0)
            self._v40_mac_available = bool(snapshot.mac_available)
            self._v40_pose_id = snapshot.pose_id
            self._v40_upload_date = snapshot.upload_date
            self._v38_map_error = None
            self._v39_consume_snapshot(snapshot)
            return

        if kind == "cloud_ijai_map_error_v40":
            self._v38_map_worker = False
            self._v38_map_error = str(payload[0]) if payload else "Error IJAI"
            upload_info = payload[1] if len(payload) > 1 else None
            if upload_info is not None:
                self._v40_upload_attempts += 1
                self._v40_last_upload = upload_info
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _v40_upload_diag(info):
        if not isinstance(info, dict):
            return "—"
        if info.get("ok"):
            return f"OK · acción {info.get('action')} · map_id {info.get('map_id')}"
        return f"ERROR · map_id {info.get('map_id')} · {info.get('error') or 'sin detalle'}"

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V40 ACTIVO · E10 / mapa IJAI real\n"
            "================================================\n"
            "familia detectada: xiaomi.vacuum.b112 → IJAI protobuf\n"
            "descifrado esperado: AES-ECB + clave wifi_sn/user_id/did/MAC/modelo + zlib\n"
            f"wifi_sn: {'detectado' if self._v40_wifi_sn_length else '—'} · fuente {self._v40_wifi_sn_source or '—'} · longitud {self._v40_wifi_sn_length or 0}\n"
            f"MAC local para clave: {'detectada' if self._v40_mac_available else '—'}\n"
            f"slot Cloud elegido: {self._v40_slot or '—'} · slots válidos: {self._v40_valid_slots or []}\n"
            f"endpoint URL: {self._v40_endpoint or '—'}\n"
            f"archivo cifrado: {self._v40_raw_size} bytes · descifrado: {self._v40_decrypted_size} bytes\n"
            f"prefijo archivo (hex, 16 B): {self._v40_raw_prefix or '—'}\n"
            f"errores de otros slots: {self._v40_slot_errors or {}}\n"
            f"map_id protobuf: {self._v39_map_id!r} · resolution: {self._v39_resolution!r}\n"
            f"pose-id protobuf: {self._v40_pose_id!r} · mapUploadDate: {self._v40_upload_date!r}\n"
            f"currentPose IJAI cruda: {self._v40_native_robot!r}\n"
            f"chargeStation IJAI cruda: {self._v40_native_base!r}\n"
            f"historyPose IJAI: {self._v40_native_path_count} puntos\n"
            f"escala aplicada a metros: {self._v40_unit_scale:g}\n"
            f"origen visual: {self._v40_origin_source}\n"
            f"solicitudes de mapa fresco: {self._v40_upload_attempts}\n"
            f"última solicitud upload: {self._v40_upload_diag(self._v40_last_upload)}\n"
            f"movimiento confirmado: {bool(getattr(self, '_v34_motion_confirmed', False))}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import math
import threading
import time

import app_v45
from xiaomi_cloud_path_events_v46 import XiaomiCloudPathEventsV46
from xiaomi_e10_map_v46 import XiaomiE10MapV46


class App(app_v45.App):
    """v46: trayectoria desde el evento Cloud 10/5 + seguridad de origen.

    El polling de 10/5 puede devolver ``hello`` aunque el firmware publique la
    trayectoria como evento cleaning-path. V46 consulta el historial Cloud de
    ese evento y sólo mueve el icono cuando aparecen DOS posiciones distintas.
    Nunca usa cambios de chargingbase para confirmar movimiento.
    """

    CLOUD_FILE_POLL_SECONDS = 2.0
    CLOUD_UPLOAD_INTERVAL_SECONDS = 10.0
    CLOUD_UPLOAD_SETTLE_SECONDS = 2.5
    CLOUD_EVENT_POLL_MS = 1450

    def __init__(self):
        self._v46_event_worker = False
        self._v46_event_since = 0.0
        self._v46_event_diag = {}
        self._v46_event_origins = {}
        self._v46_event_scale = {}
        self._v46_event_merged_count = 0
        self._v46_event_new_count = 0
        self._v46_event_motion = False
        self._v46_event_error = None
        self._v46_event_client = None
        self._v46_last_upload_diag = {}
        super().__init__()
        self.after(1100, self._v46_event_tick)

    # ---------------------------------------------------------- mapa Cloud
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV46(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # ------------------------------------------------------- evento 10/5
    def _v46_reset_event_session(self, reset_origin=False):
        self._v46_event_since = time.time() - 2.0
        self._v46_event_diag = {}
        self._v46_event_merged_count = 0
        self._v46_event_new_count = 0
        self._v46_event_motion = False
        self._v46_event_error = None
        self._v46_event_client = None
        if reset_origin:
            self._v46_event_origins = {}
            self._v46_event_scale = {}

    def start_new_mapping(self):
        self._v46_reset_event_session(reset_origin=True)
        return super().start_new_mapping()

    def start_interior_mapping(self):
        # Conservamos el origen del Paso 1: los puntos de ambos pasos comparten
        # el mismo sistema de coordenadas cuando vienen de la misma sesión/mapa.
        self._v46_reset_event_session(reset_origin=False)
        return super().start_interior_mapping()

    @staticmethod
    def _v46_distinct_points(points, epsilon=1e-4):
        distinct = []
        for point in points or []:
            try:
                xy = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if not distinct or math.hypot(xy[0] - distinct[-1][0], xy[1] - distinct[-1][1]) >= epsilon:
                distinct.append(xy)
        return distinct

    @staticmethod
    def _v46_detect_path_scale(points):
        """El spec B112 muestra x/y en metros; sólo corrige variantes enormes."""
        distances = []
        previous = None
        for point in points or []:
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if previous is not None:
                d = math.hypot(current[0] - previous[0], current[1] - previous[1])
                if d > 1e-9:
                    distances.append(d)
            previous = current
        if not distances:
            return 1.0
        distances.sort()
        median = distances[len(distances) // 2]
        # Un robot no avanza decenas/centenas de metros entre poses contiguas.
        if median > 100.0:
            return 0.001
        if median > 5.0:
            return 0.01
        return 1.0

    def _v46_normalize_event_path(self, path, phase):
        if not path:
            return []
        phase = int(phase or 0)
        # Un solo origen global mientras exista: mantiene Paso 1 y Paso 2
        # alineados. Si V46 arrancó directamente en Paso 2, su primer punto es 0.
        origin = self._v46_event_origins.get("global")
        if origin is None:
            first = path[0]
            try:
                origin = (float(first["x"]), float(first["y"]))
            except Exception:
                return []
            self._v46_event_origins["global"] = origin
        scale = self._v46_event_scale.get("global")
        if scale is None:
            scale = self._v46_detect_path_scale(path)
            self._v46_event_scale["global"] = scale

        normalized = []
        for point in path:
            try:
                normalized.append({
                    "id": int(point.get("id", len(normalized))),
                    "x": (float(point["x"]) - origin[0]) * scale,
                    "y": (float(point["y"]) - origin[1]) * scale,
                    "phi": float(point.get("phi", 0) or 0),
                    "update": int(point.get("update", 1) or 0),
                })
            except Exception:
                continue
        return normalized

    def _v46_apply_event_path(self, result):
        points = list((result or {}).get("points") or [])
        if not points or not self.local_map or not self.mapping_active:
            return

        merger = getattr(self.vacuum, "_merge_live_path", None) if self.vacuum else None
        if callable(merger):
            try:
                raw_merged, changed = merger(points)
            except Exception:
                raw_merged, changed = points, len(points)
        else:
            raw_merged, changed = points, len(points)

        phase = int(self.mapping_phase or 0)
        normalized = self._v46_normalize_event_path(raw_merged, phase)
        if not normalized:
            return
        distinct = self._v46_distinct_points(normalized, epsilon=self.MOTION_EPSILON)
        motion = len(distinct) >= 2

        self._v46_event_merged_count = len(normalized)
        self._v46_event_new_count = int(changed or 0)
        self._v46_event_motion = bool(motion)

        # Base/origen visual fijo. Una muestra única NO desplaza el robot.
        self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
        if motion:
            added = self.local_map.merge_trajectory(normalized, phase=phase)
            last = normalized[-1]
            self.local_map.set_robot({
                "x": float(last["x"]),
                "y": float(last["y"]),
                "angle": float(last.get("phi", 0) or 0),
            })
            self._v34_motion_confirmed = True
            self._v34_position_changes = max(
                int(getattr(self, "_v34_position_changes", 0) or 0),
                max(1, len(distinct) - 1),
            )
            if phase == 1:
                self._rebuild_mapped_walls(force=False)
        else:
            added = 0
            self.local_map.set_robot({"x": 0.0, "y": 0.0, "angle": 0.0})

        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        state.update({
            "path": normalized if motion else [],
            "robot": None,
            "charging_base": None,
            "path_source": "Cloud history · event 10/5 cleaning-path",
            "position_source": "último punto event 10/5" if motion else "event 10/5 · esperando segundo punto",
            "direct_path_count": len(normalized),
            "action_path_count": int(state.get("action_path_count", 0) or 0),
            "accumulated_path_count": len(normalized),
            "new_path_count": int(added or changed or 0),
            "telemetry_note": "trayectoria Cloud 10/5 fresca" if motion else "primer punto Cloud recibido; todavía no confirma movimiento",
        })
        self._last_map_state_debug = state
        try:
            self._stable_map_status(state)
        except Exception:
            pass
        self._render_maps()

    def _v46_event_tick(self):
        try:
            if (
                self.mapping_active
                and self.vacuum
                and self._cloud_session_ready()
                and not self._v46_event_worker
                and self._v46_event_since > 0
            ):
                self._v46_event_worker = True
                settings = dict(self.settings or {})
                since_epoch = float(self._v46_event_since)

                def worker():
                    try:
                        client = XiaomiCloudPathEventsV46(settings)
                        result = client.read_cleaning_path(since_epoch, limit=60)
                        self._post_ui("v46_cloud_path_history", result)
                    except Exception as exc:
                        self._post_ui(
                            "v46_cloud_path_history_error",
                            str(exc).strip() or type(exc).__name__,
                        )

                threading.Thread(target=worker, daemon=True).start()
        finally:
            try:
                self.after(self.CLOUD_EVENT_POLL_MS, self._v46_event_tick)
            except Exception:
                pass

    # ------------------------------------------------------------ UI events
    def _handle_ui_event(self, kind, payload):
        if kind == "v46_cloud_path_history":
            self._v46_event_worker = False
            result = payload[0] if payload else {}
            self._v46_event_diag = dict(result or {})
            self._v46_event_error = None
            self._v46_apply_event_path(result)
            return
        if kind == "v46_cloud_path_history_error":
            self._v46_event_worker = False
            self._v46_event_error = str(payload[0]) if payload else "Error historial 10/5"
            return

        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            if client is not None:
                self._v46_last_upload_diag = dict(
                    getattr(client, "last_v46_upload_diagnostics", {}) or {}
                )
        return result

    # --------------------------------------------------------- diagnóstico
    @staticmethod
    def _v46_attempts_text(attempts):
        if not attempts:
            return "—"
        rows = []
        for item in attempts:
            if item.get("ok"):
                rows.append(
                    f"{item.get('action')} {item.get('transport')} OK "
                    f"top={item.get('top_code')!r} result={item.get('result_code')!r} out={item.get('out') or {}}"
                )
            else:
                rows.append(
                    f"{item.get('action')} {item.get('transport')} ERROR "
                    f"{item.get('error') or item.get('cloud_error') or ''}"
                )
        return "\n    ".join(rows)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        event = dict(self._v46_event_diag or {})
        upload = dict(self._v46_last_upload_diag or {})
        latest = event.get("latest_time")
        age = None
        try:
            age = max(0.0, time.time() - float(latest)) if latest is not None else None
        except Exception:
            pass
        return (
            "DIAGNÓSTICO V46 ACTIVO · evento cleaning-path + movimiento seguro\n"
            "================================================================\n"
            "causa V44 corregida: 10/24 quedó fijo; 10/22 pasó a 255_255 y generó el salto falso -196/-195\n"
            "regla V46: cambios de chargingbase jamás confirman movimiento; 255_255 es sentinela\n"
            "fuente nueva: /user/get_user_device_data → MIoT 10.5 type=event (fallback prop)\n"
            f"historial ganador: key={event.get('winner_key') or '—'} · type={event.get('winner_type') or '—'}\n"
            f"registros recibidos: {event.get('record_count', 0)} · stale ignorados: {event.get('stale_records_ignored', 0)}\n"
            f"puntos parseados historial: {event.get('point_count', 0)} · fusionados: {self._v46_event_merged_count} · nuevos: {self._v46_event_new_count}\n"
            f"último evento epoch: {latest!r} · edad: {f'{age:.1f}s' if age is not None else '—'}\n"
            f"payload último evento (recortado): {event.get('latest_raw') or '—'}\n"
            f"intentos historial: {event.get('attempts') or []}\n"
            f"origen raw trayectoria: {self._v46_event_origins.get('global')!r} · escala: {self._v46_event_scale.get('global', 1.0)}\n"
            f"movimiento confirmado por trayectoria: {self._v46_event_motion}\n"
            f"error historial: {self._v46_event_error or '—'}\n"
            "upload B112: 10/18 + 10/15(type=0) + 10/6(type=0) son acciones documentadas; map-id sólo si >0\n"
            f"upload map_id: {upload.get('map_id')!r} · privacidad: original={upload.get('privacy_original')!r} actual={upload.get('privacy_now')!r}\n"
            f"respuestas upload:\n    {self._v46_attempts_text(upload.get('attempts') or [])}\n"
            f"outputs upload por PIID: {upload.get('outputs') or {}}\n"
            "10/15 y 10/16 se conservan sólo como diagnóstico de argumentos de 10/12; el firmware puede no permitir leerlos como propiedades\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

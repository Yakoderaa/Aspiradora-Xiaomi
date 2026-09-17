import math
import statistics
import threading
import time

import app_v45
from xiaomi_cloud_history_v46 import XiaomiCloudHistoryV46


class App(app_v45.App):
    """v46: trayectoria real desde el historial Xiaomi Cloud de 10/5.

    V45 dejó probado que 10/24 permanece inmóvil y que 10/22 puede publicar el
    sentinela 255_255. Por eso v46 deja de usar la posición Cloud actual como
    fuente de movimiento y consulta ``user/get_user_device_data`` para la clave
    MIoT 10.5. Cur-cleaning-path es una propiedad; ``event`` se consulta sólo
    como fallback de compatibilidad.

    Ninguna muestra aislada mueve el dibujo: sólo se acepta una trayectoria con
    al menos dos coordenadas X/Y distintas.
    """

    CLOUD_HISTORY_POLL_SECONDS = 1.8
    HISTORY_POINT_ID_BASE = 4_600_000
    HISTORY_MOTION_EPSILON = 0.015

    def __init__(self):
        self._v46_history_worker = False
        self._v46_history_last_at = 0.0
        self._v46_history_ok_reads = 0
        self._v46_history_error = None
        self._v46_history_queries = {}
        self._v46_history_winner = None
        self._v46_history_records = 0
        self._v46_history_raw_points = 0
        self._v46_history_distinct_points = 0
        self._v46_history_applied_points = 0
        self._v46_history_new_last = 0
        self._v46_history_newest = None
        self._v46_history_scale = 1.0
        self._v46_history_origin = None
        self._v46_history_last_raw = None
        self._v46_history_last_relative = None
        self._v46_history_motion_confirmed = False
        self._v46_history_point_id = self.HISTORY_POINT_ID_BASE
        self._v46_history_seen = set()
        self._v46_phase = None
        self._v46_phase_started_at = 0.0
        super().__init__()

    # ------------------------------------------------------------- sesión/fase
    def _v46_reset_history_phase(self, phase=None):
        self._v46_phase = int(phase or 0)
        # Margen para no perder el primer frame por redondeo entre relojes.
        self._v46_phase_started_at = time.time() - 5.0
        self._v46_history_last_at = 0.0
        self._v46_history_error = None
        self._v46_history_queries = {}
        self._v46_history_winner = None
        self._v46_history_records = 0
        self._v46_history_raw_points = 0
        self._v46_history_distinct_points = 0
        self._v46_history_applied_points = 0
        self._v46_history_new_last = 0
        self._v46_history_newest = None
        self._v46_history_scale = 1.0
        self._v46_history_origin = None
        self._v46_history_last_raw = None
        self._v46_history_last_relative = None
        self._v46_history_motion_confirmed = False
        self._v46_history_seen = set()
        self._v46_history_point_id = self.HISTORY_POINT_ID_BASE + max(0, self._v46_phase) * 100_000

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if getattr(self, "mapping_active", False):
            self._v46_reset_history_phase(getattr(self, "mapping_phase", 1))
        return result

    def start_interior_mapping(self):
        result = super().start_interior_mapping()
        if getattr(self, "mapping_active", False):
            self._v46_reset_history_phase(getattr(self, "mapping_phase", 2))
        return result

    # ------------------------------------------------------------- Cloud 10.5
    def _maybe_poll_cloud_position(self):
        """Reemplaza el polling v37 de 10/24 por historial de 10/5."""
        if not self.mapping_active or not self.vacuum:
            return
        if not self._cloud_session_ready() or self._v46_history_worker:
            return

        phase = int(getattr(self, "mapping_phase", 0) or 0)
        if phase not in (1, 2):
            return
        if self._v46_phase != phase or not self._v46_phase_started_at:
            self._v46_reset_history_phase(phase)

        now = time.monotonic()
        if now - float(self._v46_history_last_at or 0.0) < self.CLOUD_HISTORY_POLL_SECONDS:
            return
        self._v46_history_last_at = now
        self._v46_history_worker = True
        settings = dict(self.settings or {})
        started_at = float(self._v46_phase_started_at)

        def worker():
            try:
                result = XiaomiCloudHistoryV46(settings).read_cleaning_path_history(started_at)
                self._post_ui("cloud_history_v46", result)
            except Exception as exc:
                self._post_ui(
                    "cloud_history_error_v46",
                    str(exc).strip() or "No se pudo consultar el historial 10.5 de Xiaomi Cloud.",
                )

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------- trayectoria segura
    @classmethod
    def _distinct_xy_count(cls, points):
        distinct = []
        for point in points or []:
            try:
                xy = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if not distinct or math.hypot(xy[0] - distinct[-1][0], xy[1] - distinct[-1][1]) >= cls.HISTORY_MOTION_EPSILON:
                distinct.append(xy)
        return len(distinct)

    @staticmethod
    def _detect_history_scale(points):
        """Detecta m/cm/mm por distancia entre poses, no por coordenada absoluta."""
        steps = []
        previous = None
        for point in points or []:
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if previous is not None:
                distance = math.hypot(current[0] - previous[0], current[1] - previous[1])
                if math.isfinite(distance) and distance > 1e-9:
                    steps.append(distance)
            previous = current
        if not steps:
            return 1.0
        typical = float(statistics.median(steps[:80]))
        # Un robot avanza décimas de metro por frame. En cm son decenas y en mm
        # centenas; los umbrales son deliberadamente amplios.
        if typical > 80.0:
            return 0.001
        if typical > 8.0:
            return 0.01
        return 1.0

    def _normalize_history_points(self, points):
        if not points:
            return []
        if self._v46_history_origin is None:
            try:
                first = points[0]
                self._v46_history_origin = (float(first["x"]), float(first["y"]))
            except Exception:
                return []
        ox, oy = self._v46_history_origin
        scale = self._detect_history_scale(points)
        self._v46_history_scale = scale

        normalized = []
        previous_xy = None
        for point in points:
            try:
                raw_x = float(point["x"])
                raw_y = float(point["y"])
                phi = float(point.get("phi", 0) or 0)
                protocol_id = int(point.get("id", 0) or 0)
            except Exception:
                continue
            x = (raw_x - ox) * scale
            y = (raw_y - oy) * scale
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(phi)):
                continue
            xy = (x, y)
            if previous_xy is not None and math.hypot(x - previous_xy[0], y - previous_xy[1]) < 1e-9:
                continue
            previous_xy = xy
            normalized.append({
                "protocol_id": protocol_id,
                "x": x,
                "y": y,
                "phi": phi,
                "update": int(point.get("update", 1) or 0),
                "history_time": point.get("history_time"),
                "raw_x": raw_x,
                "raw_y": raw_y,
            })
        return normalized

    def _apply_history_result(self, result):
        self._v46_history_queries = dict((result or {}).get("queries") or {})
        self._v46_history_winner = (result or {}).get("winner")
        self._v46_history_records = int((result or {}).get("records_with_path", 0) or 0)
        self._v46_history_newest = (result or {}).get("newest")
        points = list((result or {}).get("points") or [])
        self._v46_history_raw_points = len(points)
        self._v46_history_distinct_points = self._distinct_xy_count(points)
        self._v46_history_new_last = 0
        if points:
            last = points[-1]
            try:
                self._v46_history_last_raw = (
                    float(last["x"]), float(last["y"]), float(last.get("phi", 0) or 0)
                )
            except Exception:
                self._v46_history_last_raw = None

        # Una sola pose no es movimiento.
        if self._v46_history_distinct_points < 2:
            return

        normalized = self._normalize_history_points(points)
        if len(normalized) < 2 or self._distinct_xy_count(normalized) < 2:
            return

        phase = int(getattr(self, "mapping_phase", 0) or 0)
        if phase not in (1, 2) or (phase == 2 and getattr(self, "mapping_transitioning", False)):
            return
        if not self.local_map:
            return

        new_samples = []
        for point in normalized:
            signature = (
                int(point.get("protocol_id", 0) or 0),
                round(float(point["x"]), 6),
                round(float(point["y"]), 6),
                round(float(point.get("phi", 0) or 0), 6),
            )
            if signature in self._v46_history_seen:
                continue
            self._v46_history_seen.add(signature)
            self._v46_history_point_id += 1
            new_samples.append({
                "id": self._v46_history_point_id,
                "x": float(point["x"]),
                "y": float(point["y"]),
                "phi": float(point.get("phi", 0) or 0),
                "update": int(point.get("update", 1) or 0),
            })

        if not new_samples:
            return

        self._v46_history_new_last = len(new_samples)
        self._v46_history_applied_points += len(new_samples)
        self._v46_history_motion_confirmed = True
        self._v34_motion_confirmed = True
        self._v34_position_changes = max(
            int(getattr(self, "_v34_position_changes", 0) or 0),
            max(1, self._v46_history_distinct_points - 1),
        )

        self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
        self.local_map.merge_trajectory(new_samples, phase=phase)

        last = normalized[-1]
        relative = {
            "x": float(last["x"]),
            "y": float(last["y"]),
            "angle": float(last.get("phi", 0) or 0),
        }
        self._v46_history_last_relative = (relative["x"], relative["y"], relative["angle"])
        self.local_map.set_robot(relative)

        if phase == 1:
            self._rebuild_mapped_walls(force=False)

        try:
            self.map_status_label.configure(
                text=(
                    f"Trayectoria Xiaomi Cloud 10/5 · X {relative['x']:+.3f} m · "
                    f"Y {relative['y']:+.3f} m · {self._v46_history_applied_points} puntos reales"
                )
            )
            self.mapping_steps_info.configure(
                text="Fuente: historial Xiaomi Cloud 10.5 · no se usa 10/22 para inferir movimiento"
            )
        except Exception:
            pass
        self._render_maps()

    # ------------------------------------------------------------- eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "cloud_history_v46":
            self._v46_history_worker = False
            self._v46_history_ok_reads += 1
            self._v46_history_error = None
            result = payload[0] if payload else {}
            self._apply_history_result(result)
            return
        if kind == "cloud_history_error_v46":
            self._v46_history_worker = False
            self._v46_history_error = str(payload[0]) if payload else "Error historial Cloud 10.5"
            return
        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _query_diag_text(queries, label):
        item = (queries or {}).get(label) or {}
        if not item:
            return "sin consulta"
        if not item.get("ok"):
            return f"ERROR {item.get('error') or 'sin detalle'}"
        return (
            f"records={int(item.get('records', 0) or 0)} · "
            f"con trayectoria={int(item.get('records_with_path', 0) or 0)} · "
            f"puntos={int(item.get('points', 0) or 0)} · "
            f"newest={item.get('newest')!r} · preview={item.get('preview') or '—'}"
        )

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V46 ACTIVO · historial Cloud de cur-cleaning-path\n"
            "=============================================================\n"
            "fuente buscada: user/get_user_device_data · key=10.5\n"
            "orden: prop:10.5 (correcto para cur-cleaning-path) · event:10.5 sólo fallback\n"
            f"inicio de fase epoch: {self._v46_phase_started_at:.3f} · fase: {self._v46_phase!r}\n"
            f"consultas historial correctas: {self._v46_history_ok_reads}\n"
            f"prop:10.5: {self._query_diag_text(self._v46_history_queries, 'prop:10.5')}\n"
            f"event:10.5: {self._query_diag_text(self._v46_history_queries, 'event:10.5')}\n"
            f"ganador: {self._v46_history_winner or '—'} · registros útiles: {self._v46_history_records}\n"
            f"puntos crudos: {self._v46_history_raw_points} · distintos X/Y: {self._v46_history_distinct_points}\n"
            f"puntos aplicados acumulados: {self._v46_history_applied_points} · nuevos última lectura: {self._v46_history_new_last}\n"
            f"escala detectada: {self._v46_history_scale:g} · origen raw primera pose: {self._v46_history_origin!r}\n"
            f"última pose raw: {self._v46_history_last_raw!r}\n"
            f"última pose relativa: {self._v46_history_last_relative!r}\n"
            f"movimiento confirmado por historial: {self._v46_history_motion_confirmed}\n"
            f"error historial: {self._v46_history_error or '—'}\n"
            "seguridad: una muestra aislada no mueve el robot; 10/22=255_255 sigue ignorado\n"
            "upload/mapa: V45 se conserva; con cur-map-id=0 no se ejecutan acciones de upload por ID\n"
            "nota: el blob FDS/IJAI queda como fallback; v46 no necesita descifrarlo para obtener trayectoria\n\n"
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

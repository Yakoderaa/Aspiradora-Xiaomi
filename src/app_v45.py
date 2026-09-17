import math
import threading

import app_v44
from xiaomi_e10_map_v45 import XiaomiE10MapV45
from xiaomi_e10_probe_v45 import XiaomiE10ProbeV45


class App(app_v44.App):
    """v45: elimina el salto falso por 10/22=255_255 y usa 10/15-10/16.

    El diagnóstico v44 demostró que el robot 10/24 siguió fijo en 59_60; lo que
    cambió fue chargingbase 10/22 de 60_60 a 255_255. Restar una base sentinela
    hizo aparecer un movimiento inexistente (-196,-195). V45 ancla la base a la
    primera lectura válida y sólo permite confirmar movimiento si cambia el
    ROBOT o aparece una trayectoria real.
    """

    def __init__(self):
        self._v45_local_base_anchor = None
        self._v45_cloud_base_anchor = None
        self._v45_cloud_last_robot = None
        self._v45_cloud_robot_changes = 0
        self._v45_cloud_base_sentinels = 0
        super().__init__()

    # ----------------------------------------------------------- conexión v45
    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10ProbeV45(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui("connect_error", str(exc).strip() or "El robot no respondió correctamente.", quiet)

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------- cliente Cloud
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV45(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # ------------------------------------------------------------ sentinelas
    @staticmethod
    def _base_xy_valid(point):
        if point is None:
            return False
        try:
            x = float(point[0]) if not isinstance(point, dict) else float(point["x"])
            y = float(point[1]) if not isinstance(point, dict) else float(point["y"])
        except Exception:
            return False
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
        xi, yi = int(round(x)), int(round(y))
        if abs(x - xi) < 1e-9 and abs(y - yi) < 1e-9 and xi == yi and xi in {-1, 255, 65535, 4294967295}:
            return False
        return True

    @staticmethod
    def _dict_xy(point):
        if not isinstance(point, dict):
            return None
        try:
            return float(point["x"]), float(point["y"])
        except Exception:
            return None

    def _relative_robot_from_state(self, state):
        """Origen local estable: los cambios de base nunca cuentan como movimiento."""
        if not isinstance(state, dict):
            return None
        robot = state.get("robot")
        base = state.get("charging_base")
        robot_xy = self._dict_xy(robot)
        base_xy = self._dict_xy(base)
        if robot_xy is None or base_xy is None or not self._base_xy_valid(base):
            return None

        if self._v45_local_base_anchor is None:
            self._v45_local_base_anchor = base_xy
        bx, by = self._v45_local_base_anchor
        return {
            "x": robot_xy[0] - bx,
            "y": robot_xy[1] - by,
            "angle": float(robot.get("angle", 0) or 0),
        }

    # ---------------------------------------------------- MIoT cloud seguro
    def _consume_cloud_position(self, robot_xy, base_xy):
        """V36 confirmaba movimiento sobre robot-base; v45 fija la base.

        De este modo 60_60 -> 255_255 no puede volver a disparar al icono. La
        detección heredada sólo ve cambios relativos si cambió 10/24 de verdad.
        """
        if robot_xy is None:
            return
        try:
            current_robot = (float(robot_xy[0]), float(robot_xy[1]))
        except Exception:
            return

        previous_robot = self._v45_cloud_last_robot
        self._v45_cloud_last_robot = current_robot
        if previous_robot is not None and math.hypot(
            current_robot[0] - previous_robot[0],
            current_robot[1] - previous_robot[1],
        ) >= self.CLOUD_MOVE_EPSILON_M:
            self._v45_cloud_robot_changes += 1

        if self._base_xy_valid(base_xy):
            if self._v45_cloud_base_anchor is None:
                self._v45_cloud_base_anchor = (float(base_xy[0]), float(base_xy[1]))
        elif base_xy is not None:
            self._v45_cloud_base_sentinels += 1

        if self._v45_cloud_base_anchor is None:
            return
        return super()._consume_cloud_position(robot_xy, self._v45_cloud_base_anchor)

    # --------------------------------------------------------------- sesión
    def start_new_mapping(self):
        self._v45_local_base_anchor = None
        self._v45_cloud_base_anchor = None
        self._v45_cloud_last_robot = None
        self._v45_cloud_robot_changes = 0
        self._v45_cloud_base_sentinels = 0
        self._v36_cloud_last_xy = None
        self._v36_cloud_changes = 0
        self._v36_cloud_motion_confirmed = False
        return super().start_new_mapping()

    def start_interior_mapping(self):
        self._v45_local_base_anchor = None
        self._v45_cloud_base_anchor = None
        self._v45_cloud_last_robot = None
        self._v36_cloud_last_xy = None
        return super().start_interior_mapping()

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _safe_short(value, limit=160):
        try:
            text = repr(value)
        except Exception:
            text = str(value)
        return text if len(text) <= limit else text[:limit] + "…"

    def _diagnostic_text(self):
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        client = getattr(self, "_v40_client", None)
        upload = dict(getattr(client, "last_v45_upload_diagnostics", {}) or {}) if client else {}
        inherited = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V45 ACTIVO · movimiento seguro + rango real 10/12\n"
            "============================================================\n"
            "corrección salto: 10/22=255_255 es sentinela; una base que cambia NO confirma movimiento\n"
            "regla movimiento: sólo cambio de 10/24 o trayectoria real puede mover el robot\n"
            f"ancla base local: {self._v45_local_base_anchor!r}\n"
            f"10/15 start-cleaning-point crudo: {state.get('path_bound_start_raw')!r}\n"
            f"10/16 end-cleaning-point crudo: {state.get('path_bound_end_raw')!r}\n"
            f"rango usado por 10/12: {state.get('path_bound_range')!r} · fuente: {state.get('path_bound_source') or '—'}\n"
            f"code acción 10/12: {state.get('path_bound_action_code')!r}\n"
            f"salida 10/12 con rango real: {self._safe_short(state.get('path_bound_action_raw'))}\n"
            f"puntos 10/12 rango real: {int(state.get('path_bound_action_points', 0) or 0)}\n"
            f"sentinelas base ignorados LAN: {int(state.get('base_sentinels_ignored', 0) or 0)}\n"
            f"cambios de base ignorados LAN: {int(state.get('base_changes_ignored', 0) or 0)}\n"
            f"cambios reales 10/24 Cloud: {self._v45_cloud_robot_changes}\n"
            f"sentinelas base ignorados Cloud: {self._v45_cloud_base_sentinels}\n"
            "upload Cloud B112: sólo 10/14 o 10/2 con map_id>0; 10/18, 10/15 y 10/6 eliminados\n"
            f"upload omitido: {bool(upload.get('skipped', False))} · map_id: {upload.get('map_id')!r}\n"
            f"motivo upload: {upload.get('reason') or '—'}\n"
            f"map-privacy tocada por V45: False · lectura actual: {upload.get('privacy_now')!r}\n"
            f"movimiento final confirmado: {bool(getattr(self, '_v34_motion_confirmed', False))}\n\n"
            + inherited
        )


if __name__ == "__main__":
    app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

import math
import time

import app_v116
import app_v9


class App(app_v116.App):
    """V117: pose 10/24 viva sobre el mapa Xiaomi guardado durante limpieza."""

    RAW_TO_METERS = 0.10
    MAX_REASONABLE_DELTA_METERS = 20.0

    def __init__(self):
        self._v117_live_pose = None
        self._v117_live_base = {"x": 0.0, "y": 0.0, "angle": 0.0}
        self._v117_live_pose_updates = 0
        self._v117_live_pose_changes = 0
        self._v117_live_pose_rejects = 0
        self._v117_live_pose_key = None
        self._v117_last_raw_robot = None
        self._v117_last_raw_base = None
        self._v117_last_pose_source = "—"
        self._v117_main_pose_renders = 0
        self._v117_thumb_pose_renders = 0
        self._v117_last_pose_at = 0.0
        super().__init__()

    @classmethod
    def _v117_pose_from_state(cls, state, physical_status=None):
        if not isinstance(state, dict):
            return None

        robot = state.get("robot")
        base = state.get("charging_base")
        if not isinstance(robot, dict):
            return None

        try:
            rx = float(robot["x"])
            ry = float(robot["y"])
            angle = float(
                robot.get("angle", robot.get("phi", 0.0)) or 0.0
            )
        except Exception:
            return None

        try:
            bx = float(base["x"])
            by = float(base["y"])
            if (
                not math.isfinite(bx)
                or not math.isfinite(by)
                or bx >= 200.0
                or by >= 200.0
            ):
                raise ValueError
        except Exception:
            bx = 60.0
            by = 60.0

        if not all(math.isfinite(v) for v in (rx, ry, bx, by, angle)):
            return None

        try:
            status = int(physical_status)
        except Exception:
            status = None

        if status == 4:
            return {"x": 0.0, "y": 0.0, "angle": 0.0}

        x = (rx - bx) * cls.RAW_TO_METERS
        y = (by - ry) * cls.RAW_TO_METERS
        mapped_angle = -angle

        if (
            abs(x) > cls.MAX_REASONABLE_DELTA_METERS
            or abs(y) > cls.MAX_REASONABLE_DELTA_METERS
        ):
            return None

        return {
            "x": float(x),
            "y": float(y),
            "angle": float(mapped_angle),
        }

    def _v117_pose_overlay_enabled(self):
        if bool(getattr(self, "_v115_global_clean_active", False)):
            return True
        try:
            status = int(getattr(self, "_v94_last_status_code", -1))
        except Exception:
            status = -1
        return status in (2, 3, 4, 5, 6, 7)

    def _v117_capture_raw_diag(self, state):
        probe = (state or {}).get("service10_probe") or {}
        values = probe.get("values") or {}
        self._v117_last_raw_base = values.get(
            22,
            values.get("22", (state or {}).get("charging_base")),
        )
        self._v117_last_raw_robot = values.get(
            24,
            values.get("24", (state or {}).get("robot")),
        )

    def _v117_update_live_pose(self, state):
        if not isinstance(state, dict):
            return False

        self._v117_capture_raw_diag(state)

        try:
            status = int(getattr(self, "_v94_last_status_code", -1))
        except Exception:
            status = -1

        if not self._v117_pose_overlay_enabled():
            return False

        pose = self._v117_pose_from_state(state, status)
        if pose is None:
            self._v117_live_pose_rejects += 1
            return False

        key = (
            round(float(pose["x"]), 4),
            round(float(pose["y"]), 4),
            round(float(pose.get("angle", 0.0)), 4),
        )
        self._v117_live_pose_updates += 1
        if key != self._v117_live_pose_key:
            self._v117_live_pose_changes += 1
            self._v117_live_pose_key = key

        self._v117_live_pose = dict(pose)
        self._v117_live_base = {"x": 0.0, "y": 0.0, "angle": 0.0}
        self._v117_last_pose_at = time.monotonic()
        self._v117_last_pose_source = (
            "10/24 - 10/22 · 0.10 m/raw · Y reflejado como grid V107"
        )
        return True

    def _apply_map_state(self, state):
        # Capturamos ANTES de V73: esa capa descarta robot/base cuando
        # mapping_active=False, que es por qué V116 conservaba la planta pero
        # perdía la aspiradora durante una limpieza normal.
        self._v117_update_live_pose(state)
        return super()._apply_map_state(state)

    def _v117_snapshot_with_live_pose(self, snapshot):
        source = dict(snapshot or {})
        if not self._v117_pose_overlay_enabled():
            return source

        source["charging_base"] = dict(self._v117_live_base)
        if isinstance(self._v117_live_pose, dict):
            source["robot"] = dict(self._v117_live_pose)
        else:
            source["robot"] = dict(self._v117_live_base)
        return source

    def _render_map_canvas(self, canvas, snapshot):
        source = self._v117_snapshot_with_live_pose(snapshot)
        result = super()._render_map_canvas(canvas, source)
        if self._v117_pose_overlay_enabled():
            try:
                if canvas is getattr(self, "map_canvas", None):
                    self._v117_main_pose_renders += 1
            except Exception:
                pass
        return result

    def _v70_render_thumbnail(
        self,
        canvas,
        snapshot,
        plan=None,
        active=False,
    ):
        source = self._v117_snapshot_with_live_pose(snapshot)
        result = super()._v70_render_thumbnail(
            canvas,
            source,
            plan,
            active,
        )
        if self._v117_pose_overlay_enabled():
            self._v117_thumb_pose_renders += 1
        return result

    def start_clean(self):
        self._v117_live_pose = None
        self._v117_live_pose_key = None
        self._v117_last_pose_source = "esperando primera lectura 10/24"
        return super().start_clean()

    @staticmethod
    def _v117_age(now, value):
        try:
            value = float(value or 0.0)
            if value <= 0.0:
                return "—"
            return f"{max(0.0, now - value):.1f}s"
        except Exception:
            return "—"

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()
        vacuum = getattr(self, "vacuum", None)
        locate_calls = (
            int(getattr(vacuum, "_locate_calls", 0) or 0)
            if vacuum is not None
            else 0
        )
        last_locate = (
            float(getattr(vacuum, "_last_locate_at", 0.0) or 0.0)
            if vacuum is not None
            else 0.0
        )

        lines = [
            "DIAGNÓSTICO V117 ACTIVO · pose viva sobre mapa guardado",
            "=======================================================",
            (
                f"pose overlay={self._v117_pose_overlay_enabled()} · "
                f"actualizaciones={self._v117_live_pose_updates} · "
                f"cambios={self._v117_live_pose_changes} · "
                f"rechazos={self._v117_live_pose_rejects}"
            ),
            f"raw 10/24 robot={self._v117_last_raw_robot!r}",
            f"raw 10/22 base={self._v117_last_raw_base!r}",
            f"pose convertida={self._v117_live_pose or '—'}",
            (
                f"fuente={self._v117_last_pose_source} · "
                f"edad={self._v117_age(now, self._v117_last_pose_at)}"
            ),
            (
                f"renders pose: mapa grande={self._v117_main_pose_renders} · "
                f"miniaturas={self._v117_thumb_pose_renders}"
            ),
            (
                f"Hacer sonar/locate emitidos por ESTA app={locate_calls} · "
                f"último hace={self._v117_age(now, last_locate)}"
            ),
            "regla V117: V73 puede descartar pose fuera de mapping, pero V117 la captura antes y la superpone después",
            "regla V117: 10/24-10/22 usa 0.10 m/raw y el mismo espejo Y del grid final V107",
            "regla V117: el seguimiento vivo sólo cambia base/robot del frame; jamás escribe native_grid ni redibuja la planta",
            "regla V117: un pitido sólo se atribuye a Hacer sonar si locate_calls aumenta",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

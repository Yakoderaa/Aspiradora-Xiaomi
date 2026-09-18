import math
import time

import app_v75


class App(app_v75.App):
    """V76: una sola trayectoria + antiatasco conservador."""

    STALL_GRACE_AFTER_START_SECONDS = 45.0
    STALL_GRACE_AFTER_RECOVERY_SECONDS = 35.0
    STALL_WINDOW_SECONDS = 30.0
    STALL_MIN_SECONDS = 24.0
    STALL_POSITION_SPAN = 0.45
    STALL_MIN_ANGLE_TRAVEL = 7.5
    STALL_MIN_DIRECTION_REVERSALS = 3
    STALL_MIN_POSE_SAMPLES = 12
    STALL_TURN_DELTA_MIN = 0.08
    STALL_COOLDOWN_SECONDS = 60.0

    REPEAT_WINDOW_SECONDS = 240.0
    REPEAT_MIN_SAMPLES = 140
    REPEAT_POSITION_SPAN = 8.0

    def __init__(self):
        self._v76_session_started_at = None
        self._v76_last_resume_at = None
        self._v76_last_stall_span = None
        self._v76_last_stall_angle = None
        self._v76_last_stall_reversals = 0
        self._v76_stall_checks = 0
        self._v76_stall_grace_blocks = 0
        self._v76_duplicate_points_blocked = 0
        super().__init__()

    # ===================================================== una sola trayectoria
    def _v76_reset_legacy_motion_state(self):
        # app_v34 llevaba su propia polilínea paralela. En el flujo V74+ esa
        # capa ya no es necesaria porque V55/V73 entregan la trayectoria real
        # completa. Además podía arrastrar _v34_last_relative entre sesiones.
        self._v34_last_relative = None
        self._v34_motion_confirmed = False
        self._v34_position_changes = 0
        self._v34_point_id = int(getattr(self, "LIVE_POINT_ID_BASE", 100000))

        # app_v33 también conserva puntos LIVE históricos por fase.
        try:
            self._live_last_point = {1: None, 2: None}
        except Exception:
            pass
        try:
            self._live_point_id = {1: 0, 2: 0}
        except Exception:
            pass

    def _v74_reset_session(self):
        self._v76_reset_legacy_motion_state()
        self._v76_session_started_at = None
        self._v76_last_resume_at = None
        self._v76_last_stall_span = None
        self._v76_last_stall_angle = None
        self._v76_last_stall_reversals = 0
        self._v76_stall_checks = 0
        self._v76_stall_grace_blocks = 0
        self._v76_duplicate_points_blocked = 0
        return super()._v74_reset_session()

    def _record_relative_motion(self, relative):
        """Desactiva la segunda trayectoria heredada de app_v34.

        Conservamos sus contadores/pose para diagnósticos y render, pero no
        volvemos a insertar puntos en LocalMapStore. V73 es la única fuente.
        """
        try:
            current = (
                float(relative["x"]),
                float(relative["y"]),
                float(relative.get("angle", 0.0) or 0.0),
            )
        except Exception:
            return 0

        previous = getattr(self, "_v34_last_relative", None)
        self._v34_last_relative = current
        if previous is None:
            return 0

        try:
            distance = math.hypot(
                float(current[0]) - float(previous[0]),
                float(current[1]) - float(previous[1]),
            )
        except Exception:
            distance = 0.0

        if distance >= float(getattr(self, "MOTION_EPSILON", 0.015)):
            self._v34_motion_confirmed = True
            self._v34_position_changes = int(
                getattr(self, "_v34_position_changes", 0) or 0
            ) + 1
            self._v76_duplicate_points_blocked += 1
        return 0

    # ======================================================== gracia antiatasco
    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started":
            self._v76_session_started_at = time.monotonic()
            self._v76_last_resume_at = self._v76_session_started_at

        if kind == "v73_stall_recovered":
            self._v76_last_resume_at = time.monotonic()

        return super()._handle_ui_event(kind, payload)

    @staticmethod
    def _v76_turn_reversals(samples, min_delta):
        signs = []
        for a, b in zip(samples, samples[1:]):
            delta = app_v75.app_v74.app_v73.App._v73_angle_delta(a[3], b[3])
            if abs(delta) < float(min_delta):
                continue
            sign = 1 if delta > 0 else -1
            if not signs or signs[-1] != sign:
                signs.append(sign)
        return max(0, len(signs) - 1)

    def _v76_in_stall_grace(self, now):
        started = self._v76_session_started_at
        resumed = self._v76_last_resume_at

        if started is not None:
            if now - started < self.STALL_GRACE_AFTER_START_SECONDS:
                return True

        if resumed is not None and resumed != started:
            if now - resumed < self.STALL_GRACE_AFTER_RECOVERY_SECONDS:
                return True

        return False

    def _v73_track_motion(self, robot, phase, active):
        now = time.monotonic()

        if not active or phase != 2:
            self._v73_pose_window.clear()
            return
        if bool(getattr(self, "mapping_transitioning", False)):
            self._v73_pose_window.clear()
            return

        try:
            sample = (
                now,
                float(robot["x"]),
                float(robot["y"]),
                float(robot.get("angle", 0.0) or 0.0),
            )
        except Exception:
            return

        self._v73_pose_window.append(sample)
        cutoff = now - max(self.REPEAT_WINDOW_SECONDS + 10.0, 270.0)
        while self._v73_pose_window and self._v73_pose_window[0][0] < cutoff:
            self._v73_pose_window.popleft()

        if self._v73_recovery_active:
            return
        if now - float(self._v73_last_recovery_at or 0.0) < self.STALL_COOLDOWN_SECONDS:
            return

        if self._v76_in_stall_grace(now):
            self._v76_stall_grace_blocks += 1
            return

        short = [
            item
            for item in self._v73_pose_window
            if item[0] >= now - self.STALL_WINDOW_SECONDS
        ]

        if (
            len(short) >= self.STALL_MIN_POSE_SAMPLES
            and short[-1][0] - short[0][0] >= self.STALL_MIN_SECONDS
        ):
            self._v76_stall_checks += 1
            span = self._v73_span(short)
            angle_travel = sum(
                abs(self._v73_angle_delta(a[3], b[3]))
                for a, b in zip(short, short[1:])
            )
            reversals = self._v76_turn_reversals(
                short,
                self.STALL_TURN_DELTA_MIN,
            )

            self._v76_last_stall_span = span
            self._v76_last_stall_angle = angle_travel
            self._v76_last_stall_reversals = reversals

            # Un giro normal junto a una pared puede acumular mucho ángulo y
            # avanzar ~1 unidad. Un atasco real observado por el usuario oscila
            # derecha/izquierda sin salir del mismo punto. Exigimos las 3 firmas.
            if (
                span <= self.STALL_POSITION_SPAN
                and angle_travel >= self.STALL_MIN_ANGLE_TRAVEL
                and reversals >= self.STALL_MIN_DIRECTION_REVERSALS
            ):
                self._v73_schedule_recovery(
                    phase,
                    (
                        "oscilación real sin avance "
                        f"(span={span:.2f}, giro={angle_travel:.1f} rad, "
                        f"reversiones={reversals})"
                    ),
                )
                return

        if phase == 2 and not self._v73_repeat_triggered:
            long_window = [
                item
                for item in self._v73_pose_window
                if item[0] >= now - self.REPEAT_WINDOW_SECONDS
            ]
            if (
                len(long_window) >= self.REPEAT_MIN_SAMPLES
                and long_window[-1][0] - long_window[0][0]
                >= self.REPEAT_WINDOW_SECONDS - 15.0
            ):
                span = self._v73_span(long_window)
                if span <= self.REPEAT_POSITION_SPAN:
                    self._v73_repeat_triggered = True
                    self._v73_schedule_recovery(
                        phase,
                        (
                            f"sector repetido durante ~{int(self.REPEAT_WINDOW_SECONDS)} s "
                            f"(span={span:.2f})"
                        ),
                    )

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()
        start_grace = 0.0
        resume_grace = 0.0
        if self._v76_session_started_at is not None:
            start_grace = max(
                0.0,
                self.STALL_GRACE_AFTER_START_SECONDS
                - (now - self._v76_session_started_at),
            )
        if (
            self._v76_last_resume_at is not None
            and self._v76_last_resume_at != self._v76_session_started_at
        ):
            resume_grace = max(
                0.0,
                self.STALL_GRACE_AFTER_RECOVERY_SECONDS
                - (now - self._v76_last_resume_at),
            )

        lines = [
            "DIAGNÓSTICO V76 ACTIVO · trayectoria única + antiatasco tolerante",
            "==================================================================",
            f"puntos duplicados V34 bloqueados: {self._v76_duplicate_points_blocked}",
            f"gracia inicial restante: {start_grace:.1f}s · gracia post-recovery: {resume_grace:.1f}s",
            f"checks de atasco: {self._v76_stall_checks} · bloqueados por gracia={self._v76_stall_grace_blocks}",
            f"último span corto: {self._v76_last_stall_span!r} · giro={self._v76_last_stall_angle!r} · reversiones={self._v76_last_stall_reversals}",
            (
                "umbrales V76: "
                f"{self.STALL_MIN_SECONDS:.0f}s / span≤{self.STALL_POSITION_SPAN:.2f} / "
                f"giro≥{self.STALL_MIN_ANGLE_TRAVEL:.1f} rad / "
                f"reversiones≥{self.STALL_MIN_DIRECTION_REVERSALS}"
            ),
            "regla V76: LocalMapStore recibe trayectoria sólo desde V73/V55; V34 ya no inserta una segunda polilínea",
            "regla V76: el antiatasco no actúa al arrancar/reanudar y exige oscilación derecha/izquierda real sin desplazamiento",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

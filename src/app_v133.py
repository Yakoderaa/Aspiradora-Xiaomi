import time

import app_v132
import app_v9


class App(app_v132.App):
    """V133: EDGE V132 + reacople progresivo para base con rampa."""

    DOCK_GUARD_STABLE_SECONDS = 4.5
    DOCK_NEAR_STALL_SAMPLES = 4
    DOCK_MAX_RETRIES = 4
    DOCK_RETRY_REVERSE_SECONDS = 1.55

    DOCK_RETRY_REVERSE_PROFILE = (1.55, 2.05, 2.45, 2.80)
    DOCK_RETRY_TURN_PROFILE = (0.00, 0.18, 0.18, 0.28)

    def __init__(self):
        self._v133_dock_maneuvers = []
        self._v133_last_dock_maneuver = None
        self._v133_dock_failures = 0
        self._v133_dock_successes = 0
        super().__init__()

    def _v133_dock_profile(self, attempt):
        index = max(0, min(int(attempt) - 1, len(self.DOCK_RETRY_REVERSE_PROFILE) - 1))
        reverse_s = float(self.DOCK_RETRY_REVERSE_PROFILE[index])
        turn_s = float(self.DOCK_RETRY_TURN_PROFILE[index])
        if turn_s <= 0:
            turn = None
            turn_name = "sin giro"
        else:
            turn = 2 if int(attempt) % 2 == 0 else 3
            turn_name = "izquierda" if turn == 2 else "derecha"
        return reverse_s, turn_s, turn, turn_name

    def _v73_dock_guard_worker(self, vacuum, serial, reason):
        deadline = time.monotonic() + self.DOCK_GUARD_SECONDS
        direct_samples = 0
        retries = 0
        last_pose_key = None
        stable_since = None
        near_samples = 0

        while time.monotonic() < deadline:
            if serial != self._v73_dock_guard_serial:
                return
            if vacuum is not getattr(self, "vacuum", None):
                return

            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                raw_robot = state.get("robot")
            except Exception:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            now = time.monotonic()
            at_base, _ = self._v67_base_evidence(status, None)
            at_base = bool(at_base and fault == 0)
            direct_samples = direct_samples + 1 if at_base else 0
            if direct_samples >= self.BASE_CONFIRM_SAMPLES:
                self._v133_dock_successes += 1
                self._post_ui("v73_dock_guard_done", serial)
                return

            pose_key = self._v69_pose_key(vacuum, raw_robot)
            if pose_key is not None and pose_key == last_pose_key:
                if stable_since is None:
                    stable_since = now
            else:
                last_pose_key = pose_key
                stable_since = now if pose_key is not None else None

            stable_seconds = (
                now - stable_since
                if stable_since is not None and pose_key is not None
                else 0.0
            )

            distance = self._v71_raw_distance_to_origin(raw_robot)
            threshold = self._v71_return_limit()
            departed_enough = (
                float(self._v71_session_max_departure or 0.0)
                >= self.RETURN_MIN_DEPARTURE
            )
            near_origin = (
                distance is not None
                and departed_enough
                and distance <= threshold
                and fault == 0
            )
            near_samples = near_samples + 1 if near_origin and not at_base else 0

            stalled_on_dock = (
                status == 3
                and fault == 0
                and (
                    near_samples >= self.DOCK_NEAR_STALL_SAMPLES
                    or stable_seconds >= self.DOCK_GUARD_STABLE_SECONDS
                )
            )
            if not stalled_on_dock:
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            if retries >= self.DOCK_MAX_RETRIES:
                try:
                    vacuum.stop()
                except Exception:
                    pass
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                self._v133_dock_failures += 1
                self._post_ui(
                    "v73_dock_guard_failed",
                    serial,
                    f"{reason}; V133 agotó {self.DOCK_MAX_RETRIES} maniobras sin status=4",
                )
                return

            retries += 1
            reverse_s, turn_s, turn, turn_name = self._v133_dock_profile(retries)
            maneuver = {
                "attempt": retries,
                "reverse_s": reverse_s,
                "turn_s": turn_s,
                "turn": turn_name,
                "status_before": status,
                "distance_before": distance,
                "reason": str(reason),
            }
            self._v133_last_dock_maneuver = dict(maneuver)
            self._v133_dock_maneuvers = (
                list(self._v133_dock_maneuvers) + [dict(maneuver)]
            )[-12:]

            try:
                vacuum.stop()
            except Exception:
                pass
            time.sleep(0.30)

            try:
                vacuum.manual(4)
                time.sleep(reverse_s)
                vacuum.manual(5)
            except Exception:
                try:
                    vacuum.manual(5)
                except Exception:
                    pass

            time.sleep(0.25)

            if turn is not None and turn_s > 0:
                try:
                    vacuum.manual(turn)
                    time.sleep(turn_s)
                    vacuum.manual(5)
                except Exception:
                    try:
                        vacuum.manual(5)
                    except Exception:
                        pass
                time.sleep(0.25)

            try:
                vacuum.dock()
            except Exception:
                pass

            self._post_ui(
                "v73_dock_guard_retry",
                serial,
                retries,
                reason,
            )
            direct_samples = 0
            near_samples = 0
            last_pose_key = None
            stable_since = None
            time.sleep(1.2)

        if serial == self._v73_dock_guard_serial:
            try:
                vacuum.stop()
            except Exception:
                pass
            try:
                vacuum.manual(5)
            except Exception:
                pass
            self._v133_dock_failures += 1
            self._post_ui(
                "v73_dock_guard_failed",
                serial,
                f"{reason}; vigilancia V133 agotada sin confirmar status=4",
            )

    def _handle_ui_event(self, kind, payload):
        result = super()._handle_ui_event(kind, payload)

        if kind in ("v73_dock_guard_retry", "v73_dock_retry"):
            attempt = None
            try:
                attempt = int(payload[1] if kind == "v73_dock_guard_retry" else payload[0])
            except Exception:
                pass
            if attempt is not None:
                reverse_s, turn_s, _, turn_name = self._v133_dock_profile(attempt)
                extra = (
                    f" + giro {turn_name} {turn_s:.2f}s"
                    if turn_s > 0
                    else ""
                )
                self._set_banner(
                    f"Reacople {attempt}/{self.DOCK_MAX_RETRIES} · "
                    f"retroceso {reverse_s:.2f}s{extra} · buscando la base otra vez."
                )

        elif kind == "v73_dock_guard_done":
            status = self._v67_int(getattr(self, "_v94_last_status_code", None))
            if status == 4:
                self._set_banner(
                    "Acople finalizado · proceso finalizó con contacto de carga confirmado."
                )

        elif kind == "v73_dock_guard_failed":
            self._set_banner(
                "Acople finalizado con fallo · proceso finalizó sin contacto de carga; ruedas detenidas."
            )

        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V133 ACTIVO · EDGE V132 + reacople progresivo",
            "==========================================================",
            (
                "reacople V133: estable="
                f"{self.DOCK_GUARD_STABLE_SECONDS:.1f}s · muestras="
                f"{self.DOCK_NEAR_STALL_SAMPLES} · máximo="
                f"{self.DOCK_MAX_RETRIES}"
            ),
            f"perfil retroceso={self.DOCK_RETRY_REVERSE_PROFILE}",
            f"perfil giro={self.DOCK_RETRY_TURN_PROFILE}",
            f"última maniobra={self._v133_last_dock_maneuver or '—'}",
            f"historial maniobras={self._v133_dock_maneuvers or '—'}",
            (
                f"resultados: acoples confirmados={self._v133_dock_successes} · "
                f"fallos finales={self._v133_dock_failures}"
            ),
            "regla V133: cada reintento toma más carrera que el anterior",
            "regla V133: desde el segundo intento alterna una corrección angular pequeña antes de dock()",
            "regla V133: status=4 corta la secuencia inmediatamente; timeout/fallo detiene las ruedas",
            "regla V133: conserva íntegramente la prueba EDGE 2/1 de V132",
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

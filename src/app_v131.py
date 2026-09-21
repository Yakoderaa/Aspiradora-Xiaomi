import time

import app_v130
import app_v9


class App(app_v130.App):
    """V131: borde físico correcto + pose provisional + reacople con carrera."""

    # La base del usuario tiene rampa/inclinación. V73 ya detectaba el caso,
    # pero 0,85 s de retroceso deja al E10 demasiado cerca para tomar impulso.
    DOCK_GUARD_STABLE_SECONDS = 5.5
    DOCK_NEAR_STALL_SAMPLES = 5
    DOCK_MAX_RETRIES = 3
    DOCK_RETRY_REVERSE_SECONDS = 1.55

    def __init__(self):
        self._v131_edge_route_installed = False
        self._v131_edge_diag = {}
        self._v131_edge_primary_starts = 0
        self._v131_edge_fallback_starts = 0

        self._v131_prestart_robot_key = None
        self._v131_pose_waiting_for_change = False
        self._v131_pose_holds = 0
        self._v131_pose_releases = 0

        self._v131_dock_retry_events = 0
        self._v131_dock_confirmed_events = 0
        super().__init__()

    # =================================================== Fase 1: EDGE real
    @staticmethod
    def _v131_pose_key(vacuum, raw):
        if vacuum is None or raw is None:
            return None
        try:
            parsed = vacuum.parse_position(raw)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            return None
        try:
            return (
                round(float(parsed["x"]), 5),
                round(float(parsed["y"]), 5),
            )
        except Exception:
            return None

    def _v131_install_edge_route(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False

        app = self

        def start_mapping_exploration(confirm_timeout=5.0):
            return app._v131_start_edge_exploration(
                vacuum,
                confirm_timeout=confirm_timeout,
            )

        # Sólo se parchea ESTA instancia conectada. Las capas históricas y los
        # smoke tests de V120/V121 conservan su comportamiento original.
        vacuum.start_mapping_exploration = start_mapping_exploration
        self._v131_edge_route_installed = True
        return True

    def _v131_read_edge_state(self, vacuum):
        values = vacuum._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
        ])
        return (
            self._v67_int(values.get("status")),
            self._v67_int(values.get("sweep_type")),
        )

    def _v131_wait_edge_start(self, vacuum, timeout):
        deadline = time.monotonic() + max(0.8, float(timeout or 0.0))
        last_status = None
        last_sweep = None
        while True:
            try:
                last_status, last_sweep = self._v131_read_edge_state(vacuum)
                if last_status in (5, 6, 7):
                    if last_sweep == 2:
                        return True, last_status, last_sweep
                    # Si salió físicamente pero el firmware abandonó EDGE,
                    # detenemos el intento para no repetir una limpieza global
                    # etiquetada erróneamente como "perímetro".
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    return False, last_status, last_sweep
            except Exception:
                pass
            if time.monotonic() >= deadline:
                return False, last_status, last_sweep
            time.sleep(0.30)

    def _v131_start_edge_exploration(self, vacuum, confirm_timeout=5.0):
        """Arranca EDGE por Sweep 2/3, no por set-room-clean 7/3.

        La prueba física de V130 mostró que 7/3 ['',2,1] devolvía ACK,
        status activo y sweep_type=2, pero el E10 recorría el interior como una
        limpieza normal. V131 usa la acción nativa Start-only-sweep después de
        fijar sweep_type=2 y sólo acepta el arranque si el readback permanece 2.
        """
        vacuum._reject_mapping_during_targeted_clean(
            "start_mapping_exploration V131"
        )
        vacuum._prepare_mapping_vacuum()

        diag = {
            "route": "sweep_type=2 -> 2/3 start-only-sweep",
            "status_before": None,
            "sweep_type_before": None,
            "primary_response": None,
            "primary_error": None,
            "fallback_response": None,
            "fallback_error": None,
            "status_after": None,
            "sweep_type_after": None,
            "started_by": None,
            "success": False,
        }

        try:
            before_status, before_sweep = self._v131_read_edge_state(vacuum)
            diag["status_before"] = before_status
            diag["sweep_type_before"] = before_sweep
        except Exception as exc:
            diag["before_error"] = str(exc).strip() or type(exc).__name__

        # Repetición OFF + modo físico de borde.
        try:
            vacuum.device.set_property_by(7, 1, 0)
        except Exception as exc:
            diag["repeat_reset_error"] = (
                str(exc).strip() or type(exc).__name__
            )

        vacuum.set_sweep_type(2)

        try:
            self._v131_edge_primary_starts += 1
            diag["primary_response"] = repr(
                vacuum._send_motor_start(
                    "mapping_edge_v131/start-only-sweep",
                    2,
                    3,
                    allow_when_guarded=True,
                )
            )[:500]
        except Exception as exc:
            diag["primary_error"] = str(exc).strip() or type(exc).__name__

        ok, status, sweep = self._v131_wait_edge_start(
            vacuum,
            confirm_timeout,
        )
        diag["status_after"] = status
        diag["sweep_type_after"] = sweep
        if ok:
            diag["success"] = True
            diag["started_by"] = "2/3 start-only-sweep"
            self._v131_edge_diag = dict(diag)
            vacuum._last_mapping_exploration_diag = dict(diag)
            return diag["primary_response"]

        # Sólo si 2/3 no produjo salida física. Nunca se usa 7/3 en V131.
        if status not in (5, 6, 7):
            try:
                vacuum.set_sweep_type(2)
                self._v131_edge_fallback_starts += 1
                diag["fallback_response"] = repr(
                    vacuum._send_motor_start(
                        "mapping_edge_v131/start-sweep-fallback",
                        2,
                        1,
                        allow_when_guarded=True,
                    )
                )[:500]
            except Exception as exc:
                diag["fallback_error"] = (
                    str(exc).strip() or type(exc).__name__
                )

            ok, status, sweep = self._v131_wait_edge_start(
                vacuum,
                confirm_timeout,
            )
            diag["status_after"] = status
            diag["sweep_type_after"] = sweep
            if ok:
                diag["success"] = True
                diag["started_by"] = "2/1 start-sweep fallback"
                self._v131_edge_diag = dict(diag)
                vacuum._last_mapping_exploration_diag = dict(diag)
                return diag["fallback_response"]

        diag["error"] = (
            "El E10 no confirmó un arranque físico EDGE seguro "
            f"(status={status!r}, sweep-type={sweep!r})."
        )
        self._v131_edge_diag = dict(diag)
        vacuum._last_mapping_exploration_diag = dict(diag)
        raise RuntimeError(diag["error"])

    # ====================== pose: 10/24 previo no mueve el icono al arrancar
    def _v131_capture_prestart_pose(self):
        vacuum = getattr(self, "vacuum", None)
        self._v131_prestart_robot_key = None
        self._v131_pose_waiting_for_change = False
        if vacuum is None:
            return
        try:
            values = vacuum._get_many([("robot", 10, 24)])
            raw = values.get("robot")
            self._v131_prestart_robot_key = self._v131_pose_key(vacuum, raw)
            self._v131_pose_waiting_for_change = (
                self._v131_prestart_robot_key is not None
            )
        except Exception:
            pass

    def start_new_mapping(self):
        self._v131_install_edge_route()
        self._v131_capture_prestart_pose()
        result = super().start_new_mapping()
        if not bool(getattr(self, "mapping_active", False)):
            self._v131_pose_waiting_for_change = False
        return result

    def _v117_update_live_pose(self, state):
        if (
            bool(getattr(self, "mapping_active", False))
            and self._v131_pose_waiting_for_change
        ):
            try:
                self._v117_capture_raw_diag(state)
                vacuum = getattr(self, "vacuum", None)
                current = self._v131_pose_key(
                    vacuum,
                    self._v117_last_raw_robot,
                )
            except Exception:
                current = None

            if current is None or current == self._v131_prestart_robot_key:
                # Antes del primer 10/24 realmente nuevo, la única posición
                # honesta que conocemos es el dock. Evita el salto 0_0 vs 60_60.
                self._v117_live_pose = {
                    "x": 0.0,
                    "y": 0.0,
                    "angle": 0.0,
                }
                self._v117_live_base = {
                    "x": 0.0,
                    "y": 0.0,
                    "angle": 0.0,
                }
                self._v117_last_pose_at = time.monotonic()
                self._v117_last_pose_source = (
                    "V131 provisional: robot=dock hasta primer 10/24 post-START"
                )
                self._v131_pose_holds += 1
                return True

            self._v131_pose_waiting_for_change = False
            self._v131_pose_releases += 1

        return super()._v117_update_live_pose(state)

    # ====================================== feedback visible del reacople V131
    def _handle_ui_event(self, kind, payload):
        if kind in ("v73_dock_guard_retry", "v73_dock_retry"):
            self._v131_dock_retry_events += 1
            result = super()._handle_ui_event(kind, payload)
            attempt = None
            try:
                if kind == "v73_dock_guard_retry":
                    attempt = int(payload[1])
                else:
                    attempt = int(payload[0])
            except Exception:
                pass
            if attempt is not None:
                self._set_banner(
                    "Acople a base · sin contacto de carga. "
                    f"Retroceso largo para tomar carrera y reintento "
                    f"{attempt}/{self.DOCK_MAX_RETRIES}."
                )
            return result

        if kind == "v73_dock_guard_done":
            result = super()._handle_ui_event(kind, payload)
            status = self._v67_int(
                getattr(self, "_v94_last_status_code", None)
            )
            if status == 4:
                self._v131_dock_confirmed_events += 1
                self._set_banner(
                    "Acople finalizado · contacto de carga confirmado."
                )
            return result

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V131 ACTIVO · EDGE físico + reacople con carrera",
            "============================================================",
            (
                "Fase 1 EDGE: ruta instalada="
                f"{self._v131_edge_route_installed} · primarios="
                f"{self._v131_edge_primary_starts} · fallbacks="
                f"{self._v131_edge_fallback_starts}"
            ),
            f"último EDGE={self._v131_edge_diag or '—'}",
            (
                "pose inicial: esperando cambio="
                f"{self._v131_pose_waiting_for_change} · preSTART="
                f"{self._v131_prestart_robot_key or '—'} · holds="
                f"{self._v131_pose_holds} · liberaciones="
                f"{self._v131_pose_releases}"
            ),
            (
                "reacople: detección estable="
                f"{self.DOCK_GUARD_STABLE_SECONDS:.1f}s · muestras cerca="
                f"{self.DOCK_NEAR_STALL_SAMPLES} · retroceso="
                f"{self.DOCK_RETRY_REVERSE_SECONDS:.2f}s · máximo="
                f"{self.DOCK_MAX_RETRIES} · eventos retry="
                f"{self._v131_dock_retry_events} · confirmados="
                f"{self._v131_dock_confirmed_events}"
            ),
            "regla V131: Fase 1 no usa 7/3 set-room-clean; usa sweep_type=2 + START Sweep nativo",
            "regla V131: si el START sale con sweep_type distinto de 2, se detiene en vez de fingir un perímetro",
            "regla V131: 10/24 previo al START no desplaza el icono; robot=dock hasta ver una coordenada nueva",
            "regla V131: si llega a la rampa sin cargar, retrocede más, toma carrera y vuelve a ejecutar dock()",
            "regla V131: tras tres intentos sin carga conserva la parada de seguridad V73",
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

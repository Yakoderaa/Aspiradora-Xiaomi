import threading
import time

import app_v68
from xiaomi_e10_map_v69 import XiaomiE10MapV69


class App(app_v68.App):
    """V69: transición B112 sin 3/2 inexistente + clean-end saneado."""

    BASE_WATCH_SECONDS = 300.0
    RETURN_REASSERT_SECONDS = 30.0
    RETURN_FALLBACK_MIN_SECONDS = 75.0
    RETURN_POSE_STABLE_SECONDS = 20.0
    RETURN_IDLE_STATUS_MIN_SECONDS = 30.0

    def __init__(self):
        self._v69_transition_diag = {
            "charging_state_removed": True,
            "last_status": None,
            "last_fault": None,
            "last_battery": None,
            "return_elapsed": 0.0,
            "pose_stable_seconds": 0.0,
            "dock_reasserted": False,
            "battery_rise": 0,
            "fallback_confirmed": False,
            "fallback_mode": None,
            "fallback_reason": None,
            "confirmed_pose_key": None,
            "timeout": False,
        }
        super().__init__()

    # ---------------------------------------------------------- mapa V69
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV69(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # -------------------------------------------------- spec exacta B112
    @classmethod
    def _v67_base_evidence(cls, status, charging_state=None):
        """B112 no tiene battery 3/2. Sólo status=4 confirma carga directa."""
        status = cls._v67_int(status)
        if status == 4:
            return True, "status=4 cargando"
        return False, None

    @staticmethod
    def _v68_read_edge_state(vacuum):
        # B112 exacto: battery sólo expone 3/1 battery-level; 3/2 no existe.
        values = vacuum._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
        ])
        return {
            "status": values.get("status"),
            "sweep_type": values.get("sweep_type"),
            "charging_state": None,
        }

    @staticmethod
    def _v69_read_base_state(vacuum):
        values = vacuum._get_many([
            ("status", 2, 1),
            ("fault", 2, 2),
            ("battery", 3, 1),
            ("robot", 10, 24),
            ("charging_base", 10, 22),
        ])
        return {
            "status": values.get("status"),
            "fault": values.get("fault"),
            "battery": values.get("battery"),
            "robot": values.get("robot"),
            "charging_base": values.get("charging_base"),
        }

    @staticmethod
    def _v69_pose_key(vacuum, raw_robot):
        try:
            pos = vacuum.parse_position(raw_robot)
        except Exception:
            pos = None
        if isinstance(pos, dict):
            try:
                return (
                    round(float(pos.get("x")), 1),
                    round(float(pos.get("y")), 1),
                )
            except Exception:
                pass
        if raw_robot is None:
            return None
        try:
            return ("raw", repr(raw_robot)[:120])
        except Exception:
            return None

    @classmethod
    def _v69_fallback_reason(
        cls,
        *,
        status,
        fault,
        saw_returning,
        return_elapsed,
        dock_reasserted,
        pose_stable_seconds,
        battery_start,
        battery_now,
    ):
        status = cls._v67_int(status)
        fault = cls._v67_int(fault)
        battery_start = cls._v67_int(battery_start)
        battery_now = cls._v67_int(battery_now)

        if status == 4:
            return "direct", "status=4 cargando"

        if not saw_returning or fault != 0:
            return None, None

        if (
            battery_start is not None
            and battery_now is not None
            and battery_now >= battery_start + 1
            and float(return_elapsed or 0.0) >= 10.0
        ):
            return (
                "battery-rise",
                f"B112 status=3/retorno pero batería subió {battery_start}→{battery_now}",
            )

        if (
            status in (0, 1)
            and bool(dock_reasserted)
            and float(return_elapsed or 0.0) >= cls.RETURN_IDLE_STATUS_MIN_SECONDS
            and float(pose_stable_seconds or 0.0) >= 10.0
        ):
            return (
                "settled-idle",
                f"B112 terminó retorno en status={status} con posición estable",
            )

        if (
            status == 3
            and bool(dock_reasserted)
            and float(return_elapsed or 0.0) >= cls.RETURN_FALLBACK_MIN_SECONDS
            and float(pose_stable_seconds or 0.0) >= cls.RETURN_POSE_STABLE_SECONDS
        ):
            return (
                "stale-return",
                "B112 mantiene status=3 pese a dock revalidado y posición estable",
            )

        return None, None

    # ------------------------------------------------------- watchdog base
    def _v67_watch_base_worker(self, vacuum, serial):
        """V69: usa propiedades reales del B112 y fallback conservador."""
        deadline = time.monotonic() + self.BASE_WATCH_SECONDS
        first_probe_at = time.monotonic()
        returning_since = None
        pose_stable_since = None
        last_pose_key = None
        battery_start = None
        dock_sent = False
        direct_stable = 0
        last_tuple = None

        while time.monotonic() < deadline:
            if serial != self._v67_watch_serial or not self._auto_step2_pending:
                return
            if self.mapping_active or vacuum is not self.vacuum:
                return

            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                battery = self._v67_int(state.get("battery"))
                pose_key = self._v69_pose_key(vacuum, state.get("robot"))
            except Exception as exc:
                self._post_ui(
                    "v67_transition_probe_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )
                time.sleep(self.BASE_POLL_SECONDS)
                continue

            now = time.monotonic()
            if status == 3 and returning_since is None:
                returning_since = now
                battery_start = battery

            saw_returning = returning_since is not None
            return_elapsed = (now - returning_since) if returning_since is not None else 0.0

            if pose_key is not None and pose_key == last_pose_key:
                if pose_stable_since is None:
                    pose_stable_since = now
            else:
                pose_stable_since = now if pose_key is not None else None
                last_pose_key = pose_key

            pose_stable_seconds = (
                now - pose_stable_since
                if pose_stable_since is not None and pose_key is not None
                else 0.0
            )

            # El firmware real quedó pegado en status=3 aun físicamente acoplado.
            # Reafirmamos dock una sola vez después de 30 s de retorno.
            if (
                saw_returning
                and not dock_sent
                and return_elapsed >= self.RETURN_REASSERT_SECONDS
            ):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui(
                        "v67_dock_error",
                        serial,
                        str(exc).strip() or type(exc).__name__,
                    )

            # Si el cierre llegó sin status=3, conservamos el comportamiento
            # antiguo y pedimos dock tras un breve settle.
            if (
                not saw_returning
                and not dock_sent
                and now - first_probe_at >= 1.5
                and status not in (3, 4)
            ):
                try:
                    vacuum.dock()
                    dock_sent = True
                except Exception as exc:
                    self._post_ui(
                        "v67_dock_error",
                        serial,
                        str(exc).strip() or type(exc).__name__,
                    )

            at_base, direct_reason = self._v67_base_evidence(status, None)
            direct_stable = direct_stable + 1 if at_base else 0

            mode, fallback_reason = self._v69_fallback_reason(
                status=status,
                fault=fault,
                saw_returning=saw_returning,
                return_elapsed=return_elapsed,
                dock_reasserted=dock_sent,
                pose_stable_seconds=pose_stable_seconds,
                battery_start=battery_start,
                battery_now=battery,
            )

            self._v69_transition_diag.update({
                "last_status": status,
                "last_fault": fault,
                "last_battery": battery,
                "return_elapsed": round(return_elapsed, 1),
                "pose_stable_seconds": round(pose_stable_seconds, 1),
                "dock_reasserted": bool(dock_sent),
                "battery_rise": (
                    int(battery - battery_start)
                    if battery is not None and battery_start is not None
                    else 0
                ),
                "timeout": False,
            })

            current = (
                status,
                fault,
                battery,
                pose_key,
                dock_sent,
                saw_returning,
            )
            if current != last_tuple:
                self._post_ui(
                    "v67_transition_sample",
                    serial,
                    status,
                    None,
                    battery,
                    dock_sent,
                    saw_returning,
                )
                last_tuple = current

            if direct_stable >= self.BASE_CONFIRM_SAMPLES:
                self._v69_transition_diag.update({
                    "fallback_confirmed": False,
                    "fallback_mode": "direct",
                    "fallback_reason": direct_reason,
                    "confirmed_pose_key": pose_key,
                })
                self._post_ui(
                    "v67_base_confirmed",
                    serial,
                    status,
                    None,
                    battery,
                    direct_reason,
                    dock_sent,
                    saw_returning,
                )
                return

            if mode and mode != "direct":
                self._v69_transition_diag.update({
                    "fallback_confirmed": True,
                    "fallback_mode": mode,
                    "fallback_reason": fallback_reason,
                    "confirmed_pose_key": pose_key,
                })
                self._post_ui(
                    "v67_base_confirmed",
                    serial,
                    status,
                    None,
                    battery,
                    fallback_reason,
                    dock_sent,
                    saw_returning,
                )
                return

            time.sleep(self.BASE_POLL_SECONDS)

        self._v69_transition_diag["timeout"] = True
        self._post_ui("v67_transition_timeout", serial)

    def _v67_recheck_base_before_step2(self, serial):
        """Revalida también el fallback B112 antes del arranque interior."""
        if serial != self._v67_watch_serial:
            return
        self._v67_start_scheduled = False
        if not self._auto_step2_pending or self.mapping_active or not self.vacuum:
            return

        vacuum = self.vacuum

        def worker():
            try:
                state = self._v69_read_base_state(vacuum)
                status = self._v67_int(state.get("status"))
                fault = self._v67_int(state.get("fault"))
                battery = self._v67_int(state.get("battery"))
                pose_key = self._v69_pose_key(vacuum, state.get("robot"))

                if status == 4:
                    self._post_ui(
                        "v67_start_step2",
                        serial,
                        status,
                        None,
                        battery,
                        "status=4 cargando",
                    )
                    return

                diag = dict(self._v69_transition_diag or {})
                fallback_ok = bool(diag.get("fallback_confirmed")) and fault == 0
                confirmed_pose = diag.get("confirmed_pose_key")
                if (
                    fallback_ok
                    and status in (0, 1, 3)
                    and (
                        confirmed_pose is None
                        or pose_key is None
                        or pose_key == confirmed_pose
                    )
                ):
                    self._post_ui(
                        "v67_start_step2",
                        serial,
                        status,
                        None,
                        battery,
                        str(diag.get("fallback_reason") or "fallback B112 revalidado"),
                    )
                    return

                self._post_ui(
                    "v67_base_lost",
                    serial,
                    status,
                    None,
                    battery,
                )
            except Exception as exc:
                self._post_ui(
                    "v67_transition_probe_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        tdiag = dict(getattr(self, "_v69_transition_diag", {}) or {})
        client = getattr(self, "_v40_client", None)
        cdiag = dict(
            getattr(client, "last_v69_clean_end_diagnostics", {}) or {}
        ) if client is not None else {}

        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V69 ACTIVO · retorno B112 + clean-end real",
            "=======================================================",
            "spec exacta: battery 3/2 charging-state NO existe en xiaomi.vacuum.b112",
            f"último status={tdiag.get('last_status')!r} · fault={tdiag.get('last_fault')!r} · batería={tdiag.get('last_battery')!r}",
            f"retorno observado={tdiag.get('return_elapsed', 0)}s · pose estable={tdiag.get('pose_stable_seconds', 0)}s · dock reafirmado={bool(tdiag.get('dock_reasserted'))}",
            f"subida batería={tdiag.get('battery_rise', 0)} · fallback confirmado={bool(tdiag.get('fallback_confirmed'))} · modo={tdiag.get('fallback_mode') or '—'}",
            f"razón transición={tdiag.get('fallback_reason') or '—'} · timeout={bool(tdiag.get('timeout'))}",
            f"clean-end registros={int(cdiag.get('records_seen', 0) or 0)} · piid30 vistos={int(cdiag.get('piid30_seen', 0) or 0)} · refs usables={int(cdiag.get('usable_refs', 0) or 0)}",
            f"formas record-map-url={cdiag.get('ref_shapes') or {}} · refs anidadas={int(cdiag.get('nested_refs_seen', 0) or 0)}",
            "regla V69: 'cloud'/hello/retry/null no cuentan como FDS; sólo URL/ruta/objeto resoluble llega al probe",
            "regla V69: status=4 sigue siendo confirmación preferida; fallback status=3 exige dock revalidado + fault=0 + posición estable prolongada",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

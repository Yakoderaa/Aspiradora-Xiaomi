import threading
import time

from robot_command_arbiter import (
    RobotBusyError,
    RobotCommandArbiter,
    install_read_mostly_proxy,
)


ACTIVE = {5, 6, 7}
PROCESS_ARBITER = RobotCommandArbiter()


class SafeBaselineCore:
    """V153: baseline físico mínimo después de factory reset.

    Conectar/leer nunca escribe. La única orden de inicio permitida es A2/3,
    emitida una sola vez por una acción explícita del usuario.
    """

    def __init__(self, vacuum, arbiter=None, source="gui"):
        self.vacuum = vacuum
        self.arbiter = arbiter or PROCESS_ARBITER
        self.source = str(source)
        self.raw_device = install_read_mostly_proxy(vacuum, self.arbiter)
        self._worker = None
        self._last_diag = {}
        self._last_status = None

    @staticmethod
    def _int(value):
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _explicit_code(response):
        if isinstance(response, dict) and "code" in response:
            try:
                return int(response.get("code"))
            except Exception:
                return None
        if isinstance(response, list):
            codes = []
            for item in response:
                if isinstance(item, dict) and "code" in item:
                    try:
                        codes.append(int(item.get("code")))
                    except Exception:
                        pass
            if codes:
                return max(codes)
        return None

    def _read(self):
        values = self.vacuum._get_many([
            ("status", 2, 1),
            ("fault", 2, 2),
            ("mode", 2, 4),
            ("sweep_type", 2, 8),
            ("repeat", 7, 1),
            ("suction", 7, 5),
            ("water", 7, 6),
            ("twice_clean", 8, 10),
            ("build_state", 10, 14),
            ("has_new_map", 10, 19),
            ("robot", 10, 24),
            ("base", 10, 22),
        ])
        return {k: values.get(k) for k in (
            "status", "fault", "mode", "sweep_type", "repeat", "suction",
            "water", "twice_clean", "build_state", "has_new_map",
            "robot", "base",
        )}

    def _action_locked(self, siid, aiid, label):
        response = self.raw_device.call_action_by(int(siid), int(aiid))
        code = self._explicit_code(response)
        if code is not None and code != 0:
            raise RuntimeError(
                f"{label} rechazado por el E10 (code={code})."
            )
        self.arbiter.record("baseline_action", {
            "siid": int(siid),
            "aiid": int(aiid),
            "label": str(label),
            "response": repr(response)[:220],
        })
        return response

    def _factory_like_precheck(self):
        state = self._read()
        status = self._int(state.get("status"))
        if status in ACTIVE or status == 3:
            raise RobotBusyError(
                f"El E10 ya está en movimiento (status={status})."
            )

        # No corregimos nada automáticamente. Si el robot no está en el estado
        # limpio esperado, frenamos la prueba antes de escribir.
        checks = {
            "mode": self._int(state.get("mode")),
            "sweep_type": self._int(state.get("sweep_type")),
            "repeat": self._int(state.get("repeat")),
        }
        mismatches = {
            key: value
            for key, value in checks.items()
            if value is not None and value != 0
        }
        if mismatches:
            raise RuntimeError(
                "Baseline abortado sin escribir: el estado leído no coincide "
                f"con el estado limpio esperado: {mismatches!r}."
            )
        return state

    def start_normal_async(self, on_started=None, on_finished=None):
        if self._worker is not None and self._worker.is_alive():
            raise RobotBusyError("Ya hay una prueba baseline en curso.")

        worker = threading.Thread(
            target=self._run_normal,
            args=(on_started, on_finished),
            name="SafeBaselineNormalClean",
            daemon=True,
        )
        self._worker = worker
        worker.start()
        return True

    def _run_normal(self, on_started, on_finished):
        session = None
        diag = {
            "purpose": "baseline_normal_clean",
            "source": self.source,
            "sequence": [
                "lectura/precheck únicamente",
                "A2/3 único START",
            ],
            "writes_before_start": 0,
            "start_action": None,
            "start_response": None,
            "started": False,
            "finish_reason": None,
            "error": None,
        }
        self._last_diag = diag
        try:
            session = self.arbiter.begin(
                "baseline-normal-clean",
                self.source,
            )
            diag["session_id"] = session.session_id
            before = self._factory_like_precheck()
            diag["before"] = before

            # Misma frontera que cancelación: o sale A2/3 o gana STOP/DOCK.
            with self.arbiter._io_lock:
                if session.cancel_action:
                    raise RuntimeError(
                        "La prueba fue cancelada antes del START."
                    )
                response = self._action_locked(
                    2,
                    3,
                    "baseline standard START 2/3",
                )

            diag["start_action"] = (2, 3)
            diag["start_response"] = repr(response)[:500]

            deadline = time.monotonic() + 12.0
            started_state = {}
            while time.monotonic() < deadline:
                if session.cancel_action:
                    break
                started_state = self._read()
                status = self._int(started_state.get("status"))
                self._last_status = status
                if status in ACTIVE:
                    diag["started"] = True
                    diag["started_state"] = started_state
                    break
                time.sleep(0.30)

            if not diag["started"] and not session.cancel_action:
                raise RuntimeError(
                    "El único START 2/3 no confirmó actividad física."
                )

            if callable(on_started) and diag["started"]:
                on_started(dict(diag))

            idle_streak = 0
            dock_requested = False
            while True:
                if session.cancel_action:
                    with self.arbiter._io_lock:
                        action = str(session.cancel_action)
                        session.cancel_action = None
                        if action == "dock":
                            self._action_locked(
                                3, 1, "baseline dock user"
                            )
                            dock_requested = True
                        else:
                            self._action_locked(
                                2, 2, "baseline stop user"
                            )
                            diag["finish_reason"] = "stop_requested"
                            break

                state = self._read()
                status = self._int(state.get("status"))
                self._last_status = status
                if status == 4:
                    diag["finish_reason"] = (
                        "dock_requested" if dock_requested else "dock"
                    )
                    break
                if status in (0, 1, 2):
                    idle_streak += 1
                    if idle_streak >= 4:
                        diag["finish_reason"] = (
                            "dock_requested" if dock_requested else "idle"
                        )
                        break
                else:
                    idle_streak = 0
                time.sleep(1.0)
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
        finally:
            if session is not None:
                self.arbiter.finish(
                    session,
                    diag.get("error")
                    or diag.get("finish_reason")
                    or "finished",
                )
            self._last_diag = dict(diag)
            if callable(on_finished):
                try:
                    on_finished(dict(diag))
                except Exception:
                    pass

    def request_stop(self):
        if self.arbiter.request_cancel("stop"):
            return True
        with self.arbiter._io_lock:
            self._action_locked(2, 2, "baseline stop user")
        return True

    def request_dock(self):
        if self.arbiter.request_cancel("dock"):
            return True
        with self.arbiter._io_lock:
            self._action_locked(3, 1, "baseline dock user")
        return True

    def diagnostic(self):
        session = self.arbiter.session
        return {
            "active": bool(self.arbiter.active),
            "session": (
                {
                    "id": session.session_id,
                    "purpose": session.purpose,
                    "source": session.source,
                    "cancel_action": session.cancel_action,
                }
                if session is not None
                else None
            ),
            "last": dict(self._last_diag or {}),
            "legacy_blocks": self.arbiter.legacy_blocks,
            "last_legacy_block": self.arbiter.last_legacy_block,
            "audit": self.arbiter.audit_snapshot()[-60:],
        }

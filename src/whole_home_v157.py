import time


ACTIVE = {5, 6, 7}


class WholeHomeRunnerV157:
    """Única ruta física de vivienda: precheck de lectura + un START 2/1."""

    def __init__(self, core, source="gui"):
        self.core = core
        self.source = str(source)

    def run(
        self,
        on_started=None,
        on_state=None,
        on_idle=None,
        on_finished=None,
        max_seconds=12 * 60 * 60,
    ):
        core = self.core
        diag = {
            "purpose": "whole-home-v157",
            "source": self.source,
            "sequence": ["read/precheck", "A2/1 unico"],
            "writes_before_start": 0,
            "start_action": None,
            "started": False,
            "finish_reason": None,
            "idle_observed": False,
            "read_errors": 0,
            "error": None,
        }
        session = None
        try:
            session = core.arbiter.begin("whole-home-v157", self.source)
            diag["session_id"] = session.session_id
            before = core._factory_like_precheck()
            diag["before"] = before

            with core.arbiter._io_lock:
                if session.cancel_action:
                    raise RuntimeError("Limpieza cancelada antes del START.")
                response = core._action_locked(2, 1, "V157 whole-home start 2/1")
            diag["start_action"] = (2, 1)
            diag["start_response"] = repr(response)[:500]

            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    if callable(on_state):
                        on_state(dict(state))
                    if status in ACTIVE:
                        diag["started"] = True
                        diag["started_state"] = state
                        break
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__
                time.sleep(0.4)

            if not diag["started"]:
                raise RuntimeError("El START 2/1 no confirmó movimiento físico.")

            if callable(on_started):
                on_started(dict(diag))

            started_at = time.monotonic()
            idle_streak = 0
            idle_notified = False
            dock_requested = False
            while time.monotonic() - started_at < float(max_seconds):
                if session.cancel_action:
                    with core.arbiter._io_lock:
                        action = str(session.cancel_action)
                        session.cancel_action = None
                        if action == "dock":
                            core._action_locked(3, 1, "V157 dock user")
                            dock_requested = True
                            diag["user_dock"] = True
                        else:
                            core._action_locked(2, 2, "V157 stop user")
                            diag["finish_reason"] = "stop_requested"
                            break

                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    diag["last_state"] = state
                    if callable(on_state):
                        on_state(dict(state))

                    if status == 4:
                        diag["finish_reason"] = (
                            "dock_requested" if dock_requested else "dock"
                        )
                        break

                    if status in (0, 1, 2):
                        idle_streak += 1
                        diag["idle_observed"] = True
                        if idle_streak >= 3 and not idle_notified:
                            idle_notified = True
                            if callable(on_idle):
                                on_idle(dict(diag))
                    else:
                        idle_streak = 0
                        idle_notified = False
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__
                time.sleep(2.0)
            else:
                diag["finish_reason"] = "timeout_waiting_dock"
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
        finally:
            if session is not None:
                core.arbiter.finish(
                    session,
                    diag.get("error") or diag.get("finish_reason") or "finished",
                )
            if callable(on_finished):
                try:
                    on_finished(dict(diag))
                except Exception:
                    pass
        return diag

import json
import threading
import time
from dataclasses import dataclass

from robot_plans import local_rect_to_device

from robot_command_arbiter import (
    RobotBusyError,
    RobotCommandArbiter,
    install_read_mostly_proxy,
)


ACTIVE = {5, 6, 7}
IDLE = {0, 1, 2, 4}


@dataclass
class FreshStartResult:
    session_id: str
    purpose: str
    mode: int
    status_before: int | None
    status_after: int | None
    sweep_type_after: int | None
    start_action: tuple
    start_response: object
    build_response: object = None
    build_ack: str | None = None


class FreshRobotCore:
    """Motor físico nuevo.

    No usa helpers históricos de start/mapping/recovery. Sólo lee mediante el
    objeto XiaomiE10 y escribe contra el transporte MIoT original guardado.
    """

    START_ACTION_BY_MODE = {0: 3, 1: 5, 2: 6}

    def __init__(self, vacuum, arbiter=None, source="gui"):
        self.vacuum = vacuum
        self.arbiter = arbiter or RobotCommandArbiter()
        self.source = str(source)
        self.raw_device = install_read_mostly_proxy(vacuum, self.arbiter)
        self._worker = None
        self._last_diag = {}
        self._last_status = None
        self._status_callback = None
        self._finish_callback = None

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

    @classmethod
    def _assert_not_rejected(cls, response, label):
        code = cls._explicit_code(response)
        if code is not None and code != 0:
            raise RuntimeError(f"{label} rechazado por el E10 (code={code}).")
        return code

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

    def _set(self, siid, piid, value, label):
        with self.arbiter._io_lock:
            response = self.raw_device.set_property_by(
                int(siid), int(piid), value
            )
        self._assert_not_rejected(response, label)
        self.arbiter.record("property", {
            "siid": int(siid),
            "piid": int(piid),
            "value": value,
            "response": repr(response)[:220],
        })
        return response

    def _action(self, siid, aiid, params=None, label="action"):
        with self.arbiter._io_lock:
            if params is None:
                response = self.raw_device.call_action_by(
                    int(siid), int(aiid)
                )
            else:
                response = self.raw_device.call_action_by(
                    int(siid), int(aiid), params
                )
        self._assert_not_rejected(response, label)
        self.arbiter.record("action", {
            "siid": int(siid),
            "aiid": int(aiid),
            "params": repr(params)[:220],
            "response": repr(response)[:220],
        })
        return response

    def _neutralize_navigation_state(self):
        """Borra estado de limpieza/navegación sin tocar Wi-Fi ni mapas guardados."""
        before = self._read()
        status = self._int(before.get("status"))
        if status in ACTIVE or status == 3:
            raise RobotBusyError(
                f"No se normaliza una tarea en movimiento (status={status})."
            )

        rows = []
        def best_effort(label, fn):
            item = {"label": label, "ok": False, "error": None}
            try:
                response = fn()
                self._assert_not_rejected(response, label)
                item["ok"] = True
                item["response"] = repr(response)[:220]
            except Exception as exc:
                item["error"] = str(exc).strip() or type(exc).__name__
            rows.append(item)

        # Sólo STOP/clear. Ninguno de estos comandos inicia navegación.
        best_effort(
            "stop latent edge",
            lambda: self._action(7, 3, ["", 2, 2], "stop latent edge"),
        )
        best_effort(
            "stop latent global",
            lambda: self._action(7, 3, ["", 0, 2], "stop latent global"),
        )
        best_effort(
            "stop latent point",
            lambda: self._action(7, 3, ["", 4, 2], "stop latent point"),
        )
        best_effort(
            "vacuum stop",
            lambda: self._action(2, 2, label="neutral stop"),
        )
        best_effort(
            "remote exit",
            lambda: self._set(7, 16, 10, "remote exit"),
        )
        best_effort(
            "clear point",
            lambda: self._set(9, 5, "", "clear point"),
        )
        best_effort(
            "clear zone",
            lambda: self._set(9, 2, "", "clear zone"),
        )
        best_effort(
            "repeat off",
            lambda: self._set(7, 1, 0, "repeat off"),
        )
        best_effort(
            "twice clean off",
            lambda: self._set(8, 10, 0, "twice clean off"),
        )
        best_effort(
            "water off",
            lambda: self._set(7, 6, 0, "water off"),
        )
        best_effort(
            "suction eco",
            lambda: self._set(7, 5, 1, "suction eco"),
        )
        best_effort(
            "mode vacuum",
            lambda: self._set(2, 4, 0, "mode vacuum"),
        )
        best_effort(
            "sweep global",
            lambda: self._set(2, 8, 0, "sweep global"),
        )

        time.sleep(0.45)
        after = self._read()
        for key in ("mode", "sweep_type", "repeat"):
            value = self._int(after.get(key))
            if value not in (None, 0):
                raise RuntimeError(
                    f"Neutralización incompleta: {key}={value!r}."
                )
        self.arbiter.record(
            "navigation_neutralized",
            {
                "before": repr(before)[:500],
                "after": repr(after)[:500],
                "steps": rows,
            },
        )
        return {"before": before, "after": after, "steps": rows}

    def _normalize(self, mode, suction, water):
        mode = int(mode)
        if mode not in (0, 1, 2):
            raise ValueError("Modo inválido")
        suction = max(1, min(4, int(suction or 1)))
        water = max(0, min(3, int(water or 0)))
        if mode == 0:
            water = 0
        elif mode in (1, 2) and water <= 0:
            water = 1

        before = self._read()
        status = self._int(before.get("status"))
        if status in ACTIVE or status == 3:
            raise RobotBusyError(
                f"El E10 ya está en una tarea física (status={status})."
            )

        # Estado mínimo conocido. No usamos remember-state, 7/3 ni reasserts.
        self._set(7, 1, 0, "repeat=0")
        self._set(2, 4, mode, "mode")
        self._set(2, 8, 0, "sweep_type=Global")
        self._set(7, 5, suction, "suction")
        self._set(7, 6, water, "water")

        after = self._read()
        rb_mode = self._int(after.get("mode"))
        rb_sweep = self._int(after.get("sweep_type"))
        if rb_mode is not None and rb_mode != mode:
            raise RuntimeError(
                f"El E10 no confirmó mode={mode}; devolvió {rb_mode}."
            )
        if rb_sweep is not None and rb_sweep != 0:
            raise RuntimeError(
                f"El E10 no confirmó Global=0; sweep_type={rb_sweep}."
            )
        return before, after, suction, water

    def _request_build_once(self):
        response = self._action(
            10, 17, [1],
            label="build-map-ii 10/17",
        )
        code = self._explicit_code(response)
        if code == 0:
            ack = "explicit-code-0"
        elif code is None:
            ack = "ambiguous-no-code"
        else:
            ack = f"rejected-{code}"
        return response, ack

    def _start_standard(self, mode):
        action = self.START_ACTION_BY_MODE[int(mode)]
        response = self._action(
            2, action,
            label=f"standard-start 2/{action}",
        )
        return (2, action), response

    def _wait_started(self, session, timeout=12.0):
        deadline = time.monotonic() + max(2.0, float(timeout))
        last = {}
        while time.monotonic() < deadline:
            if session.cancel_action:
                raise RuntimeError(
                    "Inicio cancelado antes de confirmar movimiento."
                )
            last = self._read()
            status = self._int(last.get("status"))
            sweep = self._int(last.get("sweep_type"))
            self._last_status = status
            if status in ACTIVE:
                if sweep is not None and sweep != 0:
                    try:
                        self._action(2, 2, label="stop wrong sweep")
                    finally:
                        raise RuntimeError(
                            f"El robot arrancó fuera de Global=0 (sweep={sweep})."
                        )
                return last
            time.sleep(0.30)
        raise RuntimeError(
            "El E10 recibió un único START estándar pero no confirmó "
            f"actividad (último status={self._last_status})."
        )

    def _perform_cancel(self, session):
        action = str(session.cancel_action or "")
        if action == "dock":
            self._action(3, 1, label="dock user priority")
            return "dock_requested"
        if action == "stop":
            self._action(2, 2, label="stop user priority")
            return "stop_requested"
        return None

    def _monitor_until_terminal(self, session, mapping=False):
        idle_streak = 0
        while True:
            if session.cancel_action:
                reason = self._perform_cancel(session)
                if reason == "dock_requested":
                    # Seguimos hasta carga o hasta idle estable.
                    pass
                else:
                    return reason

            state = self._read()
            status = self._int(state.get("status"))
            self._last_status = status
            if callable(self._status_callback):
                try:
                    self._status_callback(dict(state))
                except Exception:
                    pass

            if status == 4:
                return "dock"
            if status in (0, 1, 2):
                idle_streak += 1
                if idle_streak >= 4:
                    return "idle"
            else:
                idle_streak = 0
            time.sleep(0.75 if mapping else 1.0)

    def _run_global(
        self,
        purpose,
        mode,
        suction,
        water,
        mapping,
        on_started,
        on_finished,
    ):
        session = None
        diag = {
            "purpose": str(purpose),
            "source": self.source,
            "mapping": bool(mapping),
            "sequence": [],
            "build_response": None,
            "build_ack": None,
            "start_action": None,
            "start_response": None,
            "started": False,
            "finish_reason": None,
            "error": None,
        }
        self._last_diag = diag
        try:
            session = self.arbiter.begin(purpose, self.source)
            diag["session_id"] = session.session_id

            neutral = self._neutralize_navigation_state()
            diag["neutralization"] = neutral
            before, normalized, suction, water = self._normalize(
                mode, suction, water
            )
            diag["before"] = before
            diag["normalized"] = normalized
            diag["sequence"].append(
                "repeat=0 -> mode -> sweep_type=0 -> suction -> water"
            )

            build_response = None
            build_ack = None
            if mapping:
                build_response, build_ack = self._request_build_once()
                diag["build_response"] = repr(build_response)[:500]
                diag["build_ack"] = build_ack
                diag["sequence"].append("10/17 [1] una vez")

            start_action, start_response = self._start_standard(mode)
            diag["start_action"] = start_action
            diag["start_response"] = repr(start_response)[:500]
            diag["sequence"].append(
                f"{start_action[0]}/{start_action[1]} único START"
            )

            started = self._wait_started(session)
            diag["started"] = True
            diag["started_state"] = started
            self._last_diag = dict(diag)

            if callable(on_started):
                on_started(dict(diag))

            self._status_callback = None
            reason = self._monitor_until_terminal(
                session,
                mapping=bool(mapping),
            )
            diag["finish_reason"] = reason
            diag["final_state"] = self._read()
            self._last_diag = dict(diag)
            if callable(on_finished):
                on_finished(dict(diag))
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._last_diag = dict(diag)
            if callable(on_finished):
                on_finished(dict(diag))
        finally:
            if session is not None:
                self.arbiter.finish(
                    session,
                    diag.get("finish_reason")
                    or diag.get("error")
                    or "finished",
                )
            self._worker = None

    def start_global_async(
        self,
        mode=0,
        suction=1,
        water=0,
        mapping=False,
        on_started=None,
        on_finished=None,
        purpose=None,
    ):
        if self._worker is not None and self._worker.is_alive():
            raise RobotBusyError("Fresh Core ya tiene una sesión activa.")
        purpose = purpose or ("mapping" if mapping else "whole_clean")
        worker = threading.Thread(
            target=self._run_global,
            args=(
                purpose,
                int(mode),
                int(suction),
                int(water),
                bool(mapping),
                on_started,
                on_finished,
            ),
            name=f"FreshRobotCore-{purpose}",
            daemon=True,
        )
        self._worker = worker
        worker.start()
        return True

    def request_stop(self):
        if self.arbiter.request_cancel("stop"):
            return True
        # Sin sesión propia: STOP explícito corto con arbitraje entre procesos.
        return self._run_one_shot("stop", lambda: self._action(2, 2, label="stop"))

    def request_dock(self):
        if self.arbiter.request_cancel("dock"):
            return True
        return self._run_one_shot("dock", lambda: self._action(3, 1, label="dock"))

    def _run_one_shot(self, purpose, func):
        session = self.arbiter.begin(purpose, self.source)
        try:
            return func()
        finally:
            self.arbiter.finish(session, purpose)

    def set_suction(self, level):
        level = max(0, min(4, int(level)))
        return self._set(7, 5, level, "user suction")

    def set_water(self, level):
        level = max(0, min(3, int(level)))
        return self._set(7, 6, level, "user water")

    def locate(self):
        # Find-me es 4/1=1 en este B112; no altera la estrategia de navegación.
        with self.arbiter._io_lock:
            return self.raw_device.set_property_by(4, 1, 1)

    def manual(self, direction):
        if self.arbiter.active:
            raise RobotBusyError(
                "Control manual bloqueado mientras hay una limpieza/mapeo activo."
            )
        direction = int(direction)
        session = self.arbiter.begin("manual", self.source)
        try:
            return self.raw_device.set_property_by(7, 16, direction)
        finally:
            self.arbiter.finish(session, "manual")

    def sync_virtual_walls(self, plan, force=False, _inside_session=False):
        plan = dict(plan or {})
        walls = list(plan.get("no_go") or [])
        if not force and not plan.get("virtual_walls_managed", False):
            return None
        if walls and not plan.get("device_origin"):
            raise RuntimeError(
                "No puedo sincronizar bloqueos sin origen físico del mapa."
            )
        encoded = []
        for index, wall in enumerate(walls, 1):
            rect = local_rect_to_device(wall, plan)
            encoded.append(
                f"{index}_1_{rect['x0']}_{rect['y1']}_{rect['x1']}_{rect['y0']}"
            )
        payload = json.dumps(
            [len(encoded), *encoded],
            separators=(",", ":"),
        )
        if _inside_session:
            return self._action(
                9, 6, [payload],
                label="virtual walls 9/6",
            )
        return self._run_one_shot(
            "virtual_walls",
            lambda: self._action(
                9, 6, [payload],
                label="virtual walls 9/6",
            ),
        )

    def run_zone_sequence(
        self,
        raw_rectangles,
        passes,
        suction,
        water,
        on_stage=None,
        on_finished=None,
        plan=None,
        force_wall_sync=False,
    ):
        if self._worker is not None and self._worker.is_alive():
            raise RobotBusyError("Fresh Core ya tiene una sesión activa.")

        rects = [dict(r) for r in list(raw_rectangles or [])]
        passes = [str(x) for x in list(passes or [])]
        suction = max(1, min(4, int(suction or 1)))
        water = max(0, min(3, int(water or 0)))

        def worker():
            session = None
            diag = {
                "purpose": "targeted_zones",
                "rectangles": len(rects),
                "passes": list(passes),
                "completed": 0,
                "error": None,
            }
            try:
                session = self.arbiter.begin("targeted_zones", self.source)
                if plan is not None:
                    self.sync_virtual_walls(
                        plan,
                        force=bool(force_wall_sync),
                        _inside_session=True,
                    )
                total = max(1, len(rects) * len(passes))
                index = 0
                for clean_mode in passes:
                    mode_id = {"vacuum": 0, "mop": 2, "vacuum_mop": 1}.get(
                        clean_mode,
                        0,
                    )
                    pass_water = 0 if mode_id == 0 else max(1, water)
                    self._normalize(mode_id, suction, pass_water)
                    for rect in rects:
                        if session.cancel_action:
                            self._perform_cancel(session)
                            raise RuntimeError("Limpieza dirigida cancelada.")
                        index += 1
                        if callable(on_stage):
                            on_stage(index, total)
                        zone_value = ",".join(str(v) for v in (
                            rect["x0"], rect["y0"],
                            rect["x0"], rect["y1"],
                            rect["x1"], rect["y1"],
                            rect["x1"], rect["y0"],
                        ))
                        try:
                            self._action(
                                9, 8, [zone_value],
                                label="zone target 9/8",
                            )
                        except Exception:
                            self._set(9, 2, zone_value, "zone target 9/2")
                        self._action(9, 3, label="zone start 9/3")
                        self._wait_started(session, timeout=10.0)
                        self._monitor_until_terminal(session, mapping=False)
                        diag["completed"] += 1
                        time.sleep(0.6)
            except Exception as exc:
                diag["error"] = str(exc).strip() or type(exc).__name__
            finally:
                if session is not None:
                    self.arbiter.finish(
                        session,
                        diag.get("error") or "targeted_complete",
                    )
                self._last_diag = dict(diag)
                self._worker = None
                if callable(on_finished):
                    on_finished(dict(diag))

        self._worker = threading.Thread(
            target=worker,
            name="FreshRobotCore-targeted",
            daemon=True,
        )
        self._worker.start()
        return True

    def diagnostic(self):
        return {
            "active": bool(self.arbiter.active),
            "session": (
                {
                    "id": self.arbiter.session.session_id,
                    "purpose": self.arbiter.session.purpose,
                    "source": self.arbiter.session.source,
                    "cancel_action": self.arbiter.session.cancel_action,
                }
                if self.arbiter.session is not None
                else None
            ),
            "last": dict(self._last_diag or {}),
            "legacy_blocks": self.arbiter.legacy_blocks,
            "last_legacy_block": self.arbiter.last_legacy_block,
            "audit": self.arbiter.audit_snapshot()[-40:],
        }

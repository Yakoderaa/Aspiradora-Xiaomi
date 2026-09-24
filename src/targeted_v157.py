import time


ACTIVE = {5, 6, 7}


def _fmt(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


class TargetedRunnerV157:
    """Limpieza explícita de habitación/zona sin usar 2/3 ni control remoto."""

    def __init__(self, core, source="gui"):
        self.core = core
        self.source = str(source)

    def _set_locked(self, siid, piid, value, label):
        response = self.core.raw_device.set_property_by(
            int(siid), int(piid), value
        )
        code = self.core._explicit_code(response)
        if code is not None and code != 0:
            raise RuntimeError(f"{label} rechazado (code={code}).")
        self.core.arbiter.record("v157_target_property", {
            "siid": int(siid),
            "piid": int(piid),
            "value": value,
            "label": str(label),
        })
        return response

    @staticmethod
    def _mode_values(mode, suction, water):
        mode = str(mode or "vacuum")
        suction = max(0, min(4, int(suction or 0)))
        water = max(0, min(3, int(water or 0)))
        if mode == "vacuum":
            return 0, max(1, suction or 1), 0
        if mode == "vacuum_mop":
            return 1, max(1, suction or 1), max(1, water or 1)
        if mode == "mop":
            return 2, 0, max(1, water or 1)
        raise ValueError(f"Modo dirigido desconocido: {mode}")

    @staticmethod
    def _zone_value(rect):
        x0, x1 = sorted((float(rect["x0"]), float(rect["x1"])))
        y0, y1 = sorted((float(rect["y0"]), float(rect["y1"])))
        return ",".join(
            _fmt(v)
            for v in (x0, y0, x0, y1, x1, y1, x1, y0)
        )

    def _start_zone_locked(self, rect):
        value = self._zone_value(rect)
        try:
            response = self.core.raw_device.call_action_by(9, 8, [value])
            code = self.core._explicit_code(response)
            if code is not None and code != 0:
                raise RuntimeError(f"9/8 code={code}")
            self.core.arbiter.record("v157_target_action", {
                "route": "9/8",
                "zone": value,
                "response": repr(response)[:220],
            })
            return "9/8", response
        except Exception as first:
            self._set_locked(9, 2, value, "target zone 9/2")
            response = self.core.raw_device.call_action_by(9, 3)
            code = self.core._explicit_code(response)
            if code is not None and code != 0:
                raise RuntimeError(
                    f"No se pudo iniciar zona: 9/8={first}; 9/3 code={code}"
                )
            self.core.arbiter.record("v157_target_action", {
                "route": "9/2+9/3",
                "zone": value,
                "response": repr(response)[:220],
            })
            return "9/2+9/3", response

    def _wait_cycle(self, on_state=None, timeout=3 * 60 * 60):
        start_deadline = time.monotonic() + 35.0
        started = False
        last = None
        while time.monotonic() < start_deadline:
            state = self.core._read()
            last = self.core._int(state.get("status"))
            if callable(on_state):
                on_state(dict(state))
            if last in ACTIVE:
                started = True
                break
            time.sleep(0.6)
        if not started:
            raise RuntimeError(
                f"El E10 no confirmó la limpieza dirigida (status={last!r})."
            )

        deadline = time.monotonic() + float(timeout)
        terminal = 0
        while time.monotonic() < deadline:
            state = self.core._read()
            last = self.core._int(state.get("status"))
            if callable(on_state):
                on_state(dict(state))
            if last in ACTIVE or last == 3:
                terminal = 0
            elif last in (0, 1, 2, 4):
                terminal += 1
                if terminal >= 2:
                    return last
            time.sleep(1.5)
        raise TimeoutError(
            f"La limpieza dirigida superó el tiempo máximo (status={last!r})."
        )

    def run(
        self,
        rects,
        mode="vacuum",
        suction=2,
        water=0,
        on_stage=None,
        on_state=None,
    ):
        rects = [dict(item) for item in list(rects or [])]
        if not rects:
            raise RuntimeError("No hay sectores para limpiar.")

        core = self.core
        session = None
        configured = False
        diag = {
            "purpose": "targeted-v157",
            "source": self.source,
            "rectangles": len(rects),
            "routes": [],
            "completed": 0,
            "error": None,
        }
        try:
            session = core.arbiter.begin("targeted-v157", self.source)
            diag["session_id"] = session.session_id
            diag["before"] = core._factory_like_precheck()
            mode_id, suction_value, water_value = self._mode_values(
                mode, suction, water
            )

            with core.arbiter._io_lock:
                self._set_locked(2, 4, mode_id, "target mode")
                self._set_locked(7, 5, suction_value, "target suction")
                self._set_locked(7, 6, water_value, "target water")
                configured = True

            total = len(rects)
            for index, rect in enumerate(rects, start=1):
                if session.cancel_action:
                    break
                if callable(on_stage):
                    on_stage(index, total)
                with core.arbiter._io_lock:
                    route, response = self._start_zone_locked(rect)
                diag["routes"].append(route)
                self._wait_cycle(on_state=on_state)
                diag["completed"] += 1
                time.sleep(0.7)

            if session.cancel_action:
                with core.arbiter._io_lock:
                    action = str(session.cancel_action)
                    session.cancel_action = None
                    if action == "dock":
                        core._action_locked(3, 1, "V157 target dock user")
                        diag["finish_reason"] = "dock_requested"
                    else:
                        core._action_locked(2, 2, "V157 target stop user")
                        diag["finish_reason"] = "stop_requested"
            else:
                diag["finish_reason"] = "completed"

        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
        finally:
            # Devolvemos sólo los selectores de navegación al estado baseline.
            # Se ejecuta después del ciclo dirigido, nunca durante movimiento.
            if configured:
                try:
                    with core.arbiter._io_lock:
                        self._set_locked(2, 4, 0, "restore mode")
                        self._set_locked(2, 8, 0, "restore sweep")
                        self._set_locked(7, 1, 0, "restore repeat")
                except Exception as exc:
                    diag.setdefault("restore_error", str(exc).strip() or type(exc).__name__)

            if session is not None:
                core.arbiter.finish(
                    session,
                    diag.get("error") or diag.get("finish_reason") or "finished",
                )
        return diag

import threading
import time
from tkinter import messagebox

import app_native_start
import app_v151
import app_v9


class App(app_native_start.App):
    """V155: baseline firme + mapeo conservador sobre START 2/1 validado."""

    MAP_CONFIRM_TIMEOUT = 15.0

    def __init__(self):
        self._v155_mapping_diag = {}
        self._v155_mapping_owner = False
        self._v155_mapping_serial = 0
        super().__init__()

    def _baseline_disabled(self, feature):
        messagebox.showinfo(
            "V155 Mapeo firme",
            f"{feature} todavía no está habilitado en esta etapa.\n\n"
            "V155 conserva el START 2/1 que ya recorrió toda la casa y habilita "
            "únicamente el mapeo global mínimo: build-map oficial + un solo 2/1. "
            "No reactiva EDGE, 7/3, 2/3, escapes ni controladores heredados.",
            parent=self,
        )
        return None

    def start_new_mapping(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)) or bool(self._v155_mapping_owner):
            messagebox.showinfo(
                "Mapeo en curso",
                "Ya hay un mapeo activo.",
                parent=self,
            )
            return

        core = self._fresh()
        if bool(core.diagnostic().get("active")):
            messagebox.showinfo(
                "Robot ocupado",
                "Esperá a que termine la sesión actual antes de mapear.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda · V155",
            "Se va a crear un mapa Xiaomi nuevo.\n\n"
            "La ruta física es deliberadamente mínima: una acción oficial "
            "build-map y, después, el mismo START 2/1 que ya completó la casa "
            "correctamente. No se usa 2/3, 7/3, EDGE, control remoto ni "
            "recoveries automáticos.\n\n"
            "Dejá abiertas todas las puertas y empezá con el robot en la base.",
            parent=self,
        )
        if not ok:
            return

        self._v155_mapping_serial += 1
        serial = self._v155_mapping_serial
        self._v155_mapping_owner = True
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False
        self._v155_mapping_diag = {
            "serial": serial,
            "route": "read/precheck -> 10/17 build-map-ii(1) -> A2/1 unico",
            "build": None,
            "start_response": None,
            "started": False,
            "finish_reason": None,
            "read_errors": 0,
            "error": None,
        }

        try:
            self._v151_prepare_map_layers()
        except Exception:
            pass
        try:
            self._v74_reset_session()
        except Exception:
            pass
        try:
            self.local_map.clear_map(keep_rooms=False)
            self.selected_point = None
        except Exception:
            pass
        try:
            self.show_page("map")
            self._sync_mapping_step_buttons()
            self._render_maps()
        except Exception:
            pass

        self._set_banner(
            "V155 · mapeo: creando mapa Xiaomi; después saldrá con un único START 2/1…"
        )
        threading.Thread(
            target=self._v155_mapping_worker,
            args=(vacuum, core, serial),
            name="V155SafeMapping",
            daemon=True,
        ).start()

    def _v155_mapping_worker(self, vacuum, core, serial):
        diag = self._v155_mapping_diag
        session = None
        try:
            session = core.arbiter.begin("v155-mapping", "gui")
            diag["session_id"] = session.session_id
            before = core._factory_like_precheck()
            diag["before"] = before

            with core.arbiter._io_lock:
                if session.cancel_action:
                    raise RuntimeError("Mapeo cancelado antes de crear el mapa.")

                # Única escritura de preparación necesaria para que Xiaomi cree
                # una sesión de mapa. Se usa sólo 10/17; no hay fallback 10/11.
                response = core.raw_device.call_action_by(10, 17, [1])
                code = vacuum._miot_action_code(response)
                ack = vacuum._miot_action_ack(response)
                empty_ack = vacuum._miot_b112_empty_result_ack(response)
                timestamp = vacuum._miot_output_value(response, 18)
                accepted = (
                    code == 0
                    or bool(ack)
                    or bool(empty_ack)
                    or timestamp is not None
                )
                diag["build"] = {
                    "action": (10, 17),
                    "response": vacuum._miot_action_response_summary(response),
                    "code": code,
                    "ack": bool(ack),
                    "b112_empty_ack": bool(empty_ack),
                    "timestamp": timestamp,
                    "accepted": bool(accepted),
                }
                core.arbiter.record("v155_map_build", diag["build"])
                if code is not None and code != 0:
                    raise RuntimeError(f"build-map 10/17 rechazado (code={code}).")
                if not accepted:
                    raise RuntimeError(
                        "build-map 10/17 no entregó un ACK reconocible; "
                        "se canceló sin mover el robot."
                    )

                if session.cancel_action:
                    raise RuntimeError("Mapeo cancelado antes del START.")

                start_response = core.raw_device.call_action_by(2, 1)
                start_code = core._explicit_code(start_response)
                if start_code is not None and start_code != 0:
                    raise RuntimeError(
                        f"START 2/1 rechazado por el E10 (code={start_code})."
                    )
                diag["start_response"] = repr(start_response)[:500]
                core.arbiter.record("v155_map_start", {
                    "siid": 2,
                    "aiid": 1,
                    "response": repr(start_response)[:220],
                })

            deadline = time.monotonic() + self.MAP_CONFIRM_TIMEOUT
            while time.monotonic() < deadline:
                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    if status in (5, 6, 7):
                        diag["started"] = True
                        diag["started_state"] = state
                        self._post_ui("v155_mapping_started", serial, dict(diag))
                        break
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__
                time.sleep(0.4)

            if not diag["started"]:
                raise RuntimeError("El START 2/1 no confirmó movimiento físico.")

            # Telemetría puede perderse temporalmente: no abortamos ni enviamos
            # nada. El firmware conserva el control de navegación.
            terminal = 0
            while self._v155_mapping_owner and serial == self._v155_mapping_serial:
                if session.cancel_action:
                    with core.arbiter._io_lock:
                        action = str(session.cancel_action)
                        session.cancel_action = None
                        if action == "dock":
                            core._action_locked(3, 1, "v155 dock user")
                            diag["user_dock"] = True
                        else:
                            core._action_locked(2, 2, "v155 stop user")
                            diag["finish_reason"] = "stop_requested"
                            break
                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    diag["last_state"] = state
                    if status == 4:
                        diag["finish_reason"] = (
                            "dock_requested" if diag.get("user_dock") else "dock"
                        )
                        break
                    if status in (0, 1):
                        terminal += 1
                        if terminal >= 6:
                            diag["finish_reason"] = "idle"
                            break
                    else:
                        terminal = 0
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__
                time.sleep(1.0)

        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
        finally:
            if session is not None:
                core.arbiter.finish(
                    session,
                    diag.get("error") or diag.get("finish_reason") or "finished",
                )
            self._post_ui("v155_mapping_finished", serial, dict(diag))

    def finish_mapping(self):
        if not self._v155_mapping_owner:
            return
        try:
            self._fresh().request_dock()
            self._set_banner("V155 · regreso a base solicitado; conservando la sesión de mapa.")
        except Exception as exc:
            messagebox.showerror("Detener mapeo", str(exc), parent=self)

    def dock(self):
        if self._v155_mapping_owner:
            return self.finish_mapping()
        return super().dock()

    def _handle_ui_event(self, kind, payload):
        if kind == "v155_mapping_started":
            serial = int(payload[0]) if payload else -1
            if serial != self._v155_mapping_serial:
                return None
            self.mapping_seen_moving = True
            self._set_banner(
                "V155 · mapeando · navegación autónoma E10 con START 2/1 · sin recoveries."
            )
            return None

        if kind == "v155_mapping_finished":
            serial = int(payload[0]) if payload else -1
            diag = dict(payload[1] or {}) if len(payload) > 1 else {}
            if serial != self._v155_mapping_serial:
                return None
            self._v155_mapping_owner = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step2_complete = not bool(diag.get("error"))
            self._v155_mapping_diag = diag
            if diag.get("error"):
                self._set_banner("V155 · mapeo finalizó con error: " + str(diag["error"]))
            else:
                self._set_banner(
                    "V155 · recorrido de mapeo finalizado · capturando geometría Xiaomi final…"
                )
                # Sólo lectura: pedimos a las capas de mapa existentes que
                # refresquen/capturen; el proxy impide cualquier write legado.
                try:
                    self.after(300, self._render_maps)
                    self.after(1800, self._render_maps)
                except Exception:
                    pass
            return None
        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        lines = [
            "V155 MAPEO FIRME · START 2/1 VALIDADO",
            "=====================================",
            f"mapeo activo={bool(self._v155_mapping_owner)}",
            f"diag mapeo={self._v155_mapping_diag or '—'}",
            "ruta física: precheck -> 10/17 build-map-ii(1) -> UN A2/1",
            "prohibido en mapeo: 2/3, 7/3, EDGE, remoto, escapes y auto-restarts",
            "pérdida LAN: sólo se registra; jamás provoca STOP/restart/dock automático",
            "navegación: firmware E10; la app observa pose/grid y captura el final",
            "",
            "",
        ]
        return "\n".join(lines) + super()._diagnostic_text()


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

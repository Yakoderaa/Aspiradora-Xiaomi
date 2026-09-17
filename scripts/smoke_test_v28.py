import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_get_cur_path_without_readable_start_end():
    from xiaomi_e10_live import XiaomiE10Live

    live = object.__new__(XiaomiE10Live)
    live._live_path_cursor = None
    live._live_path_probe_index = 0
    live._live_robot_raw_key = None
    live._live_robot_same_reads = 0

    calls = []

    def fake_get_many(defs):
        calls.append(list(defs))
        names = [item[0] for item in defs]
        if names == ["path"]:
            return {"path": ""}
        if names == ["robot"]:
            return {"robot": "0,0,0"}
        return {"path": "", "charging_base": "0,0,0", "robot": "0,0,0"}

    class Device:
        def __init__(self):
            self.calls = []

        def call_action_by(self, siid, aiid, params):
            self.calls.append((siid, aiid, list(params)))
            return {
                "code": 0,
                "out": [
                    {
                        "piid": 5,
                        "value": "[123,0,0,0,1,1.25,0.5,0,1]",
                    }
                ],
            }

    live._get_many = fake_get_many
    live.device = Device()

    state = live.local_map_state()
    check(live.device.calls, "Debe invocar get-cur-path 10/12 aunque 10/15 y 10/16 no sean legibles")
    siid, aiid, params = live.device.calls[0]
    check((siid, aiid) == (10, 12), "Debe usar la acción MIoT 10/12")
    check(params[0] == 0 and params[1] >= 1, "Debe generar localmente un rango start/end válido")
    check(len(state["path"]) == 2, "Debe parsear la trayectoria devuelta por 10/12")
    check(state["robot"]["x"] == 1.25, "La posición visual debe seguir el último punto de la trayectoria")
    check(state["action_path_count"] == 2, "Debe informar los puntos obtenidos por acción")


def test_manual_dock_cancels_pending_restart():
    import app_v28

    app = object.__new__(app_v28.App)
    app._manual_dock_guard = False
    app._manual_dock_at = 0.0
    app._auto_step2_pending = True
    app._auto_step2_scheduled = True
    app._auto_step2_serial = 7
    app._edge_session = 3
    app.mapping_active = True
    app.mapping_phase = 1
    app.mapping_seen_moving = True
    app.mapping_transitioning = False

    calls = []

    class Vacuum:
        def dock(self):
            calls.append("dock")

    app.vacuum = Vacuum()
    app._sync_mapping_step_buttons = lambda: None
    app._render_maps = lambda: None
    app._set_banner = lambda _text: None
    app._run_command = lambda _text, fn: fn()

    app.dock()

    check(calls == ["dock"], "Volver a base debe enviar exactamente una orden dock")
    check(app._manual_dock_guard, "Debe quedar activa la guardia de retorno manual")
    check(not app._auto_step2_pending and not app._auto_step2_scheduled, "Debe cancelar Paso 2 pendiente")
    check(app._auto_step2_serial == 8, "Debe invalidar cualquier callback automático ya programado")
    check(app._edge_session == 4, "Debe invalidar el watchdog EDGE anterior")
    check(not app.mapping_active and app.mapping_phase == 0, "Debe cerrar la sesión de mapeo al volver manualmente a base")


def main():
    test_get_cur_path_without_readable_start_end()
    test_manual_dock_cancels_pending_restart()
    print("SMOKE TEST V28 OK: get-cur-path 10/12 y retorno manual sin reinicios")


if __name__ == "__main__":
    main()

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_header_pose_id_drives_historical_query():
    from xiaomi_e10_live import XiaomiE10Live

    live = object.__new__(XiaomiE10Live)
    live._live_path_cursor = None
    live._live_path_probe_index = 0
    live._live_path_cache = {}
    live._live_path_last_signature = None
    live._live_path_empty_reads = 0
    live._live_path_source = "esperando trayectoria"
    live._live_stream_seq = 0
    live._live_stream_protocol_id = None
    live._live_stream_last = None
    live._live_stream_mode = False
    live._last_action_raw = None
    live._last_action_probe_range = None
    live._live_robot_raw_key = None
    live._live_robot_same_reads = 0

    current_id = 1707328529

    def fake_get_many(defs):
        names = [item[0] for item in defs]
        if names == ["path"]:
            return {"path": f"[{current_id}]"}
        if names == ["charging_base", "robot"]:
            return {"charging_base": "0,0,0", "robot": "0,0,3.01"}
        if names == ["robot"]:
            return {"robot": "0,0,3.01"}
        return {}

    class Device:
        def __init__(self):
            self.calls = []

        def call_action_by(self, siid, aiid, params):
            self.calls.append((siid, aiid, list(params)))
            return {
                "code": 0,
                "out": [{
                    "piid": 5,
                    "value": (
                        f"[{current_id - 2},"
                        "1.0,2.0,0.1,1,"
                        "1.5,2.0,0.1,1,"
                        "2.0,2.0,0.1,1]"
                    ),
                }],
            }

    live._get_many = fake_get_many
    live.device = Device()

    state = live.local_map_state()
    check(state["direct_header_id"] == current_id, "Debe conservar el pose-id aunque 10/5 no tenga coordenadas")
    check(live.device.calls, "Debe consultar 10/12 usando el pose-id real")
    siid, aiid, params = live.device.calls[0]
    check((siid, aiid) == (10, 12), "Debe usar get-cur-path 10/12")
    check(params[1] == current_id, "El final de 10/12 debe ser el pose-id actual, no un punto futuro")
    check(params[0] < params[1], "El inicio debe pedir historia anterior al pose-id actual")
    check(len(state["path"]) == 3, "Debe recuperar y parsear la trayectoria histórica")
    check(state["robot"]["x"] == 2.0, "El icono debe quedar en el último punto recuperado")
    check(state["position_source"] == "historial 10/12", "Debe informar que usa historial 10/12")


def test_v30_has_visible_diagnostics():
    import app_v30

    check("_open_map_diagnostics" in app_v30.App.__dict__, "v30 debe exponer diagnóstico visible")
    check("_copy_map_diagnostics" in app_v30.App.__dict__, "v30 debe permitir copiar el diagnóstico")


def main():
    test_header_pose_id_drives_historical_query()
    test_v30_has_visible_diagnostics()
    print("SMOKE TEST V30 OK: pose-id histórico + diagnóstico visible")


if __name__ == "__main__":
    main()

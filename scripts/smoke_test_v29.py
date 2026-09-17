import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def _blank_live():
    from xiaomi_e10_live import XiaomiE10Live

    live = object.__new__(XiaomiE10Live)
    live._live_path_cursor = None
    live._live_path_probe_index = 0
    live._live_path_cache = {}
    live._live_path_last_signature = None
    live._live_path_empty_reads = 0
    live._live_path_source = "esperando trayectoria"
    live._live_robot_raw_key = None
    live._live_robot_same_reads = 0
    live._live_stream_seq = 0
    live._live_stream_protocol_id = None
    live._live_stream_last = None
    live._live_stream_mode = False
    return live


def test_empty_frame_does_not_send_robot_back_to_base():
    live = _blank_live()

    direct_reads = iter([
        "[10,0,0,0,1,1.25,0.50,0.1,1]",
        "",
    ])

    def fake_get_many(defs):
        names = [item[0] for item in defs]
        if names == ["path"]:
            return {"path": next(direct_reads)}
        if names == ["charging_base", "robot"]:
            return {"charging_base": "0,0,0", "robot": "0,0,0"}
        if names == ["robot"]:
            return {"robot": "0,0,0"}
        return {}

    class Device:
        def call_action_by(self, siid, aiid, params):
            check((siid, aiid) == (10, 12), "El fallback debe usar 10/12")
            return {"code": 0, "out": [{"piid": 5, "value": ""}]}

    live._get_many = fake_get_many
    live.device = Device()

    first = live.local_map_state()
    second = live.local_map_state()

    check(len(first["path"]) == 2, "La primera lectura debe guardar los dos poses recibidos")
    check(first["robot"]["x"] == 1.25, "El robot debe quedar en el último pose de 10/5")
    check(len(second["path"]) == 2, "Un frame vacío no debe borrar la trayectoria acumulada")
    check(second["robot"]["x"] == 1.25, "Un frame vacío no debe devolver el icono a la base por 10/24")
    check(second["position_source"] == "última trayectoria válida", "Debe mantener la trayectoria como fuente dominante")


def test_reused_single_pose_id_becomes_live_stream():
    live = _blank_live()

    direct_reads = iter([
        "[42,5.00,7.00,0.10,1]",
        "[42,5.35,7.10,0.20,1]",
        "[42,5.70,7.20,0.25,1]",
    ])

    def fake_get_many(defs):
        names = [item[0] for item in defs]
        if names == ["path"]:
            return {"path": next(direct_reads)}
        if names == ["charging_base", "robot"]:
            return {"charging_base": "5,7,0", "robot": "5,7,0"}
        return {}

    class Device:
        def call_action_by(self, siid, aiid, params):
            return {"code": 0, "out": [{"piid": 5, "value": ""}]}

    live._get_many = fake_get_many
    live.device = Device()

    first = live.local_map_state()
    second = live.local_map_state()
    third = live.local_map_state()

    check(len(first["path"]) == 1, "La primera pose única debe conservarse como origen")
    check(len(second["path"]) == 2, "Un mismo pose-id con nuevas coordenadas debe crear una segunda muestra")
    check(len(third["path"]) == 3, "El stream debe seguir acumulando muestras con el mismo pose-id")
    check(abs(third["path"][-1]["x"] - 5.70) < 1e-9, "La última muestra debe conservar la coordenada real")
    check(third["single_pose_stream"], "Debe detectar el modo de pose-id reutilizado")
    check(live._live_path_cursor == 42, "Los ids sintéticos no deben contaminar el cursor de 10/12")
    check("pose-id reutilizado" in third["position_source"], "La UI debe identificar esta fuente de telemetría")


def test_v29_has_fast_poll_and_stable_coordinates():
    import app_v29

    check(app_v29.App.LIVE_MAP_POLL_MS <= 250, "El mapa en vivo debe sondear al menos unas 4 veces por segundo")
    check("_stable_map_status" in app_v29.App.__dict__, "v29 debe fijar una línea estable de coordenadas")
    check("_reset_robot_live_path" in app_v29.App.__dict__, "v29 debe separar las trayectorias entre sesiones")


def main():
    test_empty_frame_does_not_send_robot_back_to_base()
    test_reused_single_pose_id_becomes_live_stream()
    test_v29_has_fast_poll_and_stable_coordinates()
    print("SMOKE TEST V29 OK: trayectoria acumulada, pose-id reutilizado y polling fluido")


if __name__ == "__main__":
    main()

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class FakeDevice:
    def __init__(self):
        self.properties = []
        self.actions = []
        self.remember_state = 0

    def set_property_by(self, siid, piid, value, **kwargs):
        self.properties.append((siid, piid, value))
        if (siid, piid) == (10, 1):
            self.remember_state = int(value)
        return {"code": 0}

    def get_property_by(self, siid, piid):
        check((siid, piid) == (10, 1), "El fixture V26 sólo simula readback de remember-state")
        return [{"code": 0, "value": self.remember_state}]

    def send(self, method, payload):
        check(method == "set_properties", "El fixture V26 sólo simula set_properties")
        item = payload[0]
        check((item.get("siid"), item.get("piid")) == (10, 1), "Setter inesperado en fixture V26")
        self.remember_state = int(item.get("value"))
        self.properties.append((10, 1, self.remember_state))
        return [{"code": 0}]

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, list(params or [])))
        return {"code": 0}


class FakeLiveDevice:
    def __init__(self):
        self.action_called = False

    def call_action_by(self, siid, aiid, params=None):
        check((siid, aiid) == (10, 12), "Se esperaba get-current-path 10/12")
        self.action_called = True
        # Implementación actual: 10/12 entrega el historial en PIID 5.
        return {
            "code": 0,
            "out": [
                {"piid": 5, "value": "1,0,0,0,1,10,0,0,1"}
            ],
        }


def main():
    import app_v26
    from xiaomi_e10_edge import XiaomiE10Edge
    from xiaomi_e10_live import XiaomiE10Live

    # -4 fue el valor visto físicamente en el E10. No es un status MIoT válido
    # y nunca debe interpretarse como reposo, error o motivo para detener.
    check(XiaomiE10Edge.normalize_status(-4) is None, "status=-4 debe ignorarse como telemetría inválida")
    check(XiaomiE10Edge.normalize_status(4) == 4, "status=4 válido se perdió")
    check(XiaomiE10Edge.normalize_sweep_type(-4) is None, "sweep_type=-4 debe ignorarse")
    check(XiaomiE10Edge.normalize_sweep_type(2) == 2, "EDGE=2 válido se perdió")

    # No conectamos red: construimos la instancia sin __init__ para comprobar la
    # secuencia exacta de comandos del Paso 1.
    edge = object.__new__(XiaomiE10Edge)
    edge.device = FakeDevice()
    edge.set_water = lambda value: edge.device.set_property_by(7, 6, value)
    edge.set_suction = lambda value: edge.device.set_property_by(7, 5, value)
    edge.set_mode = lambda value: edge.device.set_property_by(2, 4, value)
    edge.set_sweep_type = lambda value: edge.device.set_property_by(2, 8, value)

    result = edge.start_mapping_perimeter()
    check(result.get("code") == 0, "La acción EDGE falsa no devolvió éxito")
    check(
        edge.device.actions[:2] == [
            (10, 17, [1]),
            (7, 3, ["", 2, 1]),
        ],
        "Paso 1 debe armar build-map 10/17 y recién después usar EDGE 7/3",
    )
    check(
        not any(a[:2] == (10, 11) for a in edge.device.actions),
        "No debe usar fallback 10/11 cuando 10/17 fue aceptado",
    )
    check(
        not any(p[:2] == (10, 1) for p in edge.device.properties),
        "V64 no debe escribir remember-state 10/1",
    )
    check((7, 6, 0) in edge.device.properties, "Mapeo debe usar agua 0")
    check((7, 5, 1) in edge.device.properties, "Mapeo debe usar succión mínima")
    check((2, 4, 0) in edge.device.properties, "Mapeo debe usar modo aspirar")
    check((2, 8, 2) in edge.device.properties, "Mapeo debe preseleccionar EDGE=2")
    check(not any(a[:2] == (2, 3) for a in edge.device.actions), "No debe volver a usarse start-only-sweep 2/3 en Paso 1")

    # Simula la implementación actual: 10/5 directo vacío y 10/12 devuelve
    # dos poses históricas en PIID 5. Inicializamos la sesión igual que __init__.
    live = object.__new__(XiaomiE10Live)
    live.device = FakeLiveDevice()
    live.reset_live_path_session()
    live._live_robot_raw_key = None
    live._live_robot_same_reads = 0

    def fake_get_many(defs):
        names = {item[0] for item in defs}
        if names == {"path"}:
            return {"path": ""}
        return {
            "charging_base": "0_0",
            "robot": "10_0_0",
        }

    live._get_many = fake_get_many
    state = live.local_map_state()
    check(len(state.get("path") or []) == 2, "Debe recuperar dos puntos desde 10/12")
    check(state.get("action_path_count") == 2, "El contador 10/12 debe reflejar los puntos recuperados")
    check(state.get("path_source") == "historial 10/12", "Debe identificar el historial 10/12 como fuente")
    check(state.get("last_pose_id") == 2, "Debe conservar el último pose-id del historial")

    check("_watch_edge_only" in app_v26.App.__dict__, "v26 debe reemplazar el watchdog EDGE")
    check("start_new_mapping" in app_v26.App.__dict__, "v26 debe mostrar el nuevo arranque EDGE")

    print("SMOKE TEST V26/V64 OK: build-map 10/17 antes de EDGE + historial 10/12")


if __name__ == "__main__":
    main()

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

    def set_property_by(self, siid, piid, value):
        self.properties.append((siid, piid, value))
        return {"code": 0}

    def call_action_by(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, list(params or [])))
        return {"code": 0}


class FakeEdge:
    from xiaomi_e10_edge import XiaomiE10Edge


def main():
    import app_v26
    from xiaomi_e10_edge import XiaomiE10Edge

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
    check(edge.device.actions == [(7, 3, ["", 2, 1])], "Paso 1 debe usar sólo set-room-clean 7/3 en modo Edge")
    check((7, 6, 0) in edge.device.properties, "Mapeo debe usar agua 0")
    check((7, 5, 1) in edge.device.properties, "Mapeo debe usar succión mínima")
    check((2, 4, 0) in edge.device.properties, "Mapeo debe usar modo aspirar")
    check((2, 8, 2) in edge.device.properties, "Mapeo debe preseleccionar EDGE=2")
    check(not any(a[:2] == (2, 3) for a in edge.device.actions), "No debe volver a usarse start-only-sweep 2/3 en Paso 1")

    check("_watch_edge_only" in app_v26.App.__dict__, "v26 debe reemplazar el watchdog EDGE")
    check("start_new_mapping" in app_v26.App.__dict__, "v26 debe mostrar el nuevo arranque EDGE")

    print("SMOKE TEST V26 OK: acción EDGE 7/3, ECO y telemetría -4 ignorada")


if __name__ == "__main__":
    main()

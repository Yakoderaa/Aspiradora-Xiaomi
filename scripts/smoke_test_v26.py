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


class FakeLiveDevice:
    def __init__(self):
        self.action_called = False

    def call_action_by(self, siid, aiid, params=None):
        check((siid, aiid) == (10, 12), "Se esperaba get-current-path 10/12")
        self.action_called = True
        # Caso real que queremos soportar: la acción responde OK pero no incluye
        # el path. El firmware actualiza 10/5 y hay que releer la propiedad.
        return {"code": 0}


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
    check(edge.device.actions == [(7, 3, ["", 2, 1])], "Paso 1 debe usar sólo set-room-clean 7/3 en modo Edge")
    check((7, 6, 0) in edge.device.properties, "Mapeo debe usar agua 0")
    check((7, 5, 1) in edge.device.properties, "Mapeo debe usar succión mínima")
    check((2, 4, 0) in edge.device.properties, "Mapeo debe usar modo aspirar")
    check((2, 8, 2) in edge.device.properties, "Mapeo debe preseleccionar EDGE=2")
    check(not any(a[:2] == (2, 3) for a in edge.device.actions), "No debe volver a usarse start-only-sweep 2/3 en Paso 1")

    # Simula la telemetría observada: current-path directo vacío y acción sin
    # payload, pero la propiedad 10/5 se llena al terminar la acción.
    live = object.__new__(XiaomiE10Live)
    live.device = FakeLiveDevice()
    live._get_many = lambda _defs: {"path": "", "path_start": 1, "path_end": 3}
    def fake_optional(siid, piid):
        if (siid, piid) == (10, 5):
            # first_pose_id=1 y dos poses: x,y,phi,update.
            return "1,0,0,0,1,10,0,0,1"
        return None
    live._optional_value = fake_optional
    state = live.local_map_state()
    check(len(state.get("path") or []) == 2, "Debe recuperar puntos desde la relectura post-acción de 10/5")
    check(state.get("reread_path_count") == 2, "El contador post-acción debe reflejar los puntos recuperados")
    check(state.get("path_source") == "current-path post-acción", "Debe priorizar la relectura más reciente")

    check("_watch_edge_only" in app_v26.App.__dict__, "v26 debe reemplazar el watchdog EDGE")
    check("start_new_mapping" in app_v26.App.__dict__, "v26 debe mostrar el nuevo arranque EDGE")

    print("SMOKE TEST V26 OK: EDGE nativo, -4 ignorado y current-path post-acción en vivo")


if __name__ == "__main__":
    main()

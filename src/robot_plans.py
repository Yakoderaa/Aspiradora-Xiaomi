import json
import time


def _fmt(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def require_origin(plan):
    origin = (plan or {}).get("device_origin")
    if not isinstance(origin, dict) or "x" not in origin or "y" not in origin:
        raise RuntimeError(
            "Todavía no tengo calibrado el origen del mapa del robot. "
            "Dejá que el E10 quede cargando en la base y abrí el mapa unos segundos."
        )
    return float(origin["x"]), float(origin["y"])


def local_point_to_device(x, y, plan):
    ox, oy = require_origin(plan)
    return float(x) + ox, float(y) + oy


def local_rect_to_device(rect, plan):
    ox, oy = require_origin(plan)
    return {
        "x0": float(rect["x0"]) + ox,
        "y0": float(rect["y0"]) + oy,
        "x1": float(rect["x1"]) + ox,
        "y1": float(rect["y1"]) + oy,
    }


def configure_mode(vacuum, mode, suction=1, water=0):
    mode = str(mode)
    suction = max(1, min(4, int(suction or 1)))
    water = max(0, min(3, int(water or 0)))

    if mode == "vacuum":
        vacuum.set_suction(suction)
        vacuum.set_water(0)
        vacuum.set_mode(0)
        return 0
    if mode == "vacuum_mop":
        vacuum.set_suction(suction)
        vacuum.set_water(max(1, water or 1))
        vacuum.set_mode(1)
        return 1
    if mode == "mop":
        vacuum.set_suction(0)
        vacuum.set_water(max(1, water or 1))
        vacuum.set_mode(2)
        return 2
    raise ValueError(f"Modo de limpieza desconocido: {mode}")


def sync_virtual_walls(vacuum, plan):
    plan = plan or {}
    walls = list(plan.get("no_go", []) or [])
    if not plan.get("virtual_walls_managed", False):
        return None

    origin = plan.get("device_origin")
    if walls and not origin:
        raise RuntimeError("No puedo sincronizar bloqueos hasta calibrar la base en el mapa.")

    encoded = []
    for index, wall in enumerate(walls, start=1):
        rect = local_rect_to_device(wall, plan)
        # El E10 usa tipo 1 para rectángulos: id_tipo_x1_y1_x2_y2.
        encoded.append(
            f"{index}_1_{_fmt(rect['x0'])}_{_fmt(rect['y1'])}_{_fmt(rect['x1'])}_{_fmt(rect['y0'])}"
        )

    # La propiedad es string aunque su contenido sea una matriz serializada.
    payload = json.dumps([len(encoded), *encoded], separators=(",", ":"))
    return vacuum.device.call_action_by(9, 6, [payload])


def start_whole_clean(vacuum, mode, suction=1, water=0):
    mode_id = configure_mode(vacuum, mode, suction, water)
    return vacuum.start(mode_id)


def start_zone_clean(vacuum, zone, plan, mode, suction=1, water=0):
    configure_mode(vacuum, mode, suction, water)
    rect = local_rect_to_device(zone, plan)
    zone_value = ",".join(
        _fmt(v)
        for v in (
            rect["x0"], rect["y0"],
            rect["x0"], rect["y1"],
            rect["x1"], rect["y1"],
            rect["x1"], rect["y0"],
        )
    )
    try:
        vacuum.device.call_action_by(9, 8, [zone_value])
    except Exception:
        vacuum.device.set_property_by(9, 2, zone_value)
    return vacuum.device.call_action_by(9, 3)


def start_point_clean(vacuum, point, plan, suction=1):
    x, y = local_point_to_device(point["x"], point["y"], plan)
    target = f"{_fmt(x)},{_fmt(y)}"
    vacuum.set_suction(max(1, min(4, int(suction or 1))))
    vacuum.set_water(0)
    vacuum.set_mode(0)
    vacuum.set_sweep_type(4)
    try:
        return vacuum.device.call_action_by(9, 9, [target])
    except Exception:
        vacuum.device.set_property_by(9, 5, target)
        return vacuum.device.call_action_by(9, 1)


def wait_for_cleaning_cycle(vacuum, timeout=3 * 60 * 60, poll_seconds=3.0):
    """Espera que una tarea empiece y luego finalice/retorne a base."""
    started = False
    started_at = time.monotonic()
    deadline = started_at + float(timeout)
    last_status = -1

    while time.monotonic() < deadline:
        status = vacuum.status()
        last_status = int(getattr(status, "status", -1))
        if last_status in (5, 6, 7):
            started = True
        if started and last_status in (0, 1, 2, 4):
            return last_status
        if not started and time.monotonic() - started_at > 35:
            raise RuntimeError(f"El E10 no inició la limpieza (estado {last_status}).")
        time.sleep(float(poll_seconds))

    raise TimeoutError(f"La limpieza superó el tiempo máximo (último estado {last_status}).")

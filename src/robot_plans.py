import json
import time

LOCAL_METERS_PER_RAW = 0.10


def _fmt(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _rect_bounds(rect):
    try:
        x0 = float(rect["x0"])
        y0 = float(rect["y0"])
        x1 = float(rect["x1"])
        y1 = float(rect["y1"])
    except Exception as exc:
        raise ValueError("Rectángulo de limpieza inválido.") from exc
    return {
        "x0": min(x0, x1),
        "y0": min(y0, y1),
        "x1": max(x0, x1),
        "y1": max(y0, y1),
    }


def _rect_area(rect):
    rect = _rect_bounds(rect)
    return max(0.0, rect["x1"] - rect["x0"]) * max(
        0.0, rect["y1"] - rect["y0"]
    )


def _rect_intersection(a, b):
    a = _rect_bounds(a)
    b = _rect_bounds(b)
    x0 = max(a["x0"], b["x0"])
    y0 = max(a["y0"], b["y0"])
    x1 = min(a["x1"], b["x1"])
    y1 = min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _rects_touch_horizontally(a, b, eps=1e-8):
    return (
        abs(float(a["y0"]) - float(b["y0"])) <= eps
        and abs(float(a["y1"]) - float(b["y1"])) <= eps
        and abs(float(a["x1"]) - float(b["x0"])) <= eps
    )


def _rects_touch_vertically(a, b, eps=1e-8):
    return (
        abs(float(a["x0"]) - float(b["x0"])) <= eps
        and abs(float(a["x1"]) - float(b["x1"])) <= eps
        and abs(float(a["y1"]) - float(b["y0"])) <= eps
    )


def _grid_cell_local_rect(grid, gx, gy):
    side = int(grid["side"])
    if not (0 <= int(gx) < side and 0 <= int(gy) < side):
        raise ValueError("Celda fuera del grid.")
    res = float(grid["resolution"])
    bx, by = grid["base_cell"]
    x0 = (float(gx) - float(bx)) * res
    x1 = (float(gx + 1) - float(bx)) * res
    y_top = (float(by) - float(gy)) * res
    y_bottom = (float(by) - float(gy + 1)) * res
    return {
        "x0": min(x0, x1),
        "y0": min(y_bottom, y_top),
        "x1": max(x0, x1),
        "y1": max(y_bottom, y_top),
    }


def constrain_rect_to_native_grid(
    rect,
    native_grid,
    no_go=None,
    max_rectangles=24,
):
    """Recorta una selección local contra la planta Xiaomi final.

    El grid recibido ya está orientado como se dibuja en pantalla (V107 refleja
    Y antes de persistirlo), por lo que estas coordenadas locales son las mismas
    que usa el editor de habitaciones/zonas. Los bloqueos eliminan celdas enteras
    para no pedir al firmware que limpie dentro de una zona prohibida.
    """
    if not isinstance(native_grid, dict):
        raise RuntimeError(
            "Este mapa todavía no tiene una geometría Xiaomi final válida."
        )

    try:
        side = int(native_grid.get("side", 0) or 0)
        resolution = float(native_grid.get("resolution", 0.0) or 0.0)
        base = list(native_grid.get("base_cell") or [])
        cells = list(native_grid.get("cells") or [])
    except Exception as exc:
        raise RuntimeError("La geometría Xiaomi guardada no es válida.") from exc

    if (
        side <= 0
        or resolution <= 0.0
        or len(base) < 2
        or len(cells) != side * side
        or not any(int(value) != 0 for value in cells)
    ):
        raise RuntimeError("La geometría Xiaomi guardada no es válida.")

    target = _rect_bounds(rect)
    blockers = []
    for item in list(no_go or []):
        try:
            blockers.append(_rect_bounds(item))
        except Exception:
            continue

    pieces_by_row = {}
    selected_cells = 0
    blocked_cells = 0
    for index, value in enumerate(cells):
        if int(value) == 0:
            continue
        gx = index % side
        gy = index // side
        cell_rect = _grid_cell_local_rect(native_grid, gx, gy)
        clipped = _rect_intersection(cell_rect, target)
        if clipped is None:
            continue

        blocked = any(
            _rect_intersection(cell_rect, wall) is not None
            for wall in blockers
        )
        if blocked:
            blocked_cells += 1
            continue

        if _rect_area(clipped) <= 1e-9:
            continue
        selected_cells += 1
        pieces_by_row.setdefault(gy, []).append(clipped)

    if selected_cells <= 0:
        raise RuntimeError(
            "La selección no contiene superficie limpiable del mapa Xiaomi "
            "o está completamente bloqueada."
        )

    # Primero fusionamos celdas contiguas de cada fila.
    row_runs = []
    for gy in sorted(pieces_by_row):
        pieces = sorted(
            pieces_by_row[gy],
            key=lambda item: (item["x0"], item["x1"]),
        )
        current = None
        for piece in pieces:
            if current is None:
                current = dict(piece)
                continue
            if _rects_touch_horizontally(current, piece):
                current["x1"] = float(piece["x1"])
            else:
                row_runs.append(current)
                current = dict(piece)
        if current is not None:
            row_runs.append(current)

    # Después unimos verticalmente runs con exactamente el mismo ancho.
    merged = []
    for run in sorted(
        row_runs,
        key=lambda item: (
            round(float(item["x0"]), 8),
            round(float(item["x1"]), 8),
            float(item["y0"]),
        ),
    ):
        match = None
        for previous in reversed(merged):
            if _rects_touch_vertically(previous, run):
                match = previous
                break
        if match is None:
            merged.append(dict(run))
        else:
            match["y1"] = float(run["y1"])

    merged = [
        _rect_bounds(item)
        for item in merged
        if _rect_area(item) > 1e-6
    ]
    merged.sort(
        key=lambda item: (
            -_rect_area(item),
            item["y0"],
            item["x0"],
        )
    )

    if len(merged) > int(max_rectangles):
        raise RuntimeError(
            "La selección es demasiado irregular para limpiarla de forma "
            "segura en una sola operación. Dividila en zonas más pequeñas."
        )

    allowed_area = sum(_rect_area(item) for item in merged)
    requested_area = _rect_area(target)
    return {
        "requested": target,
        "rectangles": merged,
        "requested_area": requested_area,
        "allowed_area": allowed_area,
        "coverage_ratio": (
            allowed_area / requested_area
            if requested_area > 1e-9
            else 0.0
        ),
        "selected_cells": int(selected_cells),
        "blocked_cells": int(blocked_cells),
        "resolution": resolution,
    }


def native_grid_contains_point(point, native_grid, no_go=None):
    try:
        x = float(point["x"])
        y = float(point["y"])
    except Exception:
        return False

    blockers = []
    for item in list(no_go or []):
        try:
            blockers.append(_rect_bounds(item))
        except Exception:
            continue
    for wall in blockers:
        if (
            wall["x0"] <= x <= wall["x1"]
            and wall["y0"] <= y <= wall["y1"]
        ):
            return False

    if not isinstance(native_grid, dict):
        return False
    try:
        side = int(native_grid.get("side", 0) or 0)
        cells = list(native_grid.get("cells") or [])
    except Exception:
        return False
    if side <= 0 or len(cells) != side * side:
        return False

    for index, value in enumerate(cells):
        if int(value) == 0:
            continue
        gx = index % side
        gy = index // side
        cell = _grid_cell_local_rect(native_grid, gx, gy)
        if (
            cell["x0"] <= x <= cell["x1"]
            and cell["y0"] <= y <= cell["y1"]
        ):
            return True
    return False


def require_origin(plan):
    origin = (plan or {}).get("device_origin")
    if not isinstance(origin, dict) or "x" not in origin or "y" not in origin:
        raise RuntimeError(
            "Todavía no tengo calibrado el origen del mapa del robot. "
            "Dejá que el E10 quede cargando en la base y abrí el mapa unos segundos."
        )
    return float(origin["x"]), float(origin["y"])


def local_point_to_device(x, y, plan):
    """Convierte metros locales del mapa a coordenadas raw del E10.

    Desde V77 el mapa local se guarda en metros, mientras que 10/22 y 10/24
    usan 1 unidad raw = 0,10 m. La operación inversa es:
        raw = origen_raw + metros / 0,10
    """
    ox, oy = require_origin(plan)
    return (
        ox + float(x) / LOCAL_METERS_PER_RAW,
        oy + float(y) / LOCAL_METERS_PER_RAW,
    )


def local_rect_to_device(rect, plan):
    x0, y0 = local_point_to_device(rect["x0"], rect["y0"], plan)
    x1, y1 = local_point_to_device(rect["x1"], rect["y1"], plan)
    return {
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
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


def sync_virtual_walls(vacuum, plan, force=False):
    plan = plan or {}
    walls = list(plan.get("no_go", []) or [])
    # Si la app nunca administró bloqueos no mandamos una lista vacía, porque
    # eso podría borrar restricciones creadas desde Mi Home.
    if not force and not plan.get("virtual_walls_managed", False):
        return None

    origin = plan.get("device_origin")
    if walls and not origin:
        raise RuntimeError("No puedo sincronizar bloqueos hasta calibrar la base en el mapa.")

    encoded = []
    for index, wall in enumerate(walls, start=1):
        rect = local_rect_to_device(wall, plan)
        encoded.append(
            f"{index}_1_{_fmt(rect['x0'])}_{_fmt(rect['y1'])}_{_fmt(rect['x1'])}_{_fmt(rect['y0'])}"
        )

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
    """Limpieza puntual respetando exactamente la succión elegida.

    Algunos firmwares del E10 cambian temporalmente la potencia al entrar en
    sweep_type=4. Por eso fijamos el modo punto primero, arrancamos la tarea y
    después reimponemos la succión solicitada durante el breve handshake inicial.
    """
    x, y = local_point_to_device(point["x"], point["y"], plan)
    target = f"{_fmt(x)},{_fmt(y)}"
    requested_suction = max(1, min(4, int(suction or 1)))

    vacuum.set_water(0)
    vacuum.set_mode(0)
    vacuum.set_sweep_type(4)
    vacuum.set_suction(requested_suction)

    try:
        result = vacuum.device.call_action_by(9, 9, [target])
    except Exception:
        vacuum.device.set_property_by(9, 5, target)
        result = vacuum.device.call_action_by(9, 1)

    # El cambio a limpieza puntual puede volver a tocar fan-level después del
    # action. Durante ~2 s comprobamos y reponemos sólo la succión pedida.
    deadline = time.monotonic() + 2.2
    while time.monotonic() < deadline:
        time.sleep(0.22)
        try:
            values = vacuum._get_many([
                ("status", 2, 1),
                ("suction", 7, 5),
            ])
            status = int(values.get("status", -1) if values.get("status") is not None else -1)
            current = int(values.get("suction", -1) if values.get("suction") is not None else -1)
            if current != requested_suction:
                vacuum.set_suction(requested_suction)
            if status in (5, 6, 7) and current == requested_suction:
                break
        except Exception:
            # La limpieza ya fue enviada; una lectura fallida no debe cancelar el objetivo.
            continue

    return result


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

import math


def _distance(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _point_line_distance(point, start, end):
    px, py = float(point[0]), float(point[1])
    x1, y1 = float(start[0]), float(start[1])
    x2, y2 = float(end[0]), float(end[1])
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    qx, qy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - qx, py - qy)


def _rdp(points, tolerance):
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    max_distance = -1.0
    max_index = 0
    for index in range(1, len(points) - 1):
        distance = _point_line_distance(points[index], start, end)
        if distance > max_distance:
            max_distance = distance
            max_index = index
    if max_distance > float(tolerance):
        left = _rdp(points[: max_index + 1], tolerance)
        right = _rdp(points[max_index:], tolerance)
        return left[:-1] + right
    return [start, end]


def build_mapped_walls(points, tolerance=0.055, jump_distance=1.20, min_step=0.025):
    """Convierte la trayectoria EDGE en polilíneas de pared estimada.

    El E10 no entrega una nube LiDAR. La mejor geometría disponible es la
    trayectoria del centro del robot mientras sigue el borde. Por eso estas
    paredes son estimadas y deliberadamente no se desplazan artificialmente
    hacia izquierda/derecha.

    app_v18 guarda dos familias de puntos en paralelo: muestras rápidas con IDs
    bajos y la trayectoria completa de get-current-path con IDs 500000+. Cuando
    existe la segunda, la usamos como fuente canónica para no duplicar paredes.
    """
    parsed = []
    for index, point in enumerate(points or []):
        try:
            if int(point.get("phase", 0) or 0) != 1:
                continue
            x = float(point["x"])
            y = float(point["y"])
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            pid = int(point.get("id", index))
            parsed.append((pid, x, y))
        except Exception:
            continue

    full_path = [item for item in parsed if item[0] >= 500000]
    live_samples = [item for item in parsed if item[0] < 500000]
    ordered = full_path if len(full_path) >= 2 else live_samples
    ordered.sort(key=lambda item: item[0])

    groups = []
    current = []
    for _pid, x, y in ordered:
        candidate = (x, y)
        if current:
            distance = _distance(current[-1], candidate)
            if distance > float(jump_distance):
                if len(current) >= 2:
                    groups.append(current)
                current = []
            elif distance < float(min_step):
                continue
        current.append(candidate)
    if len(current) >= 2:
        groups.append(current)

    walls = []
    for group in groups:
        simplified = _rdp(group, float(tolerance))
        if len(simplified) < 2:
            continue
        walls.append({
            "points": [{"x": float(x), "y": float(y)} for x, y in simplified],
            "estimated": True,
        })
    return walls

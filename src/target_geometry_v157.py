import math


def _norm_rect(item):
    x0, x1 = sorted((float(item["x0"]), float(item["x1"])))
    y0, y1 = sorted((float(item["y0"]), float(item["y1"])))
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _inside_polygon(x, y, polygon):
    pts = []
    for point in list(polygon or []):
        try:
            pts.append((float(point["x"]), float(point["y"])))
        except Exception:
            continue
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i, current in enumerate(pts):
        xi, yi = current
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _blocked(x, y, no_go):
    for item in list(no_go or []):
        try:
            rect = _norm_rect(item)
        except Exception:
            continue
        if rect["x0"] <= x <= rect["x1"] and rect["y0"] <= y <= rect["y1"]:
            return True
    return False


def room_local_rects(room, no_go=None, cell=0.35, max_rectangles=48):
    room = dict(room or {})
    polygon = list(room.get("polygon") or [])
    if len(polygon) < 3:
        return [_norm_rect(room)]

    xs = [float(p["x"]) for p in polygon]
    ys = [float(p["y"]) for p in polygon]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    step = max(0.20, float(cell))
    cols = max(1, int(math.ceil((x1 - x0) / step)))
    rows = max(1, int(math.ceil((y1 - y0) / step)))

    by_row = {}
    for iy in range(rows):
        cy0 = y0 + iy * step
        cy1 = min(y1, cy0 + step)
        cy = (cy0 + cy1) * 0.5
        for ix in range(cols):
            cx0 = x0 + ix * step
            cx1 = min(x1, cx0 + step)
            cx = (cx0 + cx1) * 0.5
            if not _inside_polygon(cx, cy, polygon):
                continue
            if _blocked(cx, cy, no_go):
                continue
            by_row.setdefault(iy, []).append(
                {"x0": cx0, "y0": cy0, "x1": cx1, "y1": cy1}
            )

    runs = []
    for iy in sorted(by_row):
        cells = sorted(by_row[iy], key=lambda r: r["x0"])
        current = None
        for item in cells:
            if current is None:
                current = dict(item)
            elif abs(current["x1"] - item["x0"]) <= 1e-8:
                current["x1"] = item["x1"]
            else:
                runs.append(current)
                current = dict(item)
        if current is not None:
            runs.append(current)

    merged = []
    for run in sorted(
        runs,
        key=lambda r: (
            round(r["x0"], 6),
            round(r["x1"], 6),
            r["y0"],
        ),
    ):
        found = None
        for prev in reversed(merged):
            if (
                abs(prev["x0"] - run["x0"]) <= 1e-8
                and abs(prev["x1"] - run["x1"]) <= 1e-8
                and abs(prev["y1"] - run["y0"]) <= 1e-8
            ):
                found = prev
                break
        if found is None:
            merged.append(dict(run))
        else:
            found["y1"] = run["y1"]

    merged = [r for r in merged if (r["x1"] - r["x0"]) > 0.05 and (r["y1"] - r["y0"]) > 0.05]
    if not merged:
        raise RuntimeError("La habitación no contiene superficie limpiable.")
    if len(merged) > int(max_rectangles):
        raise RuntimeError(
            "La habitación tiene demasiada complejidad para una limpieza dirigida segura."
        )
    return merged

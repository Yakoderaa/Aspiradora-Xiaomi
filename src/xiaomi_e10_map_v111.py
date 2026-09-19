import math

from xiaomi_e10_map_v110 import XiaomiE10MapV110


class XiaomiE10MapV111(XiaomiE10MapV110):
    """V111: retiene el área raw y resuelve su escala contra la trayectoria."""

    AREA_SCALE_HYPOTHESES = (1.0, 0.1, 0.01)
    PATH_RASTER_M = 0.10
    ROBOT_CLEAN_RADIUS_M = 0.18
    FINAL_AREA_MAX_REL_ERROR = 0.42

    def __init__(self, *args, **kwargs):
        self._v111_area_raw = 0
        self._v111_preferred_area_m2 = None
        self._v111_inferred_area_m2 = None
        self._v111_inferred_scale = None
        self._v111_reference_area_m2 = None
        self.last_v111_diagnostics = {}
        super().__init__(*args, **kwargs)

    def set_v111_area_raw(self, raw_value, preferred_area_m2=None):
        try:
            raw = int(raw_value or 0)
        except Exception:
            raw = 0
        self._v111_area_raw = max(0, raw)

        try:
            preferred = float(preferred_area_m2)
        except Exception:
            preferred = 0.0
        self._v111_preferred_area_m2 = (
            preferred
            if math.isfinite(preferred) and preferred >= self.AREA_MIN_M2
            else None
        )

        # Se recalcula con la trayectoria más reciente al entrar en modo final.
        self._v111_inferred_area_m2 = None
        self._v111_inferred_scale = None
        self._v111_reference_area_m2 = None

    @staticmethod
    def _v111_clean_path(path):
        out = []
        for item in list(path or []):
            try:
                x, y = float(item[0]), float(item[1])
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                out.append((x, y))
        return out

    @classmethod
    def _v111_path_footprint_area(cls, path):
        """Aproxima el área físicamente barrida desde el recorrido del centro.

        Sólo se usa para decidir si el entero de cleaning-area representa
        unidades, décimas o centésimas de m². No reemplaza el grid Xiaomi.
        """
        pts = cls._v111_clean_path(path)
        if not pts:
            return 0.0

        cell = float(cls.PATH_RASTER_M)
        radius = float(cls.ROBOT_CLEAN_RADIUS_M)
        stamp_radius = max(1, int(math.ceil(radius / cell)))
        occupied = set()

        def stamp(x, y):
            cx = int(round(float(x) / cell))
            cy = int(round(float(y) / cell))
            for dx in range(-stamp_radius, stamp_radius + 1):
                for dy in range(-stamp_radius, stamp_radius + 1):
                    px = dx * cell
                    py = dy * cell
                    if px * px + py * py <= (radius + cell * 0.55) ** 2:
                        occupied.add((cx + dx, cy + dy))

        previous = None
        for current in pts:
            if previous is not None:
                distance = math.hypot(
                    current[0] - previous[0],
                    current[1] - previous[1],
                )
                steps = max(1, int(math.ceil(distance / (cell * 0.70))))
                for index in range(1, steps):
                    t = index / float(steps)
                    stamp(
                        previous[0] + (current[0] - previous[0]) * t,
                        previous[1] + (current[1] - previous[1]) * t,
                    )
            stamp(*current)
            previous = current

        return float(len(occupied)) * cell * cell

    @classmethod
    def _v111_path_bbox_area(cls, path):
        pts = cls._v111_clean_path(path)
        if len(pts) < 2:
            return 0.0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        # El centro del robot no llega a las paredes; ampliamos medio diámetro
        # por lado para aproximar el recinto físico sin depender del grid.
        margin = float(cls.ROBOT_CLEAN_RADIUS_M) * 2.0
        return max(0.0, span_x + margin) * max(0.0, span_y + margin)

    def _v111_choose_target_area(self):
        if self._v111_inferred_area_m2 is not None:
            return self._v111_inferred_area_m2

        raw = int(self._v111_area_raw or 0)
        footprint = self._v111_path_footprint_area(self._v109_reference_path)
        bbox = self._v111_path_bbox_area(self._v109_reference_path)

        # Footprint refleja mejor habitaciones no rectangulares. El bbox evita
        # que una trayectoria con muchas pasadas superpuestas quede demasiado
        # chica. La mezcla sólo sirve para decidir el orden decimal del raw.
        if footprint > 0.0 and bbox > 0.0:
            reference = max(footprint, min(bbox, footprint * 1.75))
        else:
            reference = max(footprint, bbox, 0.0)
        self._v111_reference_area_m2 = reference or None

        hypotheses = []
        if raw > 0:
            for scale in self.AREA_SCALE_HYPOTHESES:
                target = float(raw) * float(scale)
                if target < self.AREA_MIN_M2 or target > 250.0:
                    continue
                if reference > 0.0:
                    # Log-ratio trata ×10 y ÷10 simétricamente.
                    distance = abs(math.log(max(target, 1e-6) / max(reference, 1e-6)))
                else:
                    distance = 0.0

                preferred_penalty = 0.0
                if self._v111_preferred_area_m2 is not None:
                    preferred_penalty = 0.18 * abs(
                        math.log(
                            max(target, 1e-6)
                            / max(self._v111_preferred_area_m2, 1e-6)
                        )
                    )
                hypotheses.append(
                    (distance + preferred_penalty, scale, target)
                )

        if hypotheses:
            hypotheses.sort(key=lambda item: item[0])
            _distance, scale, target = hypotheses[0]
            self._v111_inferred_scale = float(scale)
            self._v111_inferred_area_m2 = float(target)
        elif self._v111_preferred_area_m2 is not None:
            self._v111_inferred_scale = None
            self._v111_inferred_area_m2 = float(
                self._v111_preferred_area_m2
            )
        else:
            self._v111_inferred_scale = None
            self._v111_inferred_area_m2 = None

        self.set_v110_target_area(self._v111_inferred_area_m2)
        return self._v111_inferred_area_m2

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        if self._v107_final_mode:
            self._v111_choose_target_area()

        snapshot = super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        area_fit = dict(getattr(snapshot, "v110_area_fit", {}) or {})
        relative_error = area_fit.get("relative_error")
        try:
            relative_error_value = (
                float(relative_error)
                if relative_error is not None
                else None
            )
        except Exception:
            relative_error_value = None

        accepted = True
        reject_reason = None
        if (
            self._v107_final_mode
            and self._v111_inferred_area_m2 is not None
            and relative_error_value is not None
            and relative_error_value > float(self.FINAL_AREA_MAX_REL_ERROR)
        ):
            # Es preferible no publicar una geometría final que sabemos que no
            # corresponde al área física que acaba de limpiar el robot.
            accepted = False
            reject_reason = (
                f"área candidata difiere {relative_error_value:.1%} "
                f"del objetivo {self._v111_inferred_area_m2:.2f} m²"
            )
            snapshot.grid_cells = []
            snapshot.grid_side = 0
            snapshot.grid_walls = []
            snapshot.grid_counts = {}
            snapshot.v111_area_rejected = True

        self.last_v111_diagnostics = {
            "raw": int(self._v111_area_raw or 0),
            "preferred_m2": self._v111_preferred_area_m2,
            "reference_path_m2": self._v111_reference_area_m2,
            "inferred_scale": self._v111_inferred_scale,
            "target_m2": self._v111_inferred_area_m2,
            "grid_m2": area_fit.get("grid_m2"),
            "relative_error": relative_error_value,
            "accepted": bool(accepted),
            "reject_reason": reject_reason,
            "v110": dict(getattr(self, "last_v110_diagnostics", {}) or {}),
        }
        return snapshot

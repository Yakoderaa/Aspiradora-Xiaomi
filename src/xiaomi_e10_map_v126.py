from xiaomi_e10_map_v107 import XiaomiE10MapV107
from xiaomi_e10_map_v111 import XiaomiE10MapV111


class XiaomiE10MapV126(XiaomiE10MapV111):
    """V126: final literal V93/V107; el área queda sólo como diagnóstico."""

    def _v111_choose_target_area(self):
        # En el B112 observado, cleaning-area puede quedar en 0 o Mi Home puede
        # mostrar un área que no representa todas las pasadas/ambientes. El
        # área se conserva sólo como diagnóstico; nunca filtra ni ordena grids.
        self._v111_inferred_area_m2 = None
        self._v111_inferred_scale = None
        try:
            footprint = self._v111_path_footprint_area(self._v109_reference_path)
            bbox = self._v111_path_bbox_area(self._v109_reference_path)
            if footprint > 0.0 and bbox > 0.0:
                reference = max(footprint, min(bbox, footprint * 1.75))
            else:
                reference = max(footprint, bbox, 0.0)
            self._v111_reference_area_m2 = reference or None
        except Exception:
            self._v111_reference_area_m2 = None
        self.set_v110_target_area(None)
        return None

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        if not self._v107_final_mode:
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        # V93 ya encontró el layout válido. V109/V110 podían seleccionar luego
        # una máscara/topología más rala y convertir un frame correcto en uno
        # inválido. El final V126 toma el frame actual V93 y sólo aplica la
        # orientación V107 usada por el renderer.
        snapshot = XiaomiE10MapV107._snapshot_from_grid(
            self,
            slot,
            endpoint,
            raw,
            decoded,
        )

        cells = list(getattr(snapshot, "grid_cells", []) or [])
        metrics = dict(self._grid_metrics(cells))
        grid_m2 = (
            float(metrics.get("nonzero", 0) or 0)
            * float(self.GRID_RESOLUTION_M) ** 2
        )
        snapshot.v92_grid_metrics = dict(metrics)
        snapshot.v93_grid_metrics = dict(metrics)
        snapshot.v93_source = "v126-v93-current-frame"
        snapshot.v110_area_fit = {
            "target_m2": None,
            "grid_m2": grid_m2,
            "relative_error": None,
        }
        snapshot.v111_area_rejected = False

        self.last_v111_diagnostics = {
            "raw": int(getattr(self, "_v111_area_raw", 0) or 0),
            "preferred_m2": getattr(self, "_v111_preferred_area_m2", None),
            "reference_path_m2": getattr(self, "_v111_reference_area_m2", None),
            "inferred_scale": None,
            "target_m2": None,
            "grid_m2": grid_m2,
            "relative_error": None,
            "accepted": bool(metrics.get("valid")),
            "reject_reason": None,
            "v126_source": "V93 current frame -> V107 orientation",
        }
        return snapshot

import math

from xiaomi_e10_map_v100 import XiaomiE10MapV100
from xiaomi_e10_map_v111 import XiaomiE10MapV111


class XiaomiE10MapV112(XiaomiE10MapV111):
    """V112: conserva la geometría V93 válida y usa trayectoria como escala."""

    MIN_V93_RETENTION_RATIO = 0.84
    PATH_AXIS_MARGIN_M = 0.55
    V93_PREFERRED_BONUS = 260.0

    def __init__(self, *args, **kwargs):
        self.last_v112_diagnostics = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def _v112_min_retained_cells(cls, baseline_cells):
        try:
            baseline = max(0, int(baseline_cells or 0))
        except Exception:
            baseline = 0
        if baseline <= 0:
            return 0
        return int(math.ceil(baseline * float(cls.MIN_V93_RETENTION_RATIO)))

    @classmethod
    def _v112_span_gate(cls, physics):
        physics = dict(physics or {})
        path_span = tuple(physics.get("path_span") or (0.0, 0.0))
        floor_span = tuple(physics.get("floor_span") or (0.0, 0.0))
        if len(path_span) < 2 or len(floor_span) < 2:
            return True, {"x": True, "y": True}
        checks = []
        for p, f in zip(path_span[:2], floor_span[:2]):
            try:
                p = float(p)
                f = float(f)
            except Exception:
                checks.append(True)
                continue
            # El centro del robot no toca paredes; permitimos medio metro de
            # diferencia, pero no que la planta final sea mucho menor que el
            # recorrido que físicamente ya hizo el robot.
            checks.append(f + float(cls.PATH_AXIS_MARGIN_M) >= p)
        return all(checks), {"x": bool(checks[0]), "y": bool(checks[1])}

    def _v112_path_target_area(self):
        footprint = self._v111_path_footprint_area(self._v109_reference_path)
        bbox = self._v111_path_bbox_area(self._v109_reference_path)
        if footprint > 0.0 and bbox > 0.0:
            # No equiparamos área limpiada con área geométrica. Sólo usamos una
            # referencia prudente derivada de la trayectoria para evitar mapas
            # absurdamente pequeños.
            target = max(
                footprint,
                min(bbox, footprint * 1.30),
            )
        else:
            target = max(footprint, bbox, 0.0)
        return {
            "footprint_m2": float(footprint),
            "bbox_m2": float(bbox),
            "target_m2": float(target) if target >= self.AREA_MIN_M2 else None,
        }

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        if not self._v107_final_mode or len(self._v109_reference_path) < 8:
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        snapshot = XiaomiE10MapV100._snapshot_from_grid(
            self, slot, endpoint, raw, decoded
        )

        payload = bytes(decoded.get("payload") or b"")
        header = self._parse_header(payload) or {}
        offset = int(header.get("grid_offset", 0) or 0)
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        _current, current_options = self._decode_grid(grid_raw)

        base_grid, _robot_grid = self._device_pose_grid()
        base_cell, base_fallback = self._valid_device_base_cell(base_grid)
        preferred_key = str(getattr(self, "_v93_selected_key", "") or "")

        # Baseline: el layout/máscara que V93 ya declaró espacialmente válido.
        baseline = None
        for item in list(current_options or []):
            if self._candidate_key(item) != preferred_key:
                continue
            raw_cells = [1 if int(v) else 0 for v in list(item.get("cells") or [])]
            if len(raw_cells) != self.GRID_SIDE * self.GRID_SIDE:
                continue
            kept, detached = self._keep_main_component(raw_cells, base_cell)
            baseline = {
                "item": item,
                "raw_count": int(sum(raw_cells)),
                "main_count": int(sum(kept)),
                "cells": kept,
                "detached": int(detached),
            }
            break

        # Si el key V93 no aparece en el frame final, usamos como baseline el
        # candidato actual válido con mayor componente principal.
        if baseline is None:
            baselines = []
            for item in list(current_options or []):
                raw_cells = [1 if int(v) else 0 for v in list(item.get("cells") or [])]
                if len(raw_cells) != self.GRID_SIDE * self.GRID_SIDE:
                    continue
                metrics = dict(item.get("metrics") or self._grid_metrics(raw_cells))
                if not bool(metrics.get("valid")):
                    continue
                kept, detached = self._keep_main_component(raw_cells, base_cell)
                baselines.append((
                    int(sum(kept)),
                    int(sum(raw_cells)),
                    item,
                    kept,
                    int(detached),
                ))
            if baselines:
                baselines.sort(key=lambda row: (row[0], row[1]), reverse=True)
                main_count, raw_count, item, kept, detached = baselines[0]
                baseline = {
                    "item": item,
                    "raw_count": raw_count,
                    "main_count": main_count,
                    "cells": kept,
                    "detached": detached,
                }

        baseline_main = int((baseline or {}).get("main_count", 0) or 0)
        min_retained = self._v112_min_retained_cells(baseline_main)

        path_area = self._v112_path_target_area()
        raw_area_available = int(getattr(self, "_v111_area_raw", 0) or 0) > 0
        if raw_area_available:
            target_area = self._v111_choose_target_area()
            target_source = "cleaning-area raw + trayectoria"
        else:
            target_area = path_area.get("target_m2")
            target_source = "trayectoria física"
            self._v111_reference_area_m2 = path_area.get("target_m2")
            self._v111_inferred_area_m2 = target_area
            self._v111_inferred_scale = None
            self.set_v110_target_area(target_area)

        ranked = []
        rejected_small = 0
        rejected_span = 0
        for item in list(current_options or []):
            raw_cells = [1 if int(v) else 0 for v in list(item.get("cells") or [])]
            if len(raw_cells) != self.GRID_SIDE * self.GRID_SIDE:
                continue

            literal, detached = self._keep_main_component(raw_cells, base_cell)
            count = int(sum(literal))
            if count < 4:
                continue
            if min_retained and count < min_retained:
                rejected_small += 1
                continue

            metrics = dict(self._grid_metrics(literal))
            topology = self._v110_topology(literal, self.GRID_SIDE)
            area_score, area_diag = self._v110_area_score(count)
            topology_penalty = (
                max(0.0, float(topology["compactness"]) - 7.0) * 120.0
                + float(topology["holes"]) * 170.0
            )
            key = self._candidate_key(item)

            for orientation in self.ORIENTATIONS:
                path_score, physics = self._v109_path_score(
                    literal,
                    self.GRID_SIDE,
                    base_cell,
                    self.GRID_RESOLUTION_M,
                    self._v109_reference_path,
                    orientation,
                    metrics,
                )
                span_ok, span_axes = self._v112_span_gate(physics)
                if not span_ok:
                    rejected_span += 1
                    continue

                preference_bonus = (
                    float(self.V93_PREFERRED_BONUS)
                    if preferred_key and key == preferred_key
                    else 0.0
                )
                retention_ratio = (
                    count / float(max(1, baseline_main))
                    if baseline_main
                    else 1.0
                )
                retention_bonus = min(retention_ratio, 1.25) * 180.0
                total = (
                    float(path_score)
                    + float(area_score)
                    - float(topology_penalty)
                    + preference_bonus
                    + retention_bonus
                )
                ranked.append({
                    "score": total,
                    "path_score": float(path_score),
                    "area_score": float(area_score),
                    "item": item,
                    "cells": literal,
                    "orientation": orientation,
                    "physics": dict(physics or {}),
                    "metrics": metrics,
                    "detached": int(detached),
                    "topology": dict(topology),
                    "area": dict(area_diag),
                    "count": count,
                    "retention_ratio": retention_ratio,
                    "span_axes": span_axes,
                })

        ranked.sort(key=lambda row: row["score"], reverse=True)
        best = ranked[0] if ranked else None

        # Último seguro: si todos fallaron gates pero V93 tenía un candidato
        # válido, no retrocedemos a una máscara diminuta. Elegimos la mejor
        # orientación de ese baseline.
        fallback_to_v93 = False
        if best is None and baseline is not None:
            fallback_rows = []
            item = baseline["item"]
            cells = list(baseline["cells"])
            metrics = dict(self._grid_metrics(cells))
            topology = self._v110_topology(cells, self.GRID_SIDE)
            area_score, area_diag = self._v110_area_score(sum(cells))
            for orientation in self.ORIENTATIONS:
                path_score, physics = self._v109_path_score(
                    cells,
                    self.GRID_SIDE,
                    base_cell,
                    self.GRID_RESOLUTION_M,
                    self._v109_reference_path,
                    orientation,
                    metrics,
                )
                fallback_rows.append({
                    "score": float(path_score) + float(area_score),
                    "path_score": float(path_score),
                    "area_score": float(area_score),
                    "item": item,
                    "cells": cells,
                    "orientation": orientation,
                    "physics": dict(physics or {}),
                    "metrics": metrics,
                    "detached": int(baseline["detached"]),
                    "topology": dict(topology),
                    "area": dict(area_diag),
                    "count": int(sum(cells)),
                    "retention_ratio": 1.0,
                    "span_axes": {"x": True, "y": True},
                })
            fallback_rows.sort(key=lambda row: row["score"], reverse=True)
            best = fallback_rows[0] if fallback_rows else None
            fallback_to_v93 = best is not None

        if best is None:
            self.last_v112_diagnostics = {
                "source": "fallback-v111",
                "reason": "sin candidato final que conserve geometría física",
                "baseline_main": baseline_main,
                "min_retained": min_retained,
                "rejected_small": rejected_small,
                "rejected_span": rejected_span,
            }
            return super()._snapshot_from_grid(slot, endpoint, raw, decoded)

        final_cells = self._v109_transform_cells(
            best["cells"],
            self.GRID_SIDE,
            base_cell,
            self.GRID_RESOLUTION_M,
            best["orientation"],
        )
        final_metrics = dict(self._grid_metrics(final_cells))
        selected = best["item"]
        final_count = int(sum(final_cells))

        snapshot.grid_cells = list(final_cells)
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = self._grid_walls(final_cells, base_cell=base_cell)
        snapshot.grid_counts = {
            0: len(final_cells) - final_count,
            1: final_count,
        }
        snapshot.grid_order = (
            "v112-v93-retained|"
            + str(selected.get("label") or self._candidate_key(selected))
            + "|"
            + str(best["orientation"])
        )
        snapshot.v92_grid_metrics = dict(final_metrics)
        snapshot.v93_grid_metrics = dict(final_metrics)
        snapshot.v93_source = "v112-v93-retention-path-final"
        snapshot.v107_final_current = True
        snapshot.v109_orientation = str(best["orientation"])
        snapshot.v109_path_fit = dict(best["physics"])
        snapshot.v109_path_score = float(best["path_score"])
        snapshot.v109_selected_key = self._candidate_key(selected)
        snapshot.v110_area_fit = dict(best["area"])
        snapshot.v110_topology = dict(best["topology"])
        snapshot.v110_total_score = float(best["score"])
        snapshot.v112_baseline_cells = baseline_main
        snapshot.v112_min_retained = min_retained
        snapshot.v112_retention_ratio = float(best["retention_ratio"])
        snapshot.v112_target_source = target_source
        snapshot.v92_base_fallback = bool(base_fallback)

        grid_m2 = final_count * float(self.GRID_RESOLUTION_M) ** 2
        relative_error = (
            abs(grid_m2 - float(target_area)) / max(float(target_area), 0.01)
            if target_area is not None
            else None
        )

        self.last_v111_diagnostics = {
            "raw": int(getattr(self, "_v111_area_raw", 0) or 0),
            "preferred_m2": getattr(self, "_v111_preferred_area_m2", None),
            "reference_path_m2": path_area.get("target_m2"),
            "inferred_scale": getattr(self, "_v111_inferred_scale", None),
            "target_m2": target_area,
            "grid_m2": grid_m2,
            "relative_error": relative_error,
            "accepted": True,
            "reject_reason": None,
            "v110": dict(getattr(self, "last_v110_diagnostics", {}) or {}),
        }

        top = []
        for row in ranked[:12]:
            top.append({
                "key": self._candidate_key(row["item"]),
                "orientation": row["orientation"],
                "score": round(float(row["score"]), 2),
                "cells": int(row["count"]),
                "retention": round(float(row["retention_ratio"]), 3),
                "coverage": round(float(row["physics"].get("coverage", 0.0)), 4),
                "floor_span": row["physics"].get("floor_span"),
                "path_span": row["physics"].get("path_span"),
                "grid_m2": round(
                    int(row["count"]) * float(self.GRID_RESOLUTION_M) ** 2,
                    3,
                ),
            })

        self.last_v112_diagnostics = {
            "source": "v93-retention+path-area+topology",
            "preferred_key": preferred_key or None,
            "baseline_raw": int((baseline or {}).get("raw_count", 0) or 0),
            "baseline_main": baseline_main,
            "min_retained": min_retained,
            "selected_key": self._candidate_key(selected),
            "orientation": best["orientation"],
            "final_cells": final_count,
            "retention_ratio": float(best["retention_ratio"]),
            "target_source": target_source,
            "path_area": dict(path_area),
            "target_m2": target_area,
            "grid_m2": grid_m2,
            "rejected_small": rejected_small,
            "rejected_span": rejected_span,
            "fallback_to_v93": bool(fallback_to_v93),
            "top": top,
        }
        return snapshot

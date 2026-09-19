from xiaomi_e10_map_v100 import XiaomiE10MapV100


class XiaomiE10MapV107(XiaomiE10MapV100):
    """V107: el mapa final usa el frame Xiaomi actual, no el acumulado histórico."""

    def __init__(self, *args, **kwargs):
        self._v107_final_mode = False
        self.last_v107_diagnostics = {}
        super().__init__(*args, **kwargs)

    def set_v107_final_mode(self, enabled=True):
        self._v107_final_mode = bool(enabled)

    @staticmethod
    def _v107_mirror_y(cells, side, base_cell):
        """Refleja la planta en Y alrededor del dock, manteniendo la base fija."""
        raw = [1 if int(value) else 0 for value in (cells or [])]
        side = int(side or 0)
        if side <= 0 or len(raw) != side * side:
            return raw

        try:
            by = float(base_cell[1])
        except Exception:
            by = float(side) / 2.0

        out = [0] * len(raw)
        for idx, value in enumerate(raw):
            if not value:
                continue
            gx = idx % side
            gy = idx // side
            mirrored_y = int(round(2.0 * by - float(gy) - 1.0))
            if 0 <= mirrored_y < side:
                out[mirrored_y * side + gx] = 1
        return out

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        snapshot = super()._snapshot_from_grid(slot, endpoint, raw, decoded)
        if not self._v107_final_mode:
            return snapshot

        payload = bytes(decoded.get("payload") or b"")
        header = self._parse_header(payload) or {}
        offset = int(header.get("grid_offset", 0) or 0)
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        _current, current_options = self._decode_grid(grid_raw)

        base_grid, robot_grid = self._device_pose_grid()
        base_cell, base_fallback = self._valid_device_base_cell(base_grid)
        robot_cell = self._physical_robot_grid_cell(
            base_grid,
            robot_grid,
            base_cell,
        )

        # V93 puede elegir "acum[N]|layout|mask". Para el mapa final tomamos
        # exactamente ese layout/máscara, pero del FRAME ACTUAL, sin la unión
        # histórica que iba ensanchando la planta.
        preferred_key = str(getattr(self, "_v93_selected_key", "") or "")
        selected = None
        for item in current_options or []:
            if self._candidate_key(item) == preferred_key:
                selected = dict(item)
                break

        if selected is None:
            ranked = []
            for item in current_options or []:
                clone = dict(item)
                cells = list(clone.get("cells") or [])
                clone["metrics"] = dict(
                    clone.get("metrics") or self._grid_metrics(cells)
                )
                score, physics = self._v93_score(
                    clone,
                    base_cell,
                    robot_cell,
                )
                clone["v107_score"] = float(score)
                clone["v107_physics"] = dict(physics or {})
                ranked.append(clone)
            ranked.sort(
                key=lambda item: float(item.get("v107_score", 0.0) or 0.0),
                reverse=True,
            )
            selected = ranked[0] if ranked else None

        if not selected:
            self.last_v107_diagnostics = {
                "final_mode": True,
                "source": "fallback-super",
                "reason": "sin candidato de frame actual",
            }
            return snapshot

        cells = [1 if int(value) else 0 for value in list(selected.get("cells") or [])]
        if len(cells) != self.GRID_SIDE * self.GRID_SIDE:
            self.last_v107_diagnostics = {
                "final_mode": True,
                "source": "fallback-super",
                "reason": "frame actual con tamaño inválido",
            }
            return snapshot

        # Sólo se descartan componentes separados. No se rellenan huecos ni se
        # añaden celdas: el final debe ser lo más literal posible al blob Xiaomi.
        literal, detached = self._keep_main_component(cells, base_cell)
        before = sum(cells)
        after_component = sum(literal)

        # Nuestro renderer heredado usa Y opuesto al de la vista Mi Home.
        # Se refleja alrededor de la base para mantener el dock fijo.
        final_cells = self._v107_mirror_y(
            literal,
            self.GRID_SIDE,
            base_cell,
        )
        metrics = dict(self._grid_metrics(final_cells))

        snapshot.grid_cells = list(final_cells)
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = self._grid_walls(
            final_cells,
            base_cell=base_cell,
        )
        snapshot.grid_counts = {
            0: len(final_cells) - sum(final_cells),
            1: sum(final_cells),
        }
        snapshot.grid_order = (
            "v107-final-current|"
            + str(selected.get("label") or preferred_key or "unknown")
        )
        snapshot.v92_grid_metrics = dict(metrics)
        snapshot.v93_grid_metrics = dict(metrics)
        snapshot.v93_source = "v107-final-current-frame"
        snapshot.v107_final_current = True
        snapshot.v107_mirrored_y = True
        snapshot.v107_detached_removed = int(detached)
        snapshot.v107_before_cells = int(before)
        snapshot.v107_after_cells = int(sum(final_cells))
        snapshot.v92_base_fallback = bool(base_fallback)

        self.last_v107_diagnostics = {
            "final_mode": True,
            "source": "current-frame",
            "preferred_key": preferred_key or None,
            "selected_key": self._candidate_key(selected),
            "selected_label": selected.get("label"),
            "before": int(before),
            "after_component": int(after_component),
            "after_mirror": int(sum(final_cells)),
            "detached_removed": int(detached),
            "mirror_y": True,
            "base_cell": tuple(base_cell),
            "robot_cell": tuple(robot_cell) if robot_cell is not None else None,
            "metrics": dict(metrics),
        }
        return snapshot

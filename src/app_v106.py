import math
import statistics
import time

import app_v100
import app_v105
import app_v9


class App(app_v105.App):
    """V106: conserva el área real de cada bloque 2x2 sin fijar su permutación."""

    DENSITY_WINDOW = 5
    DENSITY_MIN_HASHES = 3
    DENSITY_MIN_SECONDS = 30.0
    DENSITY_MIN_CELLS = 4

    def __init__(self):
        self._v106_histories = {}
        self._v106_density_accepts = 0
        self._v106_density_rejects = 0
        self._v106_last_history = 0
        self._v106_last_raw_cells = 0
        self._v106_last_density_cells = 0
        self._v106_last_area_m2 = 0.0
        self._v106_last_blocks = 0
        self._v106_last_reason = "—"
        self._v106_last_age = 0.0
        self._v106_inward_choices = 0
        super().__init__()

    def _v106_history(self):
        map_id = self._v105_map_id()
        return self._v106_histories.setdefault(map_id, [])

    def start_new_mapping(self):
        self._v106_histories.pop(self._v105_map_id(), None)
        self._v106_last_history = 0
        self._v106_last_raw_cells = 0
        self._v106_last_density_cells = 0
        self._v106_last_area_m2 = 0.0
        self._v106_last_blocks = 0
        self._v106_last_reason = "nueva sesión"
        return super().start_new_mapping()

    @staticmethod
    def _v106_block_counts(grid):
        side = int(grid.get("side", 0) or 0)
        if side <= 0 or side % 2:
            return None
        cells = list(grid.get("cells") or [])
        if len(cells) != side * side:
            return None

        coarse_side = side // 2
        counts = [0] * (coarse_side * coarse_side)
        for cy in range(coarse_side):
            for cx in range(coarse_side):
                total = 0
                for dy in (0, 1):
                    for dx in (0, 1):
                        gx = cx * 2 + dx
                        gy = cy * 2 + dy
                        if int(cells[gy * side + gx]):
                            total += 1
                counts[cy * coarse_side + cx] = total
        return {
            "coarse_side": coarse_side,
            "counts": counts,
        }

    @staticmethod
    def _v106_median_low_counts(history):
        if not history:
            return []
        size = len(history[0]["counts"])
        out = [0] * size
        for idx in range(size):
            values = sorted(
                int(item["counts"][idx])
                for item in history
                if len(item.get("counts") or []) == size
            )
            if values:
                out[idx] = int(statistics.median_low(values))
        return out

    @staticmethod
    def _v106_expand_density(counts, coarse_side, base_cell):
        """Vuelve a 0,20 m sin inventar una permutación tile2.

        El número de subceldas ocupadas de cada bloque 2x2 es invariante a las
        24 permutaciones. Para ubicar esas subceldas sin agrandar el borde, se
        eligen primero las posiciones del bloque más cercanas al dock.
        """
        side = int(coarse_side) * 2
        out = [0] * (side * side)
        try:
            bx, by = float(base_cell[0]), float(base_cell[1])
        except Exception:
            bx = by = side / 2.0

        chosen_total = 0
        for cy in range(int(coarse_side)):
            for cx in range(int(coarse_side)):
                count = max(
                    0,
                    min(4, int(counts[cy * int(coarse_side) + cx] or 0)),
                )
                if count <= 0:
                    continue

                options = []
                for dy in (0, 1):
                    for dx in (0, 1):
                        gx = cx * 2 + dx
                        gy = cy * 2 + dy
                        distance2 = (
                            (float(gx) + 0.5 - bx) ** 2
                            + (float(gy) + 0.5 - by) ** 2
                        )
                        options.append((distance2, gy, gx))
                options.sort(key=lambda item: (item[0], item[1], item[2]))
                for _distance2, gy, gx in options[:count]:
                    out[gy * side + gx] = 1
                    chosen_total += 1

        return out, chosen_total

    def _v106_metrics(self, cells):
        client = getattr(self, "_v40_client", None)
        validator = getattr(client, "_grid_metrics", None)
        if callable(validator):
            try:
                return dict(validator(cells) or {})
            except Exception:
                pass
        return {}

    def _v100_live_grid_from_snapshot(self, snapshot):
        # Se parte del frame Xiaomi relajado V100, no del acumulado V92.
        raw = app_v100.App._v100_live_grid_from_snapshot(self, snapshot)
        if raw is None:
            self._v106_density_rejects += 1
            self._v106_last_reason = "V100 rechazó el frame Xiaomi"
            return None

        raw_metrics = dict(raw.get("metrics") or {})
        if bool(raw_metrics.get("valid")):
            exact = dict(raw)
            exact["v103_confident"] = True
            exact["source"] = "xiaomi-live-v57-valid"
            exact["v106_density"] = False
            self._v106_last_reason = "V57 válido: usando grid exacto 0,20 m"
            return exact

        frame_grid = self._v105_current_frame_grid(snapshot, raw)
        order = str(
            getattr(snapshot, "grid_order", "")
            or frame_grid.get("v105_frame_key")
            or ""
        )
        canonical = self._v103_canonical_candidate(order)
        if "tile2-" not in canonical:
            self._v106_density_rejects += 1
            self._v106_last_reason = (
                f"layout no tile2 ({canonical or '—'}): esperando V57"
            )
            return None

        packed = self._v106_block_counts(frame_grid)
        if not isinstance(packed, dict):
            self._v106_density_rejects += 1
            self._v106_last_reason = "no se pudo medir densidad 2x2"
            return None

        sha = str(frame_grid.get("blob_sha12") or raw.get("blob_sha12") or "")
        history = self._v106_history()
        if sha and all(item["sha"] != sha for item in history):
            history.append({
                "sha": sha,
                "counts": list(packed["counts"]),
            })
            if len(history) > int(self.DENSITY_WINDOW):
                del history[:-int(self.DENSITY_WINDOW)]

        self._v106_last_history = len(history)
        raw_cells = sum(1 for value in list(frame_grid.get("cells") or []) if int(value))
        self._v106_last_raw_cells = raw_cells

        if len(history) < int(self.DENSITY_MIN_HASHES):
            self._v106_density_rejects += 1
            self._v106_last_reason = (
                f"densidad esperando: {len(history)}/"
                f"{self.DENSITY_MIN_HASHES} hashes"
            )
            return None

        density = self._v106_median_low_counts(history)
        base_cell = list(frame_grid.get("base_cell") or raw.get("base_cell") or [60.0, 60.0])
        cells, chosen = self._v106_expand_density(
            density,
            int(packed["coarse_side"]),
            base_cell,
        )
        self._v106_inward_choices += int(chosen)

        # Conservador: si por la canonicalización aparece ruido separado,
        # conservar sólo el componente principal cercano al dock.
        client = getattr(self, "_v40_client", None)
        keeper = getattr(client, "_keep_main_component", None)
        if callable(keeper):
            try:
                cells, _removed = keeper(cells, base_cell)
            except Exception:
                pass

        metrics = self._v106_metrics(cells)
        occupied = sum(1 for value in cells if int(value))
        area_m2 = occupied * 0.20 * 0.20
        blocks = sum(1 for value in density if int(value) > 0)
        self._v106_last_density_cells = occupied
        self._v106_last_area_m2 = area_m2
        self._v106_last_blocks = blocks

        started = getattr(self, "_v74_started_at", None)
        try:
            age = (
                max(0.0, time.monotonic() - float(started))
                if started is not None else 0.0
            )
        except Exception:
            age = 0.0
        self._v106_last_age = age

        components = int(metrics.get("components", 1) or 1)
        largest_ratio = float(metrics.get("largest_ratio", 1.0) or 1.0)
        ready = bool(
            age >= float(self.DENSITY_MIN_SECONDS)
            and occupied >= int(self.DENSITY_MIN_CELLS)
            and components <= 2
            and largest_ratio >= 0.75
        )

        if not ready:
            self._v106_density_rejects += 1
            self._v106_last_reason = (
                f"densidad inmadura: {len(history)} frames · "
                f"{occupied} celdas · {age:.0f}s"
            )
            return None

        out = dict(frame_grid)
        out["side"] = int(packed["coarse_side"]) * 2
        out["resolution"] = 0.20
        out["base_cell"] = list(base_cell)
        out["cells"] = list(cells)
        out["metrics"] = {
            **metrics,
            "valid": False,
            "density_consensus": True,
        }
        out["source"] = "xiaomi-live-density-consensus"
        out["preview"] = True
        out["v103_confident"] = True
        out["v105_consensus"] = True
        out["v106_density"] = True
        out["v106_frames"] = len(history)
        out["v106_area_m2"] = area_m2
        out["v106_blocks"] = blocks

        self._v106_density_accepts += 1
        self._v106_last_reason = (
            f"densidad estable: {occupied} celdas de 0,20 m · "
            f"{area_m2:.2f} m² · {len(history)} hashes"
        )
        return out

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
            grid = self._v88_native_grid(snapshot)
        except Exception:
            grid = None

        if not isinstance(grid, dict) or not grid.get("v106_density"):
            return result

        label = getattr(self, "map_status_label", None)
        if label is None:
            return result

        area = float(grid.get("v106_area_m2", self._v106_last_area_m2) or 0.0)
        language = str(
            (getattr(self, "settings", {}) or {}).get("language", "es")
        ).lower()
        if language.startswith("en"):
            text = f"Mapping live · Xiaomi preliminary map · {area:.2f} m²"
        elif language.startswith("pt"):
            text = f"Mapeando em tempo real · mapa Xiaomi preliminar · {area:.2f} m²"
        else:
            text = f"Mapeando en tiempo real · mapa Xiaomi preliminar · {area:.2f} m²"
        self._v93_last_status_text = text
        try:
            label.configure(text=text, fg="#16a34a")
        except Exception:
            pass
        return result

    def _v88_update_legend(self, native):
        result = super()._v88_update_legend(native)
        if not native:
            return result
        label = getattr(self, "_v88_legend_source", None)
        if label is None:
            return result
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
            grid = self._v88_native_grid(snapshot)
            if isinstance(grid, dict) and grid.get("v106_density"):
                label.configure(text="Mapa Xiaomi preliminar")
        except Exception:
            pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V106 ACTIVO · densidad 2x2 sin inflar superficie",
            "================================================================",
            (
                f"historial densidad={self._v106_last_history}/"
                f"{self.DENSITY_WINDOW} · aceptados="
                f"{self._v106_density_accepts} · rechazados="
                f"{self._v106_density_rejects}"
            ),
            (
                f"frame actual={self._v106_last_raw_cells} celdas 0,20 m · "
                f"preview={self._v106_last_density_cells} celdas · "
                f"área={self._v106_last_area_m2:.2f} m² · "
                f"bloques 2x2 tocados={self._v106_last_blocks}"
            ),
            (
                f"edad={self._v106_last_age:.1f}s · "
                f"subceldas canónicas elegidas={self._v106_inward_choices}"
            ),
            f"última decisión: {self._v106_last_reason}",
            (
                "regla V106: cada bloque 2x2 conserva cuántas de sus cuatro "
                "subceldas Xiaomi estaban realmente ocupadas; ya no se rellena "
                "el bloque de 0,40 m completo"
            ),
            (
                "regla V106: la mediana baja de hasta 5 frames elimina celdas "
                "transitorias sin sumar permanentemente todos los blobs"
            ),
            (
                "regla V106: la posición exacta dentro de un bloque ambiguo se "
                "elige hacia el núcleo/dock, evitando expandir artificialmente "
                "el contorno exterior"
            ),
            (
                "regla V106: el área del preview vuelve a medirse con celdas "
                "reales de 0,20x0,20 m y el mapa retenido de V105 sigue visible "
                "durante retorno y dock"
            ),
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

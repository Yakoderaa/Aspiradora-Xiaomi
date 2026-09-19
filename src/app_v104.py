import math
import time

import app_v100
import app_v103
import app_v9


class App(app_v103.App):
    """V104: preview Xiaomi grueso, estable e independiente del layout tile2."""

    COARSE_FACTOR = 2
    COARSE_MIN_HASHES = 2
    COARSE_MIN_SECONDS = 25.0
    COARSE_MIN_CELLS = 4
    COARSE_MAX_COMPONENTS = 2
    COARSE_MIN_LARGEST_RATIO = 0.80
    COARSE_MAX_GROWTH_RATIO = 2.6

    def __init__(self):
        self._v104_coarse_state = {}
        self._v104_coarse_accepts = 0
        self._v104_coarse_rejects = 0
        self._v104_growth_resets = 0
        self._v104_last_reason = "—"
        self._v104_last_metrics = {}
        self._v104_last_source_order = "—"
        self._v104_last_age = 0.0
        self._v104_last_hashes = 0
        super().__init__()

    def _v104_map_state(self):
        map_id = self._v72_active_map_id() or "__default__"
        return self._v104_coarse_state.setdefault(
            map_id,
            {
                "hashes": set(),
                "cells": None,
                "last_count": 0,
                "ready": False,
            },
        )

    def start_new_mapping(self):
        map_id = self._v72_active_map_id() or "__default__"
        self._v104_coarse_state.pop(map_id, None)
        self._v104_last_reason = "nueva sesión"
        self._v104_last_metrics = {}
        self._v104_last_age = 0.0
        self._v104_last_hashes = 0
        return super().start_new_mapping()

    def _v74_reset_session(self):
        result = super()._v74_reset_session()
        map_id = self._v72_active_map_id() or "__default__"
        self._v104_coarse_state.pop(map_id, None)
        return result

    @staticmethod
    def _v104_metrics(cells, side):
        occupied = {
            idx for idx, value in enumerate(cells or []) if int(value) != 0
        }
        nonzero = len(occupied)
        if not occupied:
            return {
                "nonzero": 0,
                "components": 0,
                "largest": 0,
                "largest_ratio": 0.0,
                "adjacency_ratio": 0.0,
            }

        unseen = set(occupied)
        component_sizes = []
        links = 0
        for idx in occupied:
            x, y = idx % side, idx // side
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if (
                    0 <= nx < side and 0 <= ny < side
                    and ny * side + nx in occupied
                ):
                    links += 1

        while unseen:
            start = unseen.pop()
            stack = [start]
            size = 1
            while stack:
                idx = stack.pop()
                x, y = idx % side, idx // side
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < side and 0 <= ny < side):
                        continue
                    nxt = ny * side + nx
                    if nxt in unseen:
                        unseen.remove(nxt)
                        stack.append(nxt)
                        size += 1
            component_sizes.append(size)

        largest = max(component_sizes, default=0)
        return {
            "nonzero": nonzero,
            "components": len(component_sizes),
            "largest": largest,
            "largest_ratio": largest / float(nonzero),
            "adjacency_ratio": links / float(nonzero),
        }

    @classmethod
    def _v104_to_layout_invariant_coarse(cls, grid):
        side = int(grid.get("side", 0) or 0)
        factor = int(cls.COARSE_FACTOR)
        if side <= 0 or side % factor:
            return None

        cells = list(grid.get("cells") or [])
        if len(cells) != side * side:
            return None

        coarse_side = side // factor
        coarse = [0] * (coarse_side * coarse_side)
        for cy in range(coarse_side):
            for cx in range(coarse_side):
                occupied = False
                for dy in range(factor):
                    for dx in range(factor):
                        gx = cx * factor + dx
                        gy = cy * factor + dy
                        if int(cells[gy * side + gx]) != 0:
                            occupied = True
                            break
                    if occupied:
                        break
                if occupied:
                    coarse[cy * coarse_side + cx] = 1

        try:
            bx, by = grid.get("base_cell") or (side / 2.0, side / 2.0)
            base = [float(bx) / factor, float(by) / factor]
        except Exception:
            base = [coarse_side / 2.0, coarse_side / 2.0]

        return {
            "side": coarse_side,
            "resolution": float(grid.get("resolution", 0.2) or 0.2) * factor,
            "base_cell": base,
            "cells": coarse,
            "source": "xiaomi-live-coarse-invariant",
            "blob_sha12": str(grid.get("blob_sha12") or ""),
            "timestamp": grid.get("timestamp"),
            "preview": True,
            "v103_confident": True,
            "v104_coarse": True,
        }

    @staticmethod
    def _v104_union(previous, current):
        if previous is None or len(previous) != len(current):
            return list(current)
        return [
            1 if int(a) or int(b) else 0
            for a, b in zip(previous, current)
        ]

    def _v100_live_grid_from_snapshot(self, snapshot):
        # V104 parte del candidato relajado V100. No usa el gate exacto V103
        # para decidir el preview, porque justamente ese gate queda atrapado
        # entre permutaciones tile2 igualmente plausibles.
        raw = app_v100.App._v100_live_grid_from_snapshot(self, snapshot)
        if raw is None:
            self._v104_coarse_rejects += 1
            self._v104_last_reason = "V100 rechazó el frame Xiaomi"
            return None

        metrics = dict(raw.get("metrics") or {})
        if bool(metrics.get("valid")):
            exact = dict(raw)
            exact["v103_confident"] = True
            exact["source"] = "xiaomi-live-v57-valid"
            self._v104_last_reason = "grid V57 válido: usando 0,20 m"
            return exact

        order = str(getattr(snapshot, "grid_order", "") or "")
        self._v104_last_source_order = order or "—"
        if "tile2-" not in order:
            self._v104_coarse_rejects += 1
            self._v104_last_reason = (
                f"layout no tile2 ({order or '—'}): esperando V57"
            )
            return None

        coarse = self._v104_to_layout_invariant_coarse(raw)
        if coarse is None:
            self._v104_coarse_rejects += 1
            self._v104_last_reason = "no se pudo reducir el grid 120x120"
            return None

        state = self._v104_map_state()
        blob_sha = str(coarse.get("blob_sha12") or "")
        if blob_sha:
            state["hashes"].add(blob_sha)
        self._v104_last_hashes = len(state["hashes"])

        incoming = list(coarse.get("cells") or [])
        merged = self._v104_union(state.get("cells"), incoming)
        incoming_count = sum(1 for value in incoming if int(value))
        merged_count = sum(1 for value in merged if int(value))
        previous_count = int(state.get("last_count", 0) or 0)

        if previous_count > 0:
            growth_limit = max(
                float(previous_count) * float(self.COARSE_MAX_GROWTH_RATIO),
                float(previous_count + 12),
            )
            if float(merged_count) > growth_limit:
                state["cells"] = list(incoming)
                state["last_count"] = incoming_count
                state["hashes"] = {blob_sha} if blob_sha else set()
                state["ready"] = False
                self._v104_growth_resets += 1
                self._v104_coarse_rejects += 1
                self._v104_last_hashes = len(state["hashes"])
                self._v104_last_reason = (
                    f"salto coarse {previous_count}→{merged_count}; "
                    "reinicio conservador"
                )
                return None

        state["cells"] = list(merged)
        state["last_count"] = merged_count

        coarse["cells"] = list(merged)
        coarse_metrics = self._v104_metrics(
            coarse["cells"], int(coarse["side"])
        )
        coarse["metrics"] = {
            **coarse_metrics,
            "valid": False,
            "coarse_invariant": True,
        }
        self._v104_last_metrics = dict(coarse["metrics"])

        started = getattr(self, "_v74_started_at", None)
        try:
            age = (
                max(0.0, time.monotonic() - float(started))
                if started is not None else 0.0
            )
        except Exception:
            age = 0.0
        self._v104_last_age = age

        ready = bool(
            age >= float(self.COARSE_MIN_SECONDS)
            and len(state["hashes"]) >= int(self.COARSE_MIN_HASHES)
            and coarse_metrics["nonzero"] >= int(self.COARSE_MIN_CELLS)
            and coarse_metrics["components"] <= int(self.COARSE_MAX_COMPONENTS)
            and coarse_metrics["largest_ratio"]
            >= float(self.COARSE_MIN_LARGEST_RATIO)
        )

        if not ready:
            state["ready"] = False
            self._v104_coarse_rejects += 1
            self._v104_last_reason = (
                f"coarse esperando: {len(state['hashes'])}/"
                f"{self.COARSE_MIN_HASHES} hashes · "
                f"{age:.0f}/{self.COARSE_MIN_SECONDS:.0f}s · "
                f"{coarse_metrics['nonzero']}/{self.COARSE_MIN_CELLS} bloques"
            )
            return None

        state["ready"] = True
        self._v104_coarse_accepts += 1
        self._v104_last_reason = (
            f"coarse estable: {coarse_metrics['nonzero']} bloques · "
            f"{len(state['hashes'])} hashes · {age:.0f}s"
        )
        return coarse

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        if not bool(getattr(self, "mapping_active", False)):
            return result

        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
            grid = self._v88_native_grid(snapshot)
        except Exception:
            grid = None

        if not isinstance(grid, dict) or not grid.get("v104_coarse"):
            return result

        label = getattr(self, "map_status_label", None)
        if label is None:
            return result

        blocks = sum(
            1 for value in list(grid.get("cells") or []) if int(value)
        )
        language = str(
            (getattr(self, "settings", {}) or {}).get("language", "es")
        ).lower()
        if language.startswith("en"):
            text = (
                f"Mapping live · Xiaomi preliminary map · "
                f"{blocks} stable blocks"
            )
        elif language.startswith("pt"):
            text = (
                f"Mapeando em tempo real · mapa Xiaomi preliminar · "
                f"{blocks} blocos estáveis"
            )
        else:
            text = (
                f"Mapeando en tiempo real · mapa Xiaomi preliminar · "
                f"{blocks} bloques estables"
            )
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
            if isinstance(grid, dict) and grid.get("v104_coarse"):
                label.configure(text="Mapa Xiaomi preliminar")
        except Exception:
            pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        metrics = dict(self._v104_last_metrics or {})
        lines = [
            "DIAGNÓSTICO V104 ACTIVO · preview Xiaomi layout-invariant",
            "================================================================",
            (
                f"fuente tile2 recibida={self._v104_last_source_order} · "
                "permutación local ignorada=True"
            ),
            (
                f"coarse: aceptados={self._v104_coarse_accepts} · "
                f"rechazados={self._v104_coarse_rejects} · "
                f"resets crecimiento={self._v104_growth_resets}"
            ),
            (
                f"evidencia: hashes={self._v104_last_hashes}/"
                f"{self.COARSE_MIN_HASHES} · edad={self._v104_last_age:.1f}/"
                f"{self.COARSE_MIN_SECONDS:.0f}s · "
                f"bloques={metrics.get('nonzero','—')}"
            ),
            (
                f"coherencia coarse: comp={metrics.get('components','—')} · "
                f"ratio={metrics.get('largest_ratio','—')} · "
                f"ady={metrics.get('adjacency_ratio','—')}"
            ),
            f"última decisión: {self._v104_last_reason}",
            (
                "regla V104: mientras el layout 2bpp sea ambiguo, cada bloque "
                "2x2 de 0,20 m se resume en una celda física de 0,40 m"
            ),
            (
                "regla V104: tile2-1203, tile2-0213 y las demás permutaciones "
                "producen el mismo preview grueso"
            ),
            (
                "regla V104: el preview grueso aparece tras 2 hashes y 25 s; "
                "no espera las 100 celdas del gate V103"
            ),
            (
                "regla V104: cuando V57 valida el grid completo, se abandona "
                "automáticamente el preview y vuelve la resolución Xiaomi 0,20 m"
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

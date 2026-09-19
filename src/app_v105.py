import math

import app_v100
import app_v104
import app_v9


class App(app_v104.App):
    """V105: conserva el preview al volver al dock y usa consenso temporal."""

    CONSENSUS_WINDOW = 5
    CONSENSUS_RATIO = 0.60
    CONSENSUS_MIN_HASHES = 2
    CONSENSUS_MIN_SECONDS = 25.0
    CONSENSUS_MIN_BLOCKS = 3

    def __init__(self):
        self._v105_histories = {}
        self._v105_frozen_previews = {}
        self._v105_retained_hits = 0
        self._v105_consensus_accepts = 0
        self._v105_consensus_rejects = 0
        self._v105_current_frame_hits = 0
        self._v105_current_frame_fallbacks = 0
        self._v105_last_required_votes = 0
        self._v105_last_history = 0
        self._v105_last_blocks = 0
        self._v105_last_area_m2 = 0.0
        self._v105_last_reason = "—"
        self._v105_cleaning_area_raw = None
        super().__init__()

    def _v105_map_id(self):
        return self._v72_active_map_id() or "__default__"

    @staticmethod
    def _v105_copy_grid(grid):
        if not isinstance(grid, dict):
            return None
        out = dict(grid)
        out["cells"] = list(grid.get("cells") or [])
        out["base_cell"] = list(grid.get("base_cell") or [])
        out["metrics"] = dict(grid.get("metrics") or {})
        return out

    def start_new_mapping(self):
        map_id = self._v105_map_id()
        self._v105_histories.pop(map_id, None)
        self._v105_frozen_previews.pop(map_id, None)
        self._v105_last_reason = "nueva sesión"
        self._v105_last_history = 0
        self._v105_last_blocks = 0
        self._v105_last_area_m2 = 0.0
        return super().start_new_mapping()

    def _v74_reset_session(self):
        # Importante: super limpia el preview "live" de V100. El snapshot
        # congelado V105 NO se borra: tiene que seguir visible en status 3/4
        # y después del cierre local hasta que comience un mapeo nuevo.
        return super()._v74_reset_session()

    # =========================================== frame real, no unión V92
    def _v105_current_frame_grid(self, snapshot, raw):
        client = getattr(self, "_v40_client", None)
        key = getattr(client, "_v93_selected_key", None)
        frames = getattr(client, "_v93_prev_frame_cells", {}) if client is not None else {}
        cells = list((frames or {}).get(key) or [])

        if cells and len(cells) == int(raw.get("side", 0) or 0) ** 2:
            self._v105_current_frame_hits += 1
            out = dict(raw)
            out["cells"] = cells
            validator = getattr(client, "_grid_metrics", None)
            try:
                out["metrics"] = (
                    dict(validator(cells) or {}) if callable(validator) else {}
                )
            except Exception:
                out["metrics"] = {}
            out["source"] = "xiaomi-current-frame"
            out["v105_frame_key"] = str(key or "")
            return out

        self._v105_current_frame_fallbacks += 1
        return dict(raw)

    @classmethod
    def _v105_required_votes(cls, count):
        count = max(0, int(count or 0))
        if count <= 1:
            return count
        return max(2, int(math.ceil(count * float(cls.CONSENSUS_RATIO))))

    @staticmethod
    def _v105_consensus(history, required):
        if not history:
            return []
        size = len(history[0]["cells"])
        votes = [0] * size
        for item in history:
            cells = item["cells"]
            if len(cells) != size:
                continue
            for idx, value in enumerate(cells):
                if int(value):
                    votes[idx] += 1
        return [1 if count >= required else 0 for count in votes]

    def _v105_history(self):
        return self._v105_histories.setdefault(self._v105_map_id(), [])

    def _v100_live_grid_from_snapshot(self, snapshot):
        # Obtenemos primero el candidato Xiaomi relajado de V100. Si ya supera
        # V57, lo respetamos exacto. Si aún es parcial, NO usamos la unión
        # acumulada de V92 para el preview: recuperamos el frame actual.
        raw = app_v100.App._v100_live_grid_from_snapshot(self, snapshot)
        if raw is None:
            self._v105_consensus_rejects += 1
            self._v105_last_reason = "V100 rechazó el frame Xiaomi"
            return None

        raw_metrics = dict(raw.get("metrics") or {})
        if bool(raw_metrics.get("valid")):
            exact = dict(raw)
            exact["v103_confident"] = True
            exact["source"] = "xiaomi-live-v57-valid"
            exact["v105_consensus"] = False
            self._v105_last_reason = "V57 válido: usando grid exacto 0,20 m"
            return exact

        frame_grid = self._v105_current_frame_grid(snapshot, raw)
        order = str(
            getattr(snapshot, "grid_order", "")
            or frame_grid.get("v105_frame_key")
            or ""
        )
        canonical = self._v103_canonical_candidate(order)
        if "tile2-" not in canonical:
            self._v105_consensus_rejects += 1
            self._v105_last_reason = (
                f"layout no tile2 ({canonical or '—'}): esperando V57"
            )
            return None

        coarse = self._v104_to_layout_invariant_coarse(frame_grid)
        if coarse is None:
            self._v105_consensus_rejects += 1
            self._v105_last_reason = "no se pudo generar frame coarse"
            return None

        sha = str(coarse.get("blob_sha12") or "")
        history = self._v105_history()
        if sha and all(item["sha"] != sha for item in history):
            history.append({
                "sha": sha,
                "cells": list(coarse.get("cells") or []),
            })
            if len(history) > int(self.CONSENSUS_WINDOW):
                del history[:-int(self.CONSENSUS_WINDOW)]

        self._v105_last_history = len(history)
        required = self._v105_required_votes(len(history))
        self._v105_last_required_votes = required

        if len(history) < int(self.CONSENSUS_MIN_HASHES):
            self._v105_consensus_rejects += 1
            self._v105_last_reason = (
                f"consenso esperando: {len(history)}/"
                f"{self.CONSENSUS_MIN_HASHES} hashes"
            )
            return None

        consensus = self._v105_consensus(history, required)
        coarse["cells"] = list(consensus)
        metrics = self._v104_metrics(consensus, int(coarse["side"]))
        coarse["metrics"] = {
            **metrics,
            "valid": False,
            "coarse_invariant": True,
            "consensus": True,
        }
        coarse["source"] = "xiaomi-live-coarse-consensus"
        coarse["v105_consensus"] = True
        coarse["v105_votes"] = required
        coarse["v105_frames"] = len(history)
        coarse["v103_confident"] = True

        blocks = int(metrics.get("nonzero", 0) or 0)
        area_m2 = blocks * float(coarse.get("resolution", 0.4) or 0.4) ** 2
        self._v105_last_blocks = blocks
        self._v105_last_area_m2 = area_m2

        started = getattr(self, "_v74_started_at", None)
        try:
            age = (
                max(0.0, __import__("time").monotonic() - float(started))
                if started is not None else 0.0
            )
        except Exception:
            age = 0.0

        ready = bool(
            age >= float(self.CONSENSUS_MIN_SECONDS)
            and blocks >= int(self.CONSENSUS_MIN_BLOCKS)
            and int(metrics.get("components", 999) or 999) <= 2
            and float(metrics.get("largest_ratio", 0.0) or 0.0) >= 0.80
        )

        if not ready:
            self._v105_consensus_rejects += 1
            self._v105_last_reason = (
                f"consenso aún inmaduro: {len(history)} frames · "
                f"votos {required} · {blocks} bloques · {age:.0f}s"
            )
            return None

        self._v105_consensus_accepts += 1
        self._v105_last_reason = (
            f"consenso estable: {blocks} bloques · "
            f"{required}/{len(history)} votos · {area_m2:.2f} m² geométricos"
        )
        return coarse

    # ===================================== retención al retorno y al dock
    def _v100_store_live_grid(self, grid):
        changed = super()._v100_store_live_grid(grid)
        if isinstance(grid, dict):
            frozen = self._v105_copy_grid(grid)
            if frozen is not None:
                frozen["v105_retained"] = True
                self._v105_frozen_previews[self._v105_map_id()] = frozen
        return changed

    def _v88_native_grid(self, snapshot):
        grid = super()._v88_native_grid(snapshot)
        if isinstance(grid, dict):
            return grid

        frozen = self._v105_frozen_previews.get(self._v105_map_id())
        if isinstance(frozen, dict):
            self._v105_retained_hits += 1
            return self._v105_copy_grid(frozen)
        return None

    # ============================================ telemetría de área real
    def _render_status(self, status):
        try:
            self._v105_cleaning_area_raw = int(
                getattr(status, "cleaning_area", 0) or 0
            )
        except Exception:
            self._v105_cleaning_area_raw = None
        return super()._render_status(status)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        frozen = self._v105_frozen_previews.get(self._v105_map_id())
        frozen_blocks = (
            sum(1 for value in list(frozen.get("cells") or []) if int(value))
            if isinstance(frozen, dict)
            else 0
        )
        lines = [
            "DIAGNÓSTICO V105 ACTIVO · consenso + preview retenido",
            "================================================================",
            (
                f"consenso rolling: frames={self._v105_last_history}/"
                f"{self.CONSENSUS_WINDOW} · votos requeridos="
                f"{self._v105_last_required_votes} · bloques="
                f"{self._v105_last_blocks} · área geométrica="
                f"{self._v105_last_area_m2:.2f} m²"
            ),
            (
                f"consenso: aceptados={self._v105_consensus_accepts} · "
                f"rechazados={self._v105_consensus_rejects} · "
                f"frame actual usado={self._v105_current_frame_hits} · "
                f"fallback acumulado={self._v105_current_frame_fallbacks}"
            ),
            (
                f"preview congelado: existe={isinstance(frozen, dict)} · "
                f"bloques={frozen_blocks} · hits fuera de mapping_active="
                f"{self._v105_retained_hits}"
            ),
            (
                f"estado físico: mapping_active="
                f"{bool(getattr(self, 'mapping_active', False))} · "
                f"status={getattr(self, '_v84_physical_status', None)!r} · "
                f"retorno={bool(getattr(self, '_v84_returning', False))} · "
                f"dock={bool(getattr(self, '_v84_dock_latched', False))}"
            ),
            (
                f"cleaning_area MIoT 7/23 raw="
                f"{self._v105_cleaning_area_raw!r} · todavía sólo diagnóstico"
            ),
            f"última decisión: {self._v105_last_reason}",
            (
                "regla V105: el preview ya no desaparece cuando "
                "mapping_active pasa a False durante status=3 o status=4"
            ),
            (
                "regla V105: el último grid visible queda congelado hasta que "
                "llegue uno mejor o se inicie un mapeo nuevo"
            ),
            (
                "regla V105: el preview parcial usa mayoría de los últimos "
                "frames reales, no la unión acumulada V92"
            ),
            (
                "regla V105: una celda transitoria deja de inflar para siempre "
                "la superficie; debe repetirse en suficientes frames"
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

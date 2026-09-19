import time

import app_v102
import app_v9


class App(app_v102.App):
    """V103: no muestra un acumulado Xiaomi dudoso como planta real."""

    LIVE_CONFIDENCE_FRAMES = 4
    LIVE_MIN_PREVIEW_SECONDS = 60.0
    LIVE_MIN_PREVIEW_CELLS = 100
    LIVE_MAX_GROWTH_RATIO = 2.4

    def __init__(self):
        # V88 consulta este atributo sin getattr. Inicializarlo antes de toda la
        # cadena evita el error observado en V101.
        self.map_selected_xy = None

        self._v103_candidate_state = {}
        self._v103_live_gate_accepts = 0
        self._v103_live_gate_rejects = 0
        self._v103_layout_mismatches = 0
        self._v103_same_hash_reuses = 0
        self._v103_last_gate_reason = "—"
        self._v103_last_current_key = None
        self._v103_last_selected_key = None
        self._v103_last_streak = 0
        self._v103_last_sha = None
        self._v103_last_nonzero = 0
        self._v103_last_age = 0.0
        self._v103_growth_resets = 0
        super().__init__()

    @staticmethod
    def _v103_canonical_candidate(label):
        text = str(label or "").strip()
        if text.startswith("acum[") and "|" in text:
            text = text.split("|", 1)[1]
        return text

    def _v103_map_id(self):
        return self._v72_active_map_id() or "__default__"

    def _v103_state(self):
        map_id = self._v103_map_id()
        return self._v103_candidate_state.setdefault(
            map_id,
            {
                "key": None,
                "sha": None,
                "streak": 0,
                "trusted": False,
                "reason": "sin candidato",
                "last_nonzero": 0,
            },
        )

    def start_new_mapping(self):
        self._v103_candidate_state.pop(self._v103_map_id(), None)
        self._v103_last_gate_reason = "nueva sesión"
        self._v103_last_current_key = None
        self._v103_last_selected_key = None
        self._v103_last_streak = 0
        self._v103_last_sha = None
        self._v103_last_nonzero = 0
        self._v103_last_age = 0.0
        return super().start_new_mapping()

    def _v74_reset_session(self):
        result = super()._v74_reset_session()
        self._v103_candidate_state.pop(self._v103_map_id(), None)
        return result

    def _v100_live_grid_from_snapshot(self, snapshot):
        """V103 añade un gate de estabilidad encima del fast-path V100.

        V100 sólo exige coherencia geométrica relajada. Eso permitió que un
        acumulado inválido de dos frames se mostrara como planta completa.
        V103 exige que el mejor frame actual y el acumulado seleccionado usen
        el mismo layout/máscara y que esa elección sobreviva varios hashes
        distintos antes de dibujarla.
        """
        grid = super()._v100_live_grid_from_snapshot(snapshot)
        if grid is None:
            self._v103_live_gate_rejects += 1
            self._v103_last_gate_reason = "V100 rechazó el candidato"
            return None

        client = getattr(self, "_v40_client", None)
        diag = dict(getattr(client, "last_v92_diagnostics", {}) or {})
        current = dict(diag.get("current_best") or {})
        selected = dict(diag.get("selected") or {})

        current_key = self._v103_canonical_candidate(
            current.get("label")
            or getattr(snapshot, "grid_order", "")
        )
        selected_key = self._v103_canonical_candidate(
            selected.get("label")
            or getattr(snapshot, "grid_order", "")
        )
        sha = str(
            getattr(snapshot, "grid_blob_sha12", "")
            or grid.get("blob_sha12")
            or ""
        )

        self._v103_last_current_key = current_key or None
        self._v103_last_selected_key = selected_key or None
        self._v103_last_sha = sha or None

        state = self._v103_state()
        same_layout = bool(current_key and selected_key and current_key == selected_key)

        if not same_layout:
            state["key"] = selected_key or current_key or None
            state["sha"] = sha or None
            state["streak"] = 0
            state["trusted"] = False
            state["reason"] = (
                f"layout inestable: frame={current_key or '—'} "
                f"acumulado={selected_key or '—'}"
            )
            self._v103_layout_mismatches += 1
            self._v103_live_gate_rejects += 1
            self._v103_last_streak = 0
            self._v103_last_gate_reason = state["reason"]
            return None

        metrics = dict(grid.get("metrics") or {})
        nonzero = int(metrics.get("nonzero", 0) or 0)
        components = int(metrics.get("components", 999) or 999)
        largest_ratio = float(metrics.get("largest_ratio", 0.0) or 0.0)
        adjacency = float(metrics.get("adjacency_ratio", 0.0) or 0.0)
        self._v103_last_nonzero = nonzero

        started = getattr(self, "_v74_started_at", None)
        try:
            age = max(0.0, time.monotonic() - float(started)) if started is not None else 0.0
        except Exception:
            age = 0.0
        self._v103_last_age = age

        if state.get("key") != selected_key:
            state["key"] = selected_key
            state["sha"] = None
            state["streak"] = 0
            state["trusted"] = False
            state["last_nonzero"] = 0

        previous_nonzero = int(state.get("last_nonzero", 0) or 0)
        new_hash = bool(sha) and sha != state.get("sha")

        if sha and not new_hash:
            self._v103_same_hash_reuses += 1
        elif new_hash:
            growth_limit = max(
                float(previous_nonzero) * float(self.LIVE_MAX_GROWTH_RATIO),
                float(previous_nonzero + 24),
            )
            if previous_nonzero > 0 and float(nonzero) > growth_limit:
                state["sha"] = sha
                state["streak"] = 0
                state["trusted"] = False
                state["last_nonzero"] = nonzero
                state["reason"] = (
                    f"salto geométrico {previous_nonzero}→{nonzero}; "
                    "reiniciando confianza"
                )
                self._v103_growth_resets += 1
                self._v103_live_gate_rejects += 1
                self._v103_last_streak = 0
                self._v103_last_gate_reason = state["reason"]
                return None

            state["sha"] = sha
            state["streak"] = int(state.get("streak", 0) or 0) + 1
            state["last_nonzero"] = nonzero

        self._v103_last_streak = int(state.get("streak", 0) or 0)

        # Un grid que ya pasó V57 puede verse inmediatamente. Un preview
        # todavía inválido sólo aparece tras tiempo + tamaño + estabilidad.
        strong_valid = bool(metrics.get("valid"))
        delayed_preview_ready = bool(
            age >= float(self.LIVE_MIN_PREVIEW_SECONDS)
            and self._v103_last_streak >= int(self.LIVE_CONFIDENCE_FRAMES)
            and nonzero >= int(self.LIVE_MIN_PREVIEW_CELLS)
            and components <= 1
            and largest_ratio >= 0.95
            and adjacency >= 1.0
        )
        trusted = strong_valid or delayed_preview_ready

        if not trusted:
            state["trusted"] = False
            state["reason"] = (
                f"esperando mapa estable: {self._v103_last_streak}/"
                f"{self.LIVE_CONFIDENCE_FRAMES} frames · "
                f"{age:.0f}/{self.LIVE_MIN_PREVIEW_SECONDS:.0f}s · "
                f"{nonzero}/{self.LIVE_MIN_PREVIEW_CELLS} celdas"
            )
            self._v103_live_gate_rejects += 1
            self._v103_last_gate_reason = state["reason"]
            return None

        state["trusted"] = True
        state["reason"] = (
            "V57 válido"
            if strong_valid
            else (
                f"preview demorado estable · {self._v103_last_streak}/"
                f"{self.LIVE_CONFIDENCE_FRAMES} · {age:.0f}s · "
                f"{nonzero} celdas"
            )
        )
        self._v103_live_gate_accepts += 1
        self._v103_last_gate_reason = state["reason"]

        out = dict(grid)
        out["v103_confident"] = True
        out["v103_candidate_key"] = selected_key
        out["v103_streak"] = self._v103_last_streak
        return out

    def _v88_native_grid(self, snapshot):
        grid = super()._v88_native_grid(snapshot)
        if not isinstance(grid, dict):
            return None

        # Los grids persistidos/finales no son preview y conservan su gate V57.
        if not bool(grid.get("preview")):
            return grid

        # Un preview V100 viejo nunca debe colarse si V103 todavía no lo aprobó.
        if not bool(grid.get("v103_confident")):
            return None
        return grid

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()

        if not bool(getattr(self, "mapping_active", False)):
            return result

        # Si ya hay un grid V103 confiable, V102/V93 muestran el estado normal.
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        if self._v88_native_grid(snapshot) is not None:
            return result

        state = self._v103_state()
        reason = str(state.get("reason") or "")
        if not reason or reason == "sin candidato":
            return result

        label = getattr(self, "map_status_label", None)
        if label is None:
            return result

        language = str(
            (getattr(self, "settings", {}) or {}).get("language", "es")
        ).lower()
        streak = int(state.get("streak", 0) or 0)
        total = int(self.LIVE_CONFIDENCE_FRAMES)

        if language.startswith("en"):
            text = f"Mapping live · validating Xiaomi geometry · {streak}/{total}"
        elif language.startswith("pt"):
            text = f"Mapeando em tempo real · validando geometria Xiaomi · {streak}/{total}"
        else:
            text = f"Mapeando en tiempo real · validando geometría Xiaomi · {streak}/{total}"

        self._v93_last_status_text = text
        try:
            label.configure(text=text, fg="#16a34a")
        except Exception:
            pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        state = dict(self._v103_state() or {})
        lines = [
            "DIAGNÓSTICO V103 ACTIVO · gate de confianza del grid Xiaomi",
            "================================================================",
            (
                f"candidato frame={self._v103_last_current_key or '—'} · "
                f"acumulado={self._v103_last_selected_key or '—'}"
            ),
            (
                f"estabilidad={self._v103_last_streak}/"
                f"{self.LIVE_CONFIDENCE_FRAMES} · "
                f"confiable={bool(state.get('trusted'))}"
            ),
            (
                f"gate live: aceptados={self._v103_live_gate_accepts} · "
                f"rechazados={self._v103_live_gate_rejects} · "
                f"mismatches layout={self._v103_layout_mismatches} · "
                f"saltos geométricos={self._v103_growth_resets} · "
                f"hash repetido={self._v103_same_hash_reuses}"
            ),
            (
                f"espera deliberada: edad={self._v103_last_age:.1f}s · "
                f"celdas={self._v103_last_nonzero} · mínimo="
                f"{self.LIVE_MIN_PREVIEW_SECONDS:.0f}s/"
                f"{self.LIVE_MIN_PREVIEW_CELLS} celdas"
            ),
            f"último gate: {self._v103_last_gate_reason}",
            (
                "fix V103: map_selected_xy existe desde antes de inicializar "
                "la cadena V88/V101"
            ),
            (
                "regla V103: un acumulado preview inválido nunca se dibuja si "
                "el mejor frame actual y el acumulado usan layouts distintos"
            ),
            (
                "regla V103: un preview no validado por V57 requiere el mismo "
                f"layout/máscara durante {self.LIVE_CONFIDENCE_FRAMES} hashes "
                "distintos, 60 s y 100 celdas antes de convertirse en planta visible"
            ),
            (
                "regla V103: un salto fuerte de área entre blobs reinicia la "
                "confianza en vez de agrandar la planta de golpe"
            ),
            (
                "regla V103: durante el gate se mantienen base/robot y la UI "
                "dice 'validando geometría Xiaomi', no 'mapa Xiaomi en vivo'"
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

"""V160: aprendizaje persistente del mapa final Xiaomi, sin tocar navegación."""
import threading
import time

import app_v158
import app_v159
from map_learning_v160 import MapLearningStoreV160


class App(app_v159.App):
    """Acumula geometría final entre sesiones y conserva la UI rápida V159."""

    def __init__(self):
        self._v160_map_learning = None
        self._v160_map_worker = False
        self._v160_session_seq = 0
        self._v160_pending_session = None
        self._v160_pending_reason = None
        self._v160_learning_diag = {
            "state": "esperando una limpieza o mapeo finalizado",
            "sessions": 0,
        }
        super().__init__()
        self._v160_map_learning = MapLearningStoreV160(self.store.folder)

    def _v160_mark_physical_session(self, kind):
        self._v160_session_seq += 1
        map_id = self.local_map.active_map_id if self.local_map else "default"
        self._v160_pending_session = (
            f"{int(time.time() * 1000)}:{self._v160_session_seq}:{kind}:{map_id}"
        )
        self._v160_pending_reason = str(kind)
        self._v160_learning_diag = {
            "state": "sesión física terminada; esperando mapa Xiaomi final",
            "session_key": self._v160_pending_session,
            "reason": self._v160_pending_reason,
        }

    def _v160_learn_final_map(self, payload):
        capture, attempt, grid, error, decoder = payload
        if (
            grid is None
            or self._v160_map_learning is None
            or not self._v160_pending_session
        ):
            return False
        if self._v160_map_worker:
            return False

        self._v160_map_worker = True
        map_id = str(capture[3] if capture and len(capture) > 3 else self.local_map.active_map_id)
        session_key = str(self._v160_pending_session)
        reason = str(self._v160_pending_reason or "physical-session")
        source_grid = dict(grid)
        source_decoder = dict(decoder or {})

        def worker():
            learned_grid = source_grid
            learn_error = None
            try:
                candidate, diag = self._v160_map_learning.merge(
                    map_id,
                    session_key,
                    source_grid,
                    reason=reason,
                )
                if candidate is not None:
                    learned_grid = candidate
                source_decoder["v160_learning"] = dict(diag or {})
            except Exception as exc:
                diag = {
                    "accepted": False,
                    "reason": "error de aprendizaje",
                    "error": str(exc).strip() or type(exc).__name__,
                }
                source_decoder["v160_learning"] = dict(diag)
                learn_error = str(diag["error"])
            self._post_ui(
                "v160_learned_final_map",
                capture,
                attempt,
                learned_grid,
                error,
                source_decoder,
                dict(diag or {}),
                learn_error,
            )

        threading.Thread(
            target=worker,
            name="V160MapLearning",
            daemon=True,
        ).start()
        return True

    def _handle_ui_event(self, kind, payload):
        if kind in ("v157_whole_finished", "v155_mapping_finished", "v157_target_finished"):
            self._v160_mark_physical_session(kind)

        if kind == "v158_final_map":
            if self._v160_learn_final_map(payload):
                return None

        if kind == "v160_learned_final_map":
            (
                capture,
                attempt,
                grid,
                error,
                decoder,
                diag,
                learn_error,
            ) = payload
            self._v160_map_worker = False
            self._v160_learning_diag = dict(diag or {})
            if learn_error:
                self._v160_learning_diag["state"] = "falló aprendizaje; se conserva mapa Xiaomi actual"
            elif self._v160_learning_diag.get("accepted"):
                self._v160_learning_diag["state"] = "mapa Xiaomi incorporado al aprendizaje IA"
            else:
                self._v160_learning_diag["state"] = "mapa Xiaomi mostrado sin aprendizaje adicional"

            return app_v159.App._handle_ui_event(
                self,
                "v158_final_map",
                (capture, attempt, grid, error, decoder),
            )

        return super()._handle_ui_event(kind, payload)

    def _v160_full_diagnostic_text(self):
        base = app_v158.App._diagnostic_text(self)
        map_id = None
        try:
            map_id = self.local_map.active_map_id
        except Exception:
            pass
        persistent = {}
        try:
            if self._v160_map_learning is not None:
                persistent = self._v160_map_learning.diagnostic(map_id)
        except Exception as exc:
            persistent = {"error": str(exc)}
        section = (
            "\n\nAPRENDIZAJE DE MAPA V160-IA\n"
            + repr({
                "runtime": dict(self._v160_learning_diag or {}),
                "persistent": persistent,
                "rule": "actual siempre manda; histórico sólo vuelve con consenso entre sesiones",
                "navigation_changed": False,
            })
            + "\n"
        )
        return base.replace("V158-IA · DIAGNÓSTICO COMPLETO", "V160-IA · DIAGNÓSTICO COMPLETO", 1) + section

    def _v159_request_diag_refresh(self, force=False):
        if not self._v159_ready or getattr(self, "_closing", False):
            return False
        if self._v159_diag_worker:
            return False
        now = time.monotonic()
        if not force and now - self._v159_diag_last_build < self.DIAG_REBUILD_SECONDS:
            return False
        self._v159_diag_worker = True

        def worker():
            try:
                text = self._v160_full_diagnostic_text()
                error = None
            except Exception as exc:
                text = None
                error = str(exc).strip() or type(exc).__name__
            self._post_ui("v159_diag_ready", text, error, time.monotonic())

        threading.Thread(
            target=worker,
            name="V160DiagnosticSnapshot",
            daemon=True,
        ).start()
        return True

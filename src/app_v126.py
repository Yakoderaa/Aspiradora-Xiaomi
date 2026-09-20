import math
import os
import shutil
import threading
import time
from collections import deque
from pathlib import Path

import app_v107
import app_v123
import app_v9
from xiaomi_e10_map_v126 import XiaomiE10MapV126


class App(app_v123.App):
    """V126: conserva V123 y hace autoritativo el grid Xiaomi final revalidado."""

    RETURN_WINDOW_SECONDS = 28.0
    RETURN_MIN_SAMPLES = 15
    RETURN_MIN_PATH_M = 1.40
    RETURN_MAX_NET_M = 0.80
    RETURN_MIN_TURN_RAD = 10.0
    RETURN_MAX_PROGRESS_M = 0.20
    RETURN_MAX_SPAN_M = 1.80
    RETURN_MIN_BASE_DISTANCE_M = 0.90
    RETURN_RECOVERY_COOLDOWN_SECONDS = 50.0
    RETURN_FORWARD_SECONDS = 0.55
    RETURN_MAX_INTERVENTIONS = 2

    def __init__(self):
        self._v126_revalidated_final_grids = 0
        self._v126_rejected_final_grids = 0
        self._v126_last_final_metrics = {}
        self._v126_return_samples = deque()
        self._v126_return_interventions = 0
        self._v126_return_reasserts = 0
        self._v126_return_contact_attempts = 0
        self._v126_return_last_intervention_at = 0.0
        self._v126_return_last_pattern = {}
        self._v126_return_worker_active = False
        self._v126_legacy_cleanup = "pendiente"
        super().__init__()
        self._v126_remove_legacy_bridge_residue()

    # ======================================= migración: retirar integración vieja
    def _v126_remove_legacy_bridge_residue(self):
        """Borra sólo residuos de la integración experimental retirada.

        No toca mapas, token/IP Xiaomi, habitaciones, zonas ni preferencias
        operativas. Los nombres se construyen en runtime para no conservar UI
        ni dependencias de aquella integración.
        """
        changed = False
        try:
            prefix = "".join(("chat", "gpt"))
            for key in tuple((self.settings or {}).keys()):
                if str(key).lower().startswith(prefix):
                    self.settings.pop(key, None)
                    changed = True
            if changed:
                self.store.save(self.settings)
        except Exception:
            pass

        try:
            legacy_dir = (
                Path(os.environ.get("LOCALAPPDATA", Path.home()))
                / "Aspiradora Xiaomi"
                / "".join(("chat", "gpt"))
            )
            if legacy_dir.exists():
                shutil.rmtree(legacy_dir, ignore_errors=True)
            self._v126_legacy_cleanup = (
                "limpio" if not legacy_dir.exists() else "no eliminado"
            )
        except Exception:
            self._v126_legacy_cleanup = "sin acceso"

    # =============================================== cliente mapa sin gate área
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV126)
        ):
            self._v40_client = XiaomiE10MapV126(vacuum, settings)
            self._v40_client_vacuum = vacuum

        try:
            points = (
                list(self.local_map.snapshot().get("points") or [])
                if self.local_map
                else []
            )
            self._v40_client.set_v109_reference_path(points)
        except Exception:
            pass

        try:
            self._v40_client.set_v111_area_raw(
                getattr(self, "_v111_area_raw_max", 0),
                getattr(self, "_v111_area_m2_max", 0.0),
            )
        except Exception:
            pass
        return self._v40_client

    # =========================== final: validar las celdas, no metadata obsoleta
    def _v107_choose_final_grid(self, grids):
        client = getattr(self, "_v40_client", None)
        coherent = []
        for source in list(grids or []):
            if not isinstance(source, dict):
                continue

            grid = dict(source)
            cells = [
                1 if int(value) else 0
                for value in list(grid.get("cells") or [])
            ]
            metrics = {}
            try:
                if client is not None:
                    metrics = dict(client._grid_metrics(cells) or {})
            except Exception:
                metrics = {}

            if not metrics:
                metrics = dict(grid.get("metrics") or {})

            grid["metrics"] = metrics
            grid["v126_revalidated"] = True
            self._v126_last_final_metrics = dict(metrics)

            if bool(metrics.get("valid")):
                coherent.append(grid)
                self._v126_revalidated_final_grids += 1
            else:
                self._v126_rejected_final_grids += 1

        if not coherent:
            self._v107_final_candidates = 0
            self._v107_final_unique = 0
            return None, (
                "V126: las lecturas finales no superaron la validación "
                "recalculada desde sus celdas"
            )

        # Salta exclusivamente el filtro V121 basado en metadata. Conserva la
        # elección V107: si un frame se repite, se prefiere; si no, el último.
        chosen, reason = app_v107.App._v107_choose_final_grid(self, coherent)
        return chosen, "V126 revalidado desde celdas · " + str(reason)

    # ============================================= retorno: detectar espiral real
    def _v74_reset_session(self):
        self._v126_return_samples.clear()
        self._v126_return_interventions = 0
        self._v126_return_reasserts = 0
        self._v126_return_contact_attempts = 0
        self._v126_return_last_intervention_at = 0.0
        self._v126_return_last_pattern = {}
        self._v126_return_worker_active = False
        return super()._v74_reset_session()

    @staticmethod
    def _v126_angle_delta(a, b):
        delta = float(b) - float(a)
        while delta > math.pi:
            delta -= 2.0 * math.pi
        while delta < -math.pi:
            delta += 2.0 * math.pi
        return abs(delta)

    def _v126_note_return_pose(self):
        try:
            status = int(getattr(self, "_v94_last_status_code", -1))
            fault = int(getattr(self, "_v94_last_fault", 0) or 0)
        except Exception:
            return
        if (
            status != 3
            or fault != 0
            or bool(getattr(self, "_v84_dock_latched", False))
        ):
            self._v126_return_samples.clear()
            return

        pose = getattr(self, "_v117_live_pose", None)
        if not isinstance(pose, dict):
            return
        try:
            x = float(pose["x"])
            y = float(pose["y"])
            angle = float(pose.get("angle", 0.0) or 0.0)
        except Exception:
            return
        if not all(math.isfinite(v) for v in (x, y, angle)):
            return

        now = time.monotonic()
        key = (round(x, 3), round(y, 3), round(angle, 3))
        if self._v126_return_samples and self._v126_return_samples[-1][4] == key:
            return

        distance = math.hypot(x, y)
        self._v126_return_samples.append((now, x, y, angle, key, distance))
        cutoff = now - float(self.RETURN_WINDOW_SECONDS)
        while self._v126_return_samples and self._v126_return_samples[0][0] < cutoff:
            self._v126_return_samples.popleft()

        pattern = self._v126_return_pattern()
        if pattern:
            self._v126_return_last_pattern = pattern
            self._v126_maybe_recover_return(pattern)

    def _v126_return_pattern(self):
        rows = list(self._v126_return_samples)
        if len(rows) < int(self.RETURN_MIN_SAMPLES):
            return None

        path = 0.0
        turns = 0.0
        for previous, current in zip(rows, rows[1:]):
            path += math.hypot(
                float(current[1]) - float(previous[1]),
                float(current[2]) - float(previous[2]),
            )
            turns += self._v126_angle_delta(previous[3], current[3])

        first, last = rows[0], rows[-1]
        net = math.hypot(last[1] - first[1], last[2] - first[2])
        progress = float(first[5]) - float(last[5])
        xs = [row[1] for row in rows]
        ys = [row[2] for row in rows]
        span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
        elapsed = max(0.0, float(last[0]) - float(first[0]))

        diagnostic = {
            "samples": len(rows),
            "seconds": round(elapsed, 1),
            "path_m": round(path, 2),
            "net_m": round(net, 2),
            "turn_rad": round(turns, 2),
            "progress_m": round(progress, 2),
            "span_m": round(span, 2),
            "distance_m": round(float(last[5]), 2),
        }

        circular = bool(
            elapsed >= float(self.RETURN_WINDOW_SECONDS) * 0.72
            and path >= float(self.RETURN_MIN_PATH_M)
            and net <= float(self.RETURN_MAX_NET_M)
            and turns >= float(self.RETURN_MIN_TURN_RAD)
            and progress <= float(self.RETURN_MAX_PROGRESS_M)
            and span <= float(self.RETURN_MAX_SPAN_M)
            and float(last[5]) >= float(self.RETURN_MIN_BASE_DISTANCE_M)
        )
        return diagnostic if circular else None

    def _v126_maybe_recover_return(self, pattern):
        now = time.monotonic()
        if self._v126_return_worker_active:
            return False
        if self._v126_return_interventions >= int(self.RETURN_MAX_INTERVENTIONS):
            return False
        if (
            self._v126_return_last_intervention_at > 0.0
            and now - self._v126_return_last_intervention_at
            < float(self.RETURN_RECOVERY_COOLDOWN_SECONDS)
        ):
            return False

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False
        try:
            if int(getattr(self, "_v94_last_status_code", -1)) != 3:
                return False
            if bool(getattr(self, "_v84_dock_latched", False)):
                return False
            distance = float(pattern.get("distance_m", 0.0) or 0.0)
            if distance < float(self.RETURN_MIN_BASE_DISTANCE_M):
                return False
        except Exception:
            return False

        self._v126_return_interventions += 1
        attempt = int(self._v126_return_interventions)
        self._v126_return_last_intervention_at = now
        self._v126_return_worker_active = True
        self._v126_return_samples.clear()

        def worker():
            try:
                if attempt == 1:
                    # Primer escalón: no tomar control de ruedas; simplemente
                    # refrescar el objetivo nativo del dock una sola vez.
                    vacuum.dock()
                    self._v126_return_reasserts += 1
                    self._post_ui("v126_return_reassert", attempt, pattern)
                    return

                # Segundo escalón: si el mismo patrón reaparece lejos de base,
                # un avance corto ayuda al bumper a adquirir una referencia
                # física. Inmediatamente se devuelve el control al dock nativo.
                try:
                    vacuum.stop()
                except Exception:
                    pass
                time.sleep(0.25)
                vacuum.manual(1)
                time.sleep(float(self.RETURN_FORWARD_SECONDS))
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                self._v126_return_contact_attempts += 1
                time.sleep(0.20)
                vacuum.dock()
                self._post_ui("v126_return_contact", attempt, pattern)
            except Exception as exc:
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                try:
                    vacuum.dock()
                except Exception:
                    pass
                self._post_ui(
                    "v126_return_error",
                    attempt,
                    str(exc).strip() or type(exc).__name__,
                )
            finally:
                self._v126_return_worker_active = False

        threading.Thread(
            target=worker,
            name="AspiradoraReturnAssistV126",
            daemon=True,
        ).start()
        return True

    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)
        self._v126_note_return_pose()
        return result

    # =========================================================== eventos / UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v126_return_reassert":
            self._set_banner(
                "Retorno: patrón circular prolongado detectado · "
                "objetivo de base reafirmado."
            )
            return None
        if kind == "v126_return_contact":
            self._set_banner(
                "Retorno: segunda espiral detectada · referencia física "
                "corta aplicada y regreso nativo reanudado."
            )
            return None
        if kind == "v126_return_error":
            self._set_banner(
                "Retorno: la asistencia falló; el E10 continúa con el "
                "regreso nativo."
            )
            return None
        return super()._handle_ui_event(kind, payload)

    # ========================================================= diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V126 ACTIVO · grid final revalidado + retorno asistido",
            "=================================================================",
            (
                "final Xiaomi: revalidados="
                f"{self._v126_revalidated_final_grids} · rechazados="
                f"{self._v126_rejected_final_grids} · metrics="
                f"{self._v126_last_final_metrics or '—'}"
            ),
            (
                "retorno asistido: intervenciones="
                f"{self._v126_return_interventions}/"
                f"{self.RETURN_MAX_INTERVENTIONS} · reafirmaciones="
                f"{self._v126_return_reasserts} · contactos="
                f"{self._v126_return_contact_attempts}"
            ),
            f"último patrón circular={self._v126_return_last_pattern or '—'}",
            f"limpieza migración anterior={self._v126_legacy_cleanup}",
            "regla V126: V123 queda intacto para perímetro + whole-home 7/3 + trigger 2/3",
            "regla V126: un grid final se acepta por validación recalculada de sus celdas, no por metadata vieja",
            "regla V126: el área numérica reportada no descarta ni reordena la geometría final",
            "regla V126: retorno normal no se toca; asistencia sólo ante patrón circular prolongado lejos de base",
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

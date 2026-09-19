import collections
import math
import threading
import time

import app_v106
import app_v9
from xiaomi_e10_map_v107 import XiaomiE10MapV107


class App(app_v106.App):
    """V107: mapa final Xiaomi primero + UI de bajo costo."""

    # La prioridad deja de ser "tiempo real". El robot puede moverse con un
    # pequeño retraso visual si eso mantiene Tk siempre responsivo.
    RENDER_MIN_INTERVAL_SECONDS = 1.50
    UI_EVENT_BUDGET = 4
    LOCAL_ACTIVE_POLL_MS = 900
    LOCAL_IDLE_POLL_MS = 3200
    MAP_OVERVIEW_REFRESH_SECONDS = 12.0

    # No se descarga/decodifica mapa Cloud durante la limpieza. Se captura al
    # final, cuando Mi Home también dispone de la planta más madura.
    CLOUD_FILE_POLL_SECONDS = 9999.0
    CLOUD_UPLOAD_INTERVAL_SECONDS = 9999.0

    FINAL_DOCK_READS = 3
    FINAL_DOCK_SETTLE_SECONDS = 1.20
    FULL_UI_REFRESH_SECONDS = 15.0

    def __init__(self):
        self._v107_hide_surface_until_final = True
        self._v107_final_saved = False
        self._v107_final_grid = None
        self._v107_final_candidates = 0
        self._v107_final_unique = 0
        self._v107_final_choice_reason = "—"
        self._v107_final_capture_errors = []
        self._v107_cloud_polls_blocked = 0
        self._v107_theme_refresh_skipped = 0
        self._v107_last_full_refresh = 0.0
        self._v107_canvas_ready = set()
        self._v107_canvas_config_skipped = 0
        self._v107_surface_suppressed = 0
        self._v107_final_render_count = 0
        super().__init__()

    # ====================================================== cliente final V107
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV107)
        ):
            self._v40_client = XiaomiE10MapV107(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def start_new_mapping(self):
        self._v107_hide_surface_until_final = True
        self._v107_final_saved = False
        self._v107_final_grid = None
        self._v107_final_candidates = 0
        self._v107_final_unique = 0
        self._v107_final_choice_reason = "nueva sesión"
        self._v107_final_capture_errors = []
        return super().start_new_mapping()

    # =================================================== Cloud sólo al finalizar
    def _v38_maybe_poll_map_file(self):
        # Durante una limpieza ya tenemos 10/24 por LAN para pose/trayectoria.
        # Decodificar el blob cada pocos segundos no mejora el objetivo actual y
        # fue una fuente importante de carga/stalls.
        if not bool(getattr(self, "_v93_finalizing", False)):
            self._v107_cloud_polls_blocked += 1
            return False
        # Las lecturas finales V107 se hacen explícitamente en su propio worker;
        # tampoco necesitamos que el watchdog abra otro worker en paralelo.
        return False

    # ============================================== ocultar superficies dudosas
    def _v88_native_grid(self, snapshot):
        if bool(getattr(self, "_v107_hide_surface_until_final", False)):
            return None
        return super()._v88_native_grid(snapshot)

    def _v87_floor_cells(self, snapshot):
        # Evita construir cientos de celdas de fallback en cada render.
        if bool(getattr(self, "_v107_hide_surface_until_final", False)):
            self._v107_surface_suppressed += 1
            return set()
        try:
            if super()._v88_native_grid(snapshot) is not None:
                self._v107_surface_suppressed += 1
                return set()
        except Exception:
            pass
        return super()._v87_floor_cells(snapshot)

    def _v88_update_legend(self, native):
        result = super()._v88_update_legend(native)
        label = getattr(self, "_v88_legend_source", None)
        if label is None:
            return result
        try:
            if bool(getattr(self, "_v107_hide_surface_until_final", False)):
                label.configure(text="Esperando mapa final Xiaomi")
            elif self._v107_final_saved:
                label.configure(text="Mapa Xiaomi final")
        except Exception:
            pass
        return result

    # ========================================== no recorrer toda la UI por frame
    def _v99_schedule_refresh(self, root=None):
        if root is not None:
            return super()._v99_schedule_refresh(root)

        now = time.monotonic()
        if (
            self._v107_last_full_refresh > 0.0
            and now - self._v107_last_full_refresh
            < float(self.FULL_UI_REFRESH_SECONDS)
        ):
            self._v107_theme_refresh_skipped += 1
            return None

        self._v107_last_full_refresh = now
        return super()._v99_schedule_refresh()

    # =============================================== canvas sin configure spam
    def _v100_force_canvas_bg(self, canvas, thumbnail=False):
        try:
            key = str(canvas)
        except Exception:
            key = repr(canvas)

        if key in self._v107_canvas_ready:
            self._v107_canvas_config_skipped += 1
            return

        try:
            current = str(canvas.cget("background")).lower()
        except Exception:
            current = ""

        if current == str(self.MAP_BG).lower():
            self._v107_canvas_ready.add(key)
            self._v107_canvas_config_skipped += 1
            return

        result = super()._v100_force_canvas_bg(
            canvas,
            thumbnail=thumbnail,
        )
        self._v107_canvas_ready.add(key)
        return result

    # ============================================= captura final literal Xiaomi
    @staticmethod
    def _v107_grid_from_snapshot(snapshot):
        if snapshot is None:
            return None
        try:
            side = int(getattr(snapshot, "grid_side", 0) or 0)
            resolution = float(
                getattr(snapshot, "grid_resolution", 0.0) or 0.0
            )
            cells = [
                1 if int(value) else 0
                for value in list(getattr(snapshot, "grid_cells", []) or [])
            ]
            base = list(
                getattr(snapshot, "grid_base_cell", None)
                or (side / 2.0, side / 2.0)
            )
        except Exception:
            return None

        if (
            side <= 0
            or len(cells) != side * side
            or resolution <= 0.0
            or not any(cells)
            or len(base) < 2
        ):
            return None

        return {
            "side": side,
            "resolution": resolution,
            "base_cell": [float(base[0]), float(base[1])],
            "cells": cells,
            "source": "xiaomi-v107-final-current",
            "blob_sha12": str(
                getattr(snapshot, "grid_blob_sha12", "") or ""
            ),
            "timestamp": getattr(snapshot, "upload_date", None),
            "metrics": dict(
                getattr(snapshot, "v93_grid_metrics", {}) or {}
            ),
            "v107_mirrored_y": bool(
                getattr(snapshot, "v107_mirrored_y", False)
            ),
            "v107_final_current": bool(
                getattr(snapshot, "v107_final_current", False)
            ),
            "grid_order": str(
                getattr(snapshot, "grid_order", "") or ""
            ),
        }

    @staticmethod
    def _v107_grid_signature(grid):
        if not isinstance(grid, dict):
            return None
        cells = list(grid.get("cells") or [])
        occupied = tuple(
            index for index, value in enumerate(cells) if int(value)
        )
        return (
            int(grid.get("side", 0) or 0),
            round(float(grid.get("resolution", 0.0) or 0.0), 6),
            tuple(round(float(v), 4) for v in grid.get("base_cell") or ()),
            hash(occupied),
        )

    def _v107_choose_final_grid(self, grids):
        usable = [grid for grid in list(grids or []) if isinstance(grid, dict)]
        if not usable:
            return None, "sin lecturas finales utilizables"

        signatures = [self._v107_grid_signature(grid) for grid in usable]
        counts = collections.Counter(signatures)
        repeated = {
            signature
            for signature, count in counts.items()
            if signature is not None and count >= 2
        }
        self._v107_final_candidates = len(usable)
        self._v107_final_unique = len(
            {signature for signature in signatures if signature is not None}
        )

        if repeated:
            for grid, signature in reversed(list(zip(usable, signatures))):
                if signature in repeated:
                    return (
                        dict(grid),
                        "frame final repetido en al menos 2 lecturas",
                    )

        return dict(usable[-1]), "tres lecturas distintas: se usa la más reciente"

    def _v93_schedule_final_reads(self):
        serial = int(getattr(self, "_v74_mapping_serial", 0) or 0)
        if self._v93_finalizing or self._v93_finalized_serial == serial:
            return False
        if not getattr(self, "vacuum", None):
            return False

        self._v93_finalizing = True
        self._v93_final_read_success = 0
        self._v93_final_read_errors = []
        self._v107_final_capture_errors = []
        self._v93_sync_map_status_label()

        vacuum = self.vacuum
        settings = dict(self.settings or {})

        def worker():
            grids = []
            errors = []
            client = None
            try:
                client = self._v40_map_client(vacuum, settings)
                client.set_v107_final_mode(True)
            except Exception as exc:
                errors.append(
                    str(exc).strip()
                    or "No se pudo abrir el cliente V107 de mapa."
                )

            if client is not None:
                for index in range(int(self.FINAL_DOCK_READS)):
                    if vacuum is not getattr(self, "vacuum", None):
                        errors.append(
                            "robot cambiado/desconectado durante captura final"
                        )
                        break
                    try:
                        upload = client.request_live_upload()
                        if isinstance(upload, dict) and upload.get("ok"):
                            time.sleep(float(self.FINAL_DOCK_SETTLE_SECONDS))

                        snapshot = client.load_live_partial()
                        grid = self._v107_grid_from_snapshot(snapshot)
                        if grid is None:
                            raise RuntimeError(
                                "la lectura final no produjo grid literal"
                            )
                        grids.append(grid)
                    except Exception as exc:
                        errors.append(
                            f"lectura {index + 1}: "
                            + (str(exc).strip() or type(exc).__name__)
                        )
                    time.sleep(0.60)

                try:
                    client.set_v107_final_mode(False)
                    client.mark_v93_finalized()
                except Exception:
                    pass

            self._post_ui(
                "v107_final_grid_done",
                serial,
                grids,
                errors,
            )

        threading.Thread(
            target=worker,
            name="AspiradoraFinalMapV107",
            daemon=True,
        ).start()
        return True

    # ========================================================= estado de mapa
    def _v93_sync_map_status_label(self):
        label = getattr(self, "map_status_label", None)
        if label is None:
            return

        mapping = bool(getattr(self, "mapping_active", False))
        if bool(getattr(self, "_v93_finalizing", False)):
            text = (
                "Finalizando mapa Xiaomi · esperando geometría estable "
                "de Mi Home…"
            )
            color = "#16a34a"
        elif mapping:
            text = (
                "Mapeando · la planta se generará al finalizar para "
                "priorizar fidelidad"
            )
            color = "#16a34a"
        elif self._v107_final_saved and isinstance(self._v107_final_grid, dict):
            cells = sum(
                1
                for value in self._v107_final_grid.get("cells", [])
                if int(value)
            )
            text = f"Mapa Xiaomi final guardado · {cells} celdas nativas"
            color = "#4f46e5"
        else:
            text = "Esperando mapa Xiaomi final"
            color = "#64748b"

        self._v93_last_status_text = text
        try:
            label.configure(text=text, fg=color)
        except Exception:
            pass

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v107_final_grid_done":
            serial = int(payload[0]) if payload else -1
            grids = list(payload[1]) if len(payload) > 1 else []
            errors = list(payload[2]) if len(payload) > 2 else []

            if serial != int(getattr(self, "_v74_mapping_serial", 0) or 0):
                return None

            chosen, reason = self._v107_choose_final_grid(grids)
            self._v93_finalizing = False
            self._v93_finalized_serial = serial
            self._v93_final_read_success = len(grids)
            self._v93_final_read_errors = errors[-3:]
            self._v107_final_capture_errors = errors[-5:]
            self._v107_final_choice_reason = reason

            if isinstance(chosen, dict) and getattr(self, "local_map", None):
                try:
                    self.local_map.set_native_grid(chosen)
                    self._v107_final_grid = dict(chosen)
                    self._v107_final_saved = True
                    self._v107_hide_surface_until_final = False

                    # Compatibilidad con retención V105/V100.
                    map_id = self._v105_map_id()
                    self._v105_frozen_previews[map_id] = (
                        self._v105_copy_grid(chosen)
                    )
                    self._v100_live_grids[map_id] = dict(chosen)
                except Exception as exc:
                    self._v107_final_saved = False
                    self._v107_final_capture_errors.append(
                        "persistencia: "
                        + (str(exc).strip() or type(exc).__name__)
                    )

            if self._v107_final_saved:
                try:
                    self._v70_refresh_map_overview(force=True)
                except Exception:
                    pass
                try:
                    # Un solo render completo del mapa final.
                    self._v96_last_render_at = 0.0
                    self._render_maps()
                    self._v107_final_render_count += 1
                except Exception:
                    pass
                try:
                    self._set_banner(
                        "Mapa Xiaomi final capturado · "
                        f"{len(grids)}/{self.FINAL_DOCK_READS} lecturas · "
                        + reason
                    )
                except Exception:
                    pass
            else:
                try:
                    self._set_banner(
                        "No se pudo capturar una geometría Xiaomi final fiable."
                    )
                except Exception:
                    pass

            self._v93_sync_map_status_label()
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        final_diag = dict(
            getattr(client, "last_v107_diagnostics", {}) or {}
        ) if client is not None else {}
        final_cells = (
            sum(
                1
                for value in self._v107_final_grid.get("cells", [])
                if int(value)
            )
            if isinstance(self._v107_final_grid, dict)
            else 0
        )

        lines = [
            "DIAGNÓSTICO V107 ACTIVO · mapa final primero + anti-freeze",
            "================================================================",
            (
                f"estrategia visual: surface live bloqueada="
                f"{self._v107_hide_surface_until_final} · "
                f"surface calls evitadas={self._v107_surface_suppressed}"
            ),
            (
                f"final Xiaomi: guardado={self._v107_final_saved} · "
                f"candidatos={self._v107_final_candidates} · "
                f"únicos={self._v107_final_unique} · "
                f"celdas={final_cells} · "
                f"motivo={self._v107_final_choice_reason}"
            ),
            (
                f"frame literal: fuente={final_diag.get('source','—')} · "
                f"seleccionado={final_diag.get('selected_key','—')} · "
                f"antes={final_diag.get('before','—')} · "
                f"final={final_diag.get('after_mirror','—')} · "
                f"mirrorY={final_diag.get('mirror_y','—')}"
            ),
            (
                f"captura dock: OK={self._v93_final_read_success}/"
                f"{self.FINAL_DOCK_READS} · "
                f"errores={self._v107_final_capture_errors or []}"
            ),
            (
                f"rendimiento: cloud live bloqueado="
                f"{self._v107_cloud_polls_blocked} · "
                f"refresh UI omitidos={self._v107_theme_refresh_skipped} · "
                f"configure canvas omitidos={self._v107_canvas_config_skipped}"
            ),
            (
                f"presupuesto UI: render mínimo="
                f"{self.RENDER_MIN_INTERVAL_SECONDS:.2f}s · "
                f"eventos/lote={self.UI_EVENT_BUDGET} · "
                f"miniaturas cada≥{self.MAP_OVERVIEW_REFRESH_SECONDS:.1f}s"
            ),
            (
                "regla V107: durante la limpieza se priorizan pose y control; "
                "la planta no se reconstruye en tiempo real"
            ),
            (
                "regla V107: al llegar al dock se consulta Xiaomi tres veces y "
                "se prefiere un frame final repetido; si todos cambian, gana el "
                "más reciente"
            ),
            (
                "regla V107: el mapa final usa el frame Xiaomi actual del layout "
                "elegido, nunca la unión histórica acum[N]"
            ),
            (
                "regla V107: el eje Y final se refleja alrededor del dock para "
                "igualar la orientación visual observada en Mi Home"
            ),
            (
                "regla V107: tema/i18n y tarjetas no se reconstruyen después "
                "de cada movimiento del robot"
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

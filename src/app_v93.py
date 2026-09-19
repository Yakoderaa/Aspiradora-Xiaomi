import threading
import time

import app_v92
from xiaomi_e10_map_v93 import XiaomiE10MapV93


class App(app_v92.App):
    """V93: layout físico, limpieza de grid y cierre coherente con el mapa Xiaomi."""

    FINAL_DOCK_READS = 3
    FINAL_DOCK_SETTLE_SECONDS = 0.85

    def __init__(self):
        self._v93_diag = {}
        self._v93_finalizing = False
        self._v93_finalized_serial = None
        self._v93_final_read_success = 0
        self._v93_final_read_errors = []
        self._v93_grid_completion_overrides = 0
        self._v93_last_status_text = "—"
        super().__init__()
        self._v93_sync_map_status_label()

    # ======================================================== cliente mapa
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV93(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    def start_new_mapping(self):
        self._v93_finalizing = False
        self._v93_finalized_serial = None
        self._v93_final_read_success = 0
        self._v93_final_read_errors = []
        result = super().start_new_mapping()
        self._v93_sync_map_status_label()
        return result

    # ========================================== grid válido reemplaza heurística
    def _v93_native_grid_state(self):
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        grid = (snapshot or {}).get("native_grid")
        if not isinstance(grid, dict):
            return False, None, {}
        try:
            cells = list(grid.get("cells") or [])
            side = int(grid.get("side", 0) or 0)
        except Exception:
            return False, grid, {}
        if side <= 0 or len(cells) != side * side:
            return False, grid, {}

        metrics = dict(grid.get("metrics") or {})
        client = getattr(self, "_v40_client", None)
        validator = getattr(client, "_grid_metrics", None)
        if callable(validator):
            try:
                metrics = dict(validator(cells) or metrics)
            except Exception:
                pass
        return bool(metrics.get("valid")), grid, metrics

    def _v81_completion_state(self):
        state = dict(super()._v81_completion_state() or {})
        valid, grid, metrics = self._v93_native_grid_state()
        if valid:
            if not bool(state.get("ready")):
                self._v93_grid_completion_overrides += 1
            state["ready"] = True
            state["missing"] = []
            state["native_grid"] = True
            state["native_grid_cells"] = int(metrics.get("nonzero", 0) or 0)
            self._v81_completion_ready = True
            self._v81_completion_missing = []
            self._v81_incomplete_reason = None
        return state

    # =============================================== cierre físico status = 4
    def _v84_close_mapping_on_dock(self):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        if not self._v84_has_mapping_motion():
            return False

        valid, _grid, metrics = self._v93_native_grid_state()
        if not valid:
            return super()._v84_close_mapping_on_dock()

        self._v74_watch_active = False
        self._v74_finish_requested = True
        self._v73_session_phase = 0
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = True

        nonzero = int(metrics.get("nonzero", 0) or 0)
        reason = (
            "Mapeo terminado · grid Xiaomi validado y carga confirmada "
            f"físicamente en la base ({nonzero} celdas nativas)."
        )
        self._v82_status4_session_closes += 1
        self._v81_incomplete_reason = None
        self._v74_finish_reason = reason
        self._v84_last_close_reason = reason
        self._v84_cancel_recovery("cierre físico V93 con grid Xiaomi")

        try:
            self._sync_mapping_step_buttons()
        except Exception:
            pass
        try:
            threading.Thread(
                target=self._restore_cleaning_preferences,
                daemon=True,
            ).start()
        except Exception:
            pass
        try:
            self._set_banner(reason)
        except Exception:
            pass
        try:
            self.after(100, self._v70_notify_mapping_complete)
        except Exception:
            pass

        self._v93_schedule_final_reads()
        self._v93_sync_map_status_label()
        return True

    # ============================================= lecturas finales en el dock
    def _v93_schedule_final_reads(self):
        serial = int(getattr(self, "_v74_mapping_serial", 0) or 0)
        if self._v93_finalizing or self._v93_finalized_serial == serial:
            return False
        if not getattr(self, "vacuum", None):
            return False

        self._v93_finalizing = True
        self._v93_final_read_success = 0
        self._v93_final_read_errors = []
        self._v93_sync_map_status_label()

        vacuum = self.vacuum
        settings = dict(self.settings or {})

        def worker():
            successes = 0
            errors = []
            try:
                client = self._v40_map_client(vacuum, settings)
            except Exception as exc:
                self._post_ui(
                    "v93_final_grid_done",
                    serial,
                    0,
                    [str(exc).strip() or "No se pudo abrir el cliente de mapa."],
                )
                return

            for index in range(self.FINAL_DOCK_READS):
                if vacuum is not getattr(self, "vacuum", None):
                    errors.append("robot cambiado/desconectado durante lectura final")
                    break
                upload_info = None
                try:
                    upload_info = client.request_fresh_upload()
                    if isinstance(upload_info, dict) and upload_info.get("ok"):
                        time.sleep(self.FINAL_DOCK_SETTLE_SECONDS)
                    snapshot = client.load()
                    successes += 1
                    self._post_ui(
                        "cloud_ijai_map_state_v40",
                        snapshot,
                        upload_info,
                    )
                except Exception as exc:
                    errors.append(
                        f"lectura {index + 1}: "
                        + (str(exc).strip() or type(exc).__name__)
                    )
                time.sleep(0.45)

            try:
                client.mark_v93_finalized()
            except Exception:
                pass
            self._post_ui(
                "v93_final_grid_done",
                serial,
                successes,
                errors,
            )

        threading.Thread(target=worker, daemon=True).start()
        return True

    # =========================================================== UI / eventos
    def _v93_sync_map_status_label(self):
        label = getattr(self, "map_status_label", None)
        if label is None:
            return
        valid, grid, metrics = self._v93_native_grid_state()
        mapping = bool(getattr(self, "mapping_active", False))

        if self._v93_finalizing:
            text = "Finalizando mapa Xiaomi en la base…"
            color = "#16a34a"
        elif mapping and valid:
            text = (
                "Mapeando en tiempo real · grid Xiaomi "
                f"{int(metrics.get('nonzero', 0) or 0)} celdas"
            )
            color = "#16a34a"
        elif mapping:
            text = "Mapeando en tiempo real · buscando geometría Xiaomi…"
            color = "#16a34a"
        elif valid:
            resolution = float((grid or {}).get("resolution", 0.0) or 0.0)
            text = (
                "Mapa Xiaomi guardado · "
                f"{int(metrics.get('nonzero', 0) or 0)} celdas"
                + (f" · {resolution:.2f} m" if resolution > 0 else "")
            )
            color = "#4f46e5"
        else:
            text = "Mapa local guardado"
            color = "#64748b"

        self._v93_last_status_text = text
        try:
            label.configure(text=text, fg=color)
        except Exception:
            pass

    def _render_maps(self):
        result = super()._render_maps()
        self._v93_sync_map_status_label()
        return result

    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))
        result = super()._render_status(status)

        # Si el cierre heredado ocurrió por otra ruta, igual hacemos la captura
        # final una sola vez al confirmar físicamente status=4.
        if (
            physical == 4
            and bool(getattr(self, "_v90_start_confirmed", False))
            and bool(getattr(self, "_v90_departure_confirmed", False))
        ):
            self._v93_schedule_final_reads()
        self._v93_sync_map_status_label()
        return result

    def _handle_ui_event(self, kind, payload):
        if kind == "v93_final_grid_done":
            serial = int(payload[0]) if payload else -1
            successes = int(payload[1]) if len(payload) > 1 else 0
            errors = list(payload[2]) if len(payload) > 2 else []
            if serial != int(getattr(self, "_v74_mapping_serial", 0) or 0):
                return
            self._v93_finalizing = False
            self._v93_finalized_serial = serial
            self._v93_final_read_success = successes
            self._v93_final_read_errors = errors[-3:]
            try:
                self._render_maps()
            except Exception:
                self._v93_sync_map_status_label()
            if successes:
                try:
                    self._set_banner(
                        "Mapa Xiaomi finalizado en la base · "
                        f"{successes}/{self.FINAL_DOCK_READS} lecturas finales."
                    )
                except Exception:
                    pass
            return

        result = super()._handle_ui_event(kind, payload)
        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            if client is not None:
                self._v93_diag = dict(
                    getattr(client, "last_v93_diagnostics", {}) or {}
                )
        self._v93_sync_map_status_label()
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        diag = dict(
            getattr(client, "last_v93_diagnostics", {}) or self._v93_diag or {}
        )
        selected = dict(diag.get("selected") or {})
        clean = dict(diag.get("clean") or {})
        temporal = dict(diag.get("temporal") or {})
        top = list(diag.get("top") or [])

        def desc(item):
            if not item:
                return "—"
            return (
                f"{item.get('label', '—')} · válido={bool(item.get('valid'))} · "
                f"nonzero={item.get('nonzero', '—')} · "
                f"robotΔ={item.get('robot_distance', '—')} · "
                f"robotμ={item.get('robot_avg', '—')} · "
                f"deltaμ={item.get('delta_avg', '—')} · "
                f"dens={item.get('density', '—')} · "
                f"perim={item.get('perimeter', '—')}"
            )

        top_lines = [
            f"    #{index} {desc(item)}"
            for index, item in enumerate(top[:5], 1)
        ] or ["    —"]

        lines = [
            "DIAGNÓSTICO V93 ACTIVO · layout físico + cierre final en dock",
            "================================================================",
            (
                "posición física: "
                f"base={diag.get('base_cell', '—')} · "
                f"robot10/24={diag.get('robot_cell', '—')} · "
                f"fallback base={bool(diag.get('base_fallback'))}"
            ),
            f"seleccionado V93: {desc(selected)}",
            (
                "coherencia temporal: "
                f"muestras={temporal.get('samples', 0)} · "
                f"hits robot={temporal.get('robot_hits', 0)}/{temporal.get('robot_n', 0)} · "
                f"hits delta={temporal.get('delta_hits', 0)}/{temporal.get('delta_n', 0)}"
            ),
            (
                "limpieza geométrica: "
                f"{clean.get('before', '—')}→{clean.get('after', '—')} celdas · "
                f"componentes descartados={clean.get('detached_removed', 0)} · "
                f"apéndices={clean.get('spurs_removed', 0)} · "
                f"huecos rellenos={clean.get('holes_filled', 0)} · "
                f"revertida={bool(clean.get('reverted'))}"
            ),
            (
                "final dock: "
                f"en curso={self._v93_finalizing} · "
                f"serial final={self._v93_finalized_serial} · "
                f"lecturas OK={self._v93_final_read_success}/{self.FINAL_DOCK_READS} · "
                f"errores={self._v93_final_read_errors or []}"
            ),
            (
                "estado UI mapa: "
                f"{self._v93_last_status_text} · "
                f"overrides completitud por grid={self._v93_grid_completion_overrides}"
            ),
            "top candidatos V93:",
            *top_lines,
            "regla V93: un layout no gana sólo por ser conexo; debe ser coherente con 10/24 y con dónde aparecen celdas nuevas",
            "regla V93: el filtro de apéndices sólo se aplica si conserva al menos 68% de la geometría y nunca puede volver inválido un grid V57",
            "regla V93: un grid Xiaomi válido cuenta como evidencia de mapeo completo aunque la heurística de trayectoria V81 quede corta",
            "regla V93: al confirmar status=4 se hacen tres lecturas finales y luego la UI deja de mostrar 'Mapeando'",
            "",
            "",
        ]
        return "\n".join(lines) + inherited

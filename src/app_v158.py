"""Diagnóstico completo y mapa Xiaomi al terminar, sin cambiar la navegación."""
import threading
import time

import app_v151
import app_v156
import app_v157
from app_v107 import App as FinalGridHelpers
from xiaomi_e10_map_v130 import XiaomiE10MapV130


class App(app_v157.App):
    FINAL_MAP_DELAYS_MS = (5000, 15000, 30000, 60000, 120000)

    def __init__(self):
        self._v158_epoch = 0
        self._v158_capture = None
        self._v158_worker = False
        self._v158_status = None
        self._v158_state = {}
        self._v158_map_diag = {"state": "sin captura", "attempts": 0}
        super().__init__()

    def _v158_busy(self):
        return bool(self.mapping_active or self._v157_whole_active or self._v157_target_active)

    def _v158_valid(self, capture):
        return bool(
            capture is self._v158_capture
            and capture[0] == self._v158_epoch
            and capture[1] is self.vacuum
            and capture[2] is self.local_map
            and capture[3] == self.local_map.active_map_id
            and not self._v158_busy()
            and self._v158_status == 4
            and not getattr(self, "_closing", False)
        )

    def _v158_begin_capture(self, reason):
        if not self.vacuum or not self.local_map or self._v158_busy():
            return False
        if self._v158_status != 4:
            return False
        if self._v158_capture is not None and self._v158_valid(self._v158_capture):
            return False
        self._v158_epoch += 1
        capture = (self._v158_epoch, self.vacuum, self.local_map, self.local_map.active_map_id)
        self._v158_capture = capture
        self._v158_map_diag = {
            "state": "esperando mapa Xiaomi", "reason": reason,
            "map_id": capture[3], "attempts": 0, "successes": 0,
            "errors": [], "saved": False,
            "freshness": "slot actual; Xiaomi no confirma aquí la sesión física",
        }
        self.after(self.FINAL_MAP_DELAYS_MS[0], lambda: self._v158_read_final(capture, 0))
        return True

    def _v158_read_final(self, capture, attempt):
        if not self._v158_valid(capture):
            return
        if self._v158_worker:
            self.after(1000, lambda: self._v158_read_final(capture, attempt))
            return
        if not self._cloud_session_ready():
            self._v158_map_diag["state"] = "requiere conexión a Xiaomi Cloud"
            self._set_banner("Mapa final pendiente: conectá tu cuenta Xiaomi en Ajustes.")
            self._v158_next_capture(capture, attempt)
            return
        self._v158_worker = True
        self._v158_map_diag["attempts"] += 1
        self._v158_map_diag["state"] = "descargando mapa Xiaomi"
        settings = dict(self.settings or {})
        reference_path = list(self.local_map.snapshot().get("points") or [])

        def worker():
            grid, error, decoder = None, None, {}
            try:
                # Cliente independiente: sólo GET Cloud + lecturas de pose LAN.
                # No request_live_upload(), acciones MIoT ni controles antiguos.
                client = XiaomiE10MapV130(capture[1], settings)
                client.set_v109_reference_path(reference_path)
                client.set_v107_final_mode(True)
                snapshot = client.load_live_partial()
                grid = FinalGridHelpers._v107_grid_from_snapshot(snapshot)
                if grid is None:
                    raise ValueError("Xiaomi todavía no entregó una geometría válida")
                grid["source"] = "xiaomi-v158-final-current"
                decoder = {name: dict(getattr(client, name, {}) or {}) for name in (
                    "last_v100_diagnostics", "last_v107_diagnostics",
                    "last_v112_diagnostics", "last_v128_diagnostics") }
            except Exception as exc:
                error = str(exc).strip() or type(exc).__name__
            self._post_ui("v158_final_map", capture, attempt, grid, error, decoder)

        threading.Thread(target=worker, name="XiaomiFinalMapV158", daemon=True).start()

    def _v158_next_capture(self, capture, attempt):
        if attempt + 1 < len(self.FINAL_MAP_DELAYS_MS):
            self.after(self.FINAL_MAP_DELAYS_MS[attempt + 1],
                       lambda: self._v158_read_final(capture, attempt + 1))
        else:
            self._v158_map_diag["state"] = (
                "mapa Xiaomi guardado" if self._v158_map_diag["saved"]
                else "mapa final pendiente; reintentos agotados"
            )
            if not self._v158_map_diag["saved"]:
                self._set_banner("Xiaomi aún no entregó el mapa final. Se conserva el mapa anterior; detalle en Diagnóstico.")

    def _apply_map_state(self, state):
        previous = self._v158_status
        if isinstance(state, dict):
            self._v158_state = dict(state)
            try:
                self._v158_status = int(state["status"])
            except (KeyError, TypeError, ValueError):
                pass
        if self._v158_status != 4 and self._v158_capture is not None:
            self._v158_epoch += 1
            self._v158_capture = None
            self._v158_map_diag["state"] = "captura cancelada: robot fuera de base"
        result = super()._apply_map_state(state)
        if self._v158_status == 4 and previous != 4:
            self._v158_begin_capture("robot en base (inicio o fin de limpieza)")
        return result

    def _render_status(self, status):
        # local_map_state() sólo trae pose/trayectoria. El status físico llega
        # por status_ok, en un canal separado; no inferir dock desde la pose.
        previous = self._v158_status
        try:
            self._v158_status = int(status.status)
        except (AttributeError, TypeError, ValueError):
            self._v158_status = None
        if self._v158_status != 4 and self._v158_capture is not None:
            self._v158_epoch += 1
            self._v158_capture = None
            self._v158_map_diag["state"] = "captura cancelada: robot fuera de base"
        result = super()._render_status(status)
        if self._v158_status == 4 and previous != 4:
            self._v158_begin_capture("status físico: robot en base")
        return result

    def _handle_ui_event(self, kind, payload):
        if kind == "v158_final_map":
            capture, attempt, grid, error, decoder = payload
            self._v158_worker = False
            if not self._v158_valid(capture):
                return None
            diag = self._v158_map_diag
            if grid is not None:
                try:
                    self.local_map.set_native_grid(grid)
                    self._v107_final_grid = dict(grid)
                    self._v107_final_saved = True
                    self._v107_hide_surface_until_final = False
                    map_id = self._v105_map_id()
                    self._v105_frozen_previews[map_id] = self._v105_copy_grid(grid)
                    self._v100_live_grids[map_id] = dict(grid)
                    diag.update(saved=True, successes=diag["successes"] + 1,
                                cells=sum(grid["cells"]), side=grid["side"],
                                resolution=grid["resolution"], blob_sha12=grid["blob_sha12"],
                                decoder=decoder, saved_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                    self._v96_last_render_at = 0.0
                    self._render_maps()
                    self._v70_refresh_map_overview(force=True)
                    self._v93_sync_map_status_label()
                    self._set_banner("Mapa Xiaomi descargado y guardado · comprobando actualización final.")
                except Exception as exc:
                    error = "Guardar/mostrar mapa: " + str(exc)
            if error:
                diag["errors"].append(error)
            self._v158_next_capture(capture, attempt)
            return None

        result = super()._handle_ui_event(kind, payload)
        if kind in ("v157_whole_finished", "v155_mapping_finished", "v157_target_finished"):
            # La telemetría puede haber llegado antes del evento de fin. El
            # segundo disparador cierra esa carrera sin duplicar workers.
            self._v158_begin_capture(kind)
        return result

    def _diagnostic_text(self):
        sections = ["V158-IA · DIAGNÓSTICO COMPLETO\n" + "=" * 60,
                    "Navegación V157: lectura previa + un START 2/1.\n"
                    "Mapa final: sólo lectura, después de status=4; sin órdenes al robot."]
        # Cada sección falla de manera independiente; generar el informe no
        # consulta la red ni reactiva controladores.
        def section(title, getter):
            try:
                value = getter()
            except Exception as exc:
                value = "Sección no disponible: " + str(exc)
            sections.append(title + "\n" + str(value))

        section("VIVIENDA / IA / PROGRAMADOR", lambda: app_v157.App._diagnostic_text(self).replace(" · LITE", " · RESUMEN"))
        section("MAPEO / COORDENADAS / RENDIMIENTO", lambda: app_v156.App._diagnostic_text(self))
        section("ÚLTIMA TELEMETRÍA LAN", lambda: repr(self._v158_state))
        section("CAPTURA FINAL XIAOMI", lambda: repr(self._v158_map_diag))
        section("TRANSPORTE Y AUDITORÍA COMPLETOS", lambda: repr(
            self._fresh_core.diagnostic() if self._fresh_core else {}))
        section("MAPA LOCAL", lambda: repr({k: v for k, v in self.local_map.snapshot().items()
                                            if k not in ("points", "native_grid")}))
        section("GEOMETRÍA GUARDADA", lambda: repr({k: v for k, v in
            (self.local_map.snapshot().get("native_grid") or {}).items() if k != "cells"}))
        section("COMPATIBILIDAD HISTÓRICA — reglas antiguas no describen el control actual",
                lambda: app_v151.App._diagnostic_text(self).replace("ACTIVO", "HISTÓRICO"))
        # Usa el filtro de privacidad ya empleado por el informe histórico.
        text = "\n\n".join(sections) + "\n"
        return self._v109_redact_ips(text)[0]

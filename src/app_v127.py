import math
import threading
import time

import app_v126
import app_v9
from xiaomi_e10_map_v127 import XiaomiE10MapV127


class App(app_v126.App):
    """V127: regreso asistido explícito + preview final inmediato + escape Fase 2."""

    ASSISTED_RETURN_WINDOW_SECONDS = 18.0
    ASSISTED_RETURN_MIN_SAMPLES = 10
    ASSISTED_RETURN_MIN_PATH_M = 1.00
    ASSISTED_RETURN_MAX_NET_M = 0.75
    ASSISTED_RETURN_MIN_TURN_RAD = 7.0
    ASSISTED_RETURN_MAX_PROGRESS_M = 0.18
    ASSISTED_RETURN_MAX_SPAN_M = 1.60

    PHASE2_RECOVERY_NO_NEW_SECONDS = 100.0
    PHASE2_RECOVERY_COOLDOWN_SECONDS = 140.0
    PHASE2_RECOVERY_MAX = 2
    PHASE2_REVERSE_SECONDS = 0.55
    PHASE2_TURN_SECONDS = 0.55

    def __init__(self):
        self._v127_assisted_return_requested = False
        self._v127_assisted_return_started_at = 0.0
        self._v127_external_return_seen = 0

        self._v127_phase2_recoveries = 0
        self._v127_phase2_recovery_last_at = 0.0
        self._v127_phase2_recovery_active = False
        self._v127_phase2_recovery_last_reason = "—"
        self._v127_phase2_recovery_last_result = {}

        self._v127_preview_published = False
        self._v127_preview_read = 0
        self._v127_preview_cells = 0
        self._v127_preview_errors = []
        super().__init__()

    # ======================================================== cliente V127
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV127)
        ):
            self._v40_client = XiaomiE10MapV127(vacuum, settings)
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

    # ============================================= regreso asistido explícito
    def dock(self):
        self._v127_assisted_return_requested = True
        self._v127_assisted_return_started_at = time.monotonic()
        try:
            self._v126_return_samples.clear()
        except Exception:
            pass
        try:
            self._set_banner(
                "Volviendo a la base · regreso asistido activo."
            )
        except Exception:
            pass
        return super().dock()

    def _render_status(self, status):
        physical = self._v67_int(getattr(status, "status", None))
        if (
            physical == 3
            and not self._v127_assisted_return_requested
            and not bool(getattr(self, "_v84_returning", False))
        ):
            self._v127_external_return_seen += 1

        result = super()._render_status(status)

        if physical == 4:
            self._v127_assisted_return_requested = False
            self._v127_assisted_return_started_at = 0.0
        return result

    def _v126_return_pattern(self):
        if not self._v127_assisted_return_requested:
            return super()._v126_return_pattern()

        rows = list(self._v126_return_samples)
        if len(rows) < int(self.ASSISTED_RETURN_MIN_SAMPLES):
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
            "mode": "V127-assisted",
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
            elapsed >= float(self.ASSISTED_RETURN_WINDOW_SECONDS) * 0.72
            and path >= float(self.ASSISTED_RETURN_MIN_PATH_M)
            and net <= float(self.ASSISTED_RETURN_MAX_NET_M)
            and turns >= float(self.ASSISTED_RETURN_MIN_TURN_RAD)
            and progress <= float(self.ASSISTED_RETURN_MAX_PROGRESS_M)
            and span <= float(self.ASSISTED_RETURN_MAX_SPAN_M)
            and float(last[5]) >= float(self.RETURN_MIN_BASE_DISTANCE_M)
        )
        return diagnostic if circular else None

    # =========================================== Fase 2: escape sin nuevo mapa
    def _v127_phase2_recovery_allowed(self, reason):
        if self._v127_phase2_recovery_active:
            return False, "recovery ya activo"
        if self._v127_phase2_recoveries >= int(self.PHASE2_RECOVERY_MAX):
            return False, "máximo de recoveries alcanzado"
        if not bool(getattr(self, "mapping_active", False)):
            return False, "mapeo inactivo"
        if int(getattr(self, "mapping_phase", 0) or 0) != 2:
            return False, "no es Fase 2"
        if bool(getattr(self, "_v84_returning", False)):
            return False, "retorno activo"
        if bool(getattr(self, "_v84_dock_latched", False)):
            return False, "dock confirmado"

        try:
            status = int(getattr(self, "_v94_last_status_code", -1))
        except Exception:
            status = -1
        if status not in (5, 6, 7):
            return False, f"status={status}"

        now = time.monotonic()
        last_discovery = float(
            getattr(self, "_v74_last_discovery_at", now) or now
        )
        no_new = max(0.0, now - last_discovery)
        if no_new < float(self.PHASE2_RECOVERY_NO_NEW_SECONDS):
            return False, f"sin zona nueva sólo {no_new:.1f}s"

        if (
            self._v127_phase2_recovery_last_at > 0.0
            and now - self._v127_phase2_recovery_last_at
            < float(self.PHASE2_RECOVERY_COOLDOWN_SECONDS)
        ):
            return False, "cooldown"

        pose = getattr(self, "_v117_live_pose", None)
        if isinstance(pose, dict):
            try:
                distance = math.hypot(float(pose["x"]), float(pose["y"]))
                if distance < 0.80:
                    return False, f"demasiado cerca del dock ({distance:.2f}m)"
            except Exception:
                pass

        return True, f"{reason} · no-new={no_new:.1f}s"

    def _v127_try_phase2_recovery(self, reason):
        allowed, detail = self._v127_phase2_recovery_allowed(reason)
        if not allowed:
            return False

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False

        self._v127_phase2_recoveries += 1
        attempt = int(self._v127_phase2_recoveries)
        self._v127_phase2_recovery_active = True
        self._v127_phase2_recovery_last_at = time.monotonic()
        self._v127_phase2_recovery_last_reason = str(detail)
        self._v74_last_discovery_at = time.monotonic()

        try:
            self._v77_corridor_samples.clear()
        except Exception:
            pass

        def worker():
            result = {
                "attempt": attempt,
                "reason": str(detail),
                "success": False,
                "resume": None,
                "error": None,
            }
            try:
                # Pausa muy breve, escape físico y reanudación del mismo
                # whole-home. No se ejecuta build-map ni arm_new_map.
                vacuum.stop()
                time.sleep(0.35)

                vacuum.manual(4)
                time.sleep(float(self.PHASE2_REVERSE_SECONDS))
                vacuum.manual(5)
                time.sleep(0.18)

                turn = 2 if attempt % 2 else 3
                vacuum.manual(turn)
                time.sleep(float(self.PHASE2_TURN_SECONDS))
                vacuum.manual(5)
                time.sleep(0.25)

                resume = vacuum.start_mapping_whole_home(
                    confirm_timeout=6.0
                )
                result["resume"] = dict(resume or {})
                result["success"] = bool((resume or {}).get("success"))
            except Exception as exc:
                result["error"] = (
                    str(exc).strip() or type(exc).__name__
                )
                try:
                    vacuum.manual(5)
                except Exception:
                    pass
                try:
                    resume = vacuum.start_mapping_whole_home(
                        confirm_timeout=6.0
                    )
                    result["resume"] = dict(resume or {})
                    result["success"] = bool((resume or {}).get("success"))
                except Exception as resume_exc:
                    if not result["error"]:
                        result["error"] = (
                            str(resume_exc).strip()
                            or type(resume_exc).__name__
                        )
            finally:
                self._v127_phase2_recovery_last_result = dict(result)
                self._v127_phase2_recovery_active = False
                self._post_ui("v127_phase2_recovery_done", result)

        threading.Thread(
            target=worker,
            name="AspiradoraPhase2RecoveryV127",
            daemon=True,
        ).start()
        return True

    def _v73_schedule_recovery(self, phase, reason):
        text = str(reason or "").lower()
        corridor_like = (
            "corredor" in text
            or "pasadas ida/vuelta" in text
            or "sector repetido" in text
        )
        if corridor_like and self._v127_try_phase2_recovery(reason):
            return None
        return super()._v73_schedule_recovery(phase, reason)

    def _v74_request_finish_for_coverage(self, no_new_seconds):
        if (
            bool(getattr(self, "mapping_active", False))
            and float(no_new_seconds or 0.0)
            >= float(self.PHASE2_RECOVERY_NO_NEW_SECONDS)
            and self._v127_try_phase2_recovery(
                f"no-new-area {float(no_new_seconds):.1f}s"
            )
        ):
            return None
        return super()._v74_request_finish_for_coverage(no_new_seconds)

    # ===================================== primer grid visible, 3 lecturas siguen
    def _v127_publish_preview_grid(self, grid, read_number):
        if not isinstance(grid, dict) or not getattr(self, "local_map", None):
            return False

        client = getattr(self, "_v40_client", None)
        cells = [
            1 if int(value) else 0
            for value in list(grid.get("cells") or [])
        ]
        try:
            metrics = (
                dict(client._grid_metrics(cells) or {})
                if client is not None
                else dict(grid.get("metrics") or {})
            )
        except Exception:
            metrics = dict(grid.get("metrics") or {})

        if not bool(metrics.get("valid")):
            self._v127_preview_errors.append(
                f"lectura {read_number}: grid preview inválido"
            )
            return False

        preview = dict(grid)
        preview["metrics"] = dict(metrics)
        preview["source"] = "xiaomi-v127-preview"

        try:
            self.local_map.set_native_grid(preview)
            self._v107_final_grid = dict(preview)
            self._v107_final_saved = True
            self._v107_hide_surface_until_final = False

            map_id = self._v105_map_id()
            self._v105_frozen_previews[map_id] = (
                self._v105_copy_grid(preview)
            )
            self._v100_live_grids[map_id] = dict(preview)

            self._v127_preview_published = True
            self._v127_preview_read = int(read_number)
            self._v127_preview_cells = int(sum(cells))

            self._v70_refresh_map_overview(force=True)
            self._v96_last_render_at = 0.0
            self._render_maps()
            return True
        except Exception as exc:
            self._v127_preview_errors.append(
                "preview: " + (str(exc).strip() or type(exc).__name__)
            )
            return False

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
        self._v127_preview_published = False
        self._v127_preview_read = 0
        self._v127_preview_cells = 0
        self._v127_preview_errors = []
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
                    or "No se pudo abrir el cliente V127 de mapa."
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
                        self._post_ui(
                            "v127_final_grid_preview",
                            serial,
                            dict(grid),
                            index + 1,
                        )
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
            name="AspiradoraFinalMapV127",
            daemon=True,
        ).start()
        return True

    def _v93_sync_map_status_label(self):
        if (
            bool(getattr(self, "_v93_finalizing", False))
            and self._v127_preview_published
        ):
            label = getattr(self, "map_status_label", None)
            if label is not None:
                text = (
                    "Mapa Xiaomi visible · verificando lectura "
                    f"{self._v127_preview_read}/{self.FINAL_DOCK_READS}…"
                )
                self._v93_last_status_text = text
                try:
                    label.configure(text=text, fg="#4f46e5")
                except Exception:
                    pass
                return
        return super()._v93_sync_map_status_label()

    # ============================================================= eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v127_final_grid_preview":
            serial = int(payload[0]) if payload else -1
            grid = dict(payload[1]) if len(payload) > 1 else {}
            read_number = int(payload[2]) if len(payload) > 2 else 0
            if serial != int(getattr(self, "_v74_mapping_serial", 0) or 0):
                return None
            if self._v127_publish_preview_grid(grid, read_number):
                self._set_banner(
                    "Mapa Xiaomi visible · las lecturas finales siguen "
                    "verificándose en segundo plano."
                )
            self._v93_sync_map_status_label()
            return None

        if kind == "v127_phase2_recovery_done":
            result = dict(payload[0]) if payload else {}
            if bool(result.get("success")):
                self._set_banner(
                    "Fase 2: patrón repetitivo corregido · barrido "
                    "whole-home reanudado sin crear un mapa nuevo."
                )
            else:
                self._set_banner(
                    "Fase 2: se intentó salir del patrón repetitivo; "
                    "el E10 continúa con la sesión actual."
                )
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        surface = (
            dict(getattr(client, "last_v127_diagnostics", {}) or {})
            if client is not None else {}
        )
        lines = [
            "DIAGNÓSTICO V127 ACTIVO · retorno asistido + superficie continua",
            "==================================================================",
            (
                "regreso explícito: activo="
                f"{self._v127_assisted_return_requested} · externos vistos="
                f"{self._v127_external_return_seen} · ventana="
                f"{self.ASSISTED_RETURN_WINDOW_SECONDS:.0f}s"
            ),
            (
                "escape Fase 2: recoveries="
                f"{self._v127_phase2_recoveries}/{self.PHASE2_RECOVERY_MAX} · "
                f"activo={self._v127_phase2_recovery_active} · último="
                f"{self._v127_phase2_recovery_last_reason}"
            ),
            f"resultado escape={self._v127_phase2_recovery_last_result or '—'}",
            (
                "preview final: publicado="
                f"{self._v127_preview_published} · lectura="
                f"{self._v127_preview_read}/{self.FINAL_DOCK_READS} · "
                f"celdas={self._v127_preview_cells} · errores="
                f"{self._v127_preview_errors[-2:]}"
            ),
            f"superficie V127={surface or '—'}",
            "regla V127: Volver a la base desde la app arma el guard asistido desde el primer segundo",
            "regla V127: un retorno iniciado fuera de la app sigue recibiendo la vigilancia V126",
            "regla V127: el primer grid final válido se muestra sin esperar las tres lecturas",
            "regla V127: Fase 2 sólo hace escape tras no-new prolongado y reanuda whole-home sin build-map",
            "regla V127: la superficie sólo se solidifica si conserva validez y queda dentro del límite de crecimiento",
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

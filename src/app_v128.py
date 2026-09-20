import threading
import time

import app_v127
import app_v9
from xiaomi_e10_map_v128 import XiaomiE10MapV128


class App(app_v127.App):
    """V128: recovery de Fase 2 sin STOP/manual + pulido final conservador."""

    PHASE2_REASSERT_WAIT_SECONDS = 3.0
    PHASE2_REASSERT_RETRY_WAIT_SECONDS = 2.0

    def __init__(self):
        self._v128_phase2_reasserts = 0
        self._v128_phase2_retries = 0
        self._v128_phase2_idle_seen = 0
        self._v128_phase2_last_status = None
        super().__init__()

    # ======================================================== cliente V128
    def _v40_map_client(self, vacuum, settings):
        if (
            self._v40_client is None
            or self._v40_client_vacuum is not vacuum
            or not isinstance(self._v40_client, XiaomiE10MapV128)
        ):
            self._v40_client = XiaomiE10MapV128(vacuum, settings)
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

    # =================================== Fase 2: nunca parar ni tomar las ruedas
    @staticmethod
    def _v128_status_code(vacuum):
        try:
            return int(vacuum.status().status)
        except Exception:
            try:
                state = vacuum._get_many([("status", 2, 1)])
                return int(state.get("status"))
            except Exception:
                return -1

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
                "strategy": "7/3 reassert only · no STOP/manual/remote",
            }
            try:
                before = self._v128_status_code(vacuum)
                result["status_before"] = before
                self._v128_phase2_last_status = before

                # El recovery sólo se arma desde status activo. No se cambia a
                # remoto, no se frenan las ruedas y no se reconstruye el mapa.
                if before not in (5, 6, 7):
                    if before == 1:
                        self._v128_phase2_idle_seen += 1
                    raise RuntimeError(
                        f"reassert cancelado: status ya no activo ({before})"
                    )

                try:
                    vacuum.set_sweep_type(0)
                except Exception as exc:
                    result["sweep_type_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                response = vacuum._send_motor_start(
                    "v128_phase2_reassert",
                    7,
                    3,
                    ["", 0, 1],
                    allow_when_guarded=True,
                )
                self._v128_phase2_reasserts += 1
                result["response"] = repr(response)[:500]

                deadline = (
                    time.monotonic()
                    + float(self.PHASE2_REASSERT_WAIT_SECONDS)
                )
                status = before
                while time.monotonic() < deadline:
                    time.sleep(0.35)
                    status = self._v128_status_code(vacuum)
                    self._v128_phase2_last_status = status
                    if status in (5, 6, 7):
                        result["status_after"] = status
                        result["success"] = True
                        result["resume"] = {
                            "method": "7/3 reassert while active",
                            "status": status,
                        }
                        break

                if not result["success"]:
                    result["status_after"] = status

                # Único caso de retry: el propio firmware cayó a idle tras el
                # reassert. Se reenvía el MISMO 7/3 una sola vez. Nunca 2/1,
                # nunca 2/3 fuera del dock y nunca movimiento manual.
                if not result["success"] and status == 1:
                    self._v128_phase2_idle_seen += 1
                    retry = vacuum._send_motor_start(
                        "v128_phase2_idle_retry",
                        7,
                        3,
                        ["", 0, 1],
                        allow_when_guarded=True,
                    )
                    self._v128_phase2_retries += 1
                    result["retry_response"] = repr(retry)[:500]

                    deadline = (
                        time.monotonic()
                        + float(self.PHASE2_REASSERT_RETRY_WAIT_SECONDS)
                    )
                    while time.monotonic() < deadline:
                        time.sleep(0.35)
                        status = self._v128_status_code(vacuum)
                        self._v128_phase2_last_status = status
                        if status in (5, 6, 7):
                            result["status_after"] = status
                            result["success"] = True
                            result["resume"] = {
                                "method": "7/3 idle retry",
                                "status": status,
                            }
                            break

                if not result["success"] and not result.get("error"):
                    result["error"] = (
                        "el firmware no mantuvo/reanudó status 5/6/7 "
                        f"(status={result.get('status_after')})"
                    )
            except Exception as exc:
                result["error"] = (
                    str(exc).strip() or type(exc).__name__
                )
            finally:
                self._v127_phase2_recovery_last_result = dict(result)
                self._v127_phase2_recovery_active = False
                self._post_ui("v128_phase2_recovery_done", result)

        threading.Thread(
            target=worker,
            name="AspiradoraPhase2RecoveryV128",
            daemon=True,
        ).start()
        return True

    # ============================================================= eventos UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v128_phase2_recovery_done":
            result = dict(payload[0]) if payload else {}
            if bool(result.get("success")):
                self._set_banner(
                    "Fase 2: patrón repetitivo detectado · objetivo "
                    "whole-home reafirmado sin detener la aspiradora."
                )
            else:
                self._set_banner(
                    "Fase 2: el recovery seguro no confirmó reanudación; "
                    "no se enviaron STOP ni movimientos manuales."
                )
            return None
        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        client = getattr(self, "_v40_client", None)
        polish = (
            dict(getattr(client, "last_v128_diagnostics", {}) or {})
            if client is not None else {}
        )
        lines = [
            "DIAGNÓSTICO V128 ACTIVO · recovery seguro + contorno afinado",
            "=============================================================",
            (
                "Fase 2 segura: reasserts="
                f"{self._v128_phase2_reasserts} · retries="
                f"{self._v128_phase2_retries} · idle vistos="
                f"{self._v128_phase2_idle_seen} · último status="
                f"{self._v128_phase2_last_status}"
            ),
            (
                "último recovery="
                f"{self._v127_phase2_recovery_last_result or '—'}"
            ),
            f"pulido mapa={polish or '—'}",
            "regla V128: recovery Fase 2 jamás llama stop(), manual() ni modo remoto",
            "regla V128: durante status activo sólo reafirma whole-home 7/3 y verifica 5/6/7",
            "regla V128: si el firmware cae a status=1, sólo permite un retry 7/3; jamás usa 2/3 fuera del dock",
            "regla V128: conserva todas las celdas V127 y sólo rellena concavidades pequeñas bajo límite de crecimiento",
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

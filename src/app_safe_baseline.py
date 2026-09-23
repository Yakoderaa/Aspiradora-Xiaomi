import threading
from tkinter import messagebox

import app_cleanroom
import app_v151
import app_v9
from safe_baseline_core import SafeBaselineCore


class App(app_cleanroom.App):
    """V153 Safe Baseline: conexión read-only + único START normal 2/3."""

    def _install_fresh_core(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            self._fresh_core = None
            return None
        current = getattr(self, "_fresh_core", None)
        if current is not None and current.vacuum is vacuum:
            return current
        self._fresh_core = SafeBaselineCore(vacuum, source="gui")
        self._v141_log(
            "V153 Safe Baseline instalado · legado bloqueado antes de escribir"
        )
        return self._fresh_core

    def _on_connected(self, ip):
        # Instalar el proxy ANTES de propagar callbacks heredados. Así conectar
        # nunca abre una ventana temporal donde una capa vieja pueda escribir.
        try:
            self._install_fresh_core()
        except Exception as exc:
            self._set_banner(
                "V153 no pudo instalar el bloqueo read-only: "
                + (str(exc).strip() or type(exc).__name__)
            )
            return None

        result = super()._on_connected(ip)
        self._set_banner(
            "V153 Safe Baseline · conectado en sólo lectura. "
            "Nada se modifica hasta una acción explícita."
        )
        return result

    def _baseline_disabled(self, feature):
        messagebox.showinfo(
            "V153 Safe Baseline",
            f"{feature} está temporalmente bloqueado.\n\n"
            "Primero vamos a validar un aspirado normal con un único START 2/3 "
            "sobre el estado limpio que dejó el factory reset.",
            parent=self,
        )
        return None

    # =================================================== única prueba permitida
    def start_clean(self):
        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            return self._baseline_disabled("La limpieza")

        mode_label = str(self.mode_var.get() or "")
        if mode_label and mode_label != "Aspirar":
            return self._baseline_disabled(
                "Aspirar + trapear / Trapear"
            )

        self._set_banner(
            "V153 · prueba limpia: lectura previa + UN START 2/3. "
            "Sin ninguna escritura de preparación."
        )

        def started(diag):
            self._post_ui("baseline_clean_started", dict(diag or {}))

        def finished(diag):
            self._post_ui("baseline_clean_finished", dict(diag or {}))

        try:
            self._fresh().start_normal_async(
                on_started=started,
                on_finished=finished,
            )
        except Exception as exc:
            messagebox.showerror(
                "V153 Safe Baseline",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    # STOP y Volver a base siguen siendo acciones explícitas del usuario.
    def stop_clean(self):
        try:
            core = self._fresh()
            threading.Thread(
                target=lambda: self._baseline_stop_worker(core),
                name="SafeBaselineStop",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror(
                "Detener limpieza",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    def _baseline_stop_worker(self, core):
        try:
            core.request_stop()
            self._post_ui("fresh_control_ok", "STOP enviado por V153.")
        except Exception as exc:
            self._post_ui("fresh_control_error", str(exc))

    def dock(self):
        try:
            core = self._fresh()
            threading.Thread(
                target=lambda: self._baseline_dock_worker(core),
                name="SafeBaselineDock",
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror(
                "Volver a base",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )

    def _baseline_dock_worker(self, core):
        try:
            core.request_dock()
            self._post_ui(
                "fresh_control_ok",
                "Regreso a base solicitado por V153.",
            )
        except Exception as exc:
            self._post_ui("fresh_control_error", str(exc))

    # =========================================== todo lo demás: sin escrituras
    def start_new_mapping(self):
        return self._baseline_disabled("Mapear vivienda")

    def finish_mapping(self):
        return self._baseline_disabled("Detener mapeo")

    def locate(self):
        return self._baseline_disabled("Hacer sonar")

    def set_suction(self, level):
        return None

    def set_water(self, level):
        return None

    def manual(self, direction):
        return self._baseline_disabled("Control manual")

    def _v138_reset_cleaning_state(
        self, vacuum, reason, ensure_dock=True
    ):
        raise RuntimeError(
            "V153 bloqueó el reset/neutralización heredado."
        )

    def _v114_run_safe_rectangles(
        self, target, kind, label, mode, suction, water
    ):
        return self._baseline_disabled("Limpieza de habitación/zona")

    def _run_schedule_now(self, schedule):
        return self._baseline_disabled("Programaciones")

    def _sync_no_go_async(self):
        # Guardar paredes en UI no escribe nada al E10 en esta baseline.
        return None

    def _v138_start_factory_edge(self, vacuum, label):
        return {
            "route": "V153 BLOCKED",
            "label": str(label),
            "success": False,
            "movement_commands": 0,
            "error": "EDGE deshabilitado en Safe Baseline",
        }

    def _v127_try_phase2_recovery(self, reason):
        return False

    def _v147_schedule_escape(self, serial, metrics):
        return False

    def _v147_request_abort(self, serial, metrics, reason):
        return None

    def _v144_execute_auto_abort(self, serial, metrics):
        self._v144_auto_abort_requested = False
        return False

    def _v149_request_global_transition(self, serial, metrics, reason):
        return False

    def _v150_session_allows_strategy_switch(self, serial):
        return False

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "baseline_clean_started":
            diag = dict(payload[0] or {}) if payload else {}
            self._fresh_last_event = {"baseline_started": diag}
            self._set_banner(
                "V153 · aspirado normal activo · único START 2/3 enviado."
            )
            return None

        if kind == "baseline_clean_finished":
            diag = dict(payload[0] or {}) if payload else {}
            self._fresh_last_event = {"baseline_finished": diag}
            if diag.get("error"):
                self._set_banner(
                    "V153 · prueba finalizó con error: "
                    + str(diag.get("error"))
                )
            else:
                self._set_banner(
                    "V153 · prueba física terminada · "
                    f"{diag.get('finish_reason', 'fin')}."
                )
            return None

        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        core = getattr(self, "_fresh_core", None)
        diag = core.diagnostic() if core is not None else {}
        lines = [
            "V153 SAFE BASELINE · ESTADO LIMPIO POST FACTORY RESET",
            "======================================================",
            f"core instalado={core is not None}",
            f"sesión activa={bool(diag.get('active'))}",
            f"sesión={diag.get('session') or '—'}",
            f"última prueba={diag.get('last') or '—'}",
            f"writes heredados bloqueados={diag.get('legacy_blocks', 0)}",
            f"último write bloqueado={diag.get('last_legacy_block') or '—'}",
            "regla V153: conectar = sólo lectura",
            "regla V153: abrir la app = cero escrituras físicas",
            "regla V153: aspirado normal = lectura/precheck + UN A2/3",
            "regla V153: no escribe mode/sweep/repeat/suction/water antes del START",
            "regla V153: no usa 7/3, EDGE, build-map, zonas, punto, remoto ni twice-clean",
            "regla V153: mapeo, dirigidas, paredes, manual y Scheduler quedan bloqueados",
            "regla V153: STOP y Volver a base sólo salen por acción explícita del usuario",
            "",
            "AUDITORÍA V153:",
            repr(diag.get("audit") or []),
            "",
            "",
        ]
        return "\n".join(lines) + app_v151.App._diagnostic_text(self)


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

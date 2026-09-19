import tkinter as tk

import app_v93


class App(app_v93.App):
    """V94: estado físico del E10 siempre visible en la barra superior."""

    STATE_COLORS = {
        "offline": ("#64748b", "#f8fafc", "#e2e8f0"),
        "idle": ("#475569", "#f8fafc", "#e2e8f0"),
        "paused": ("#b45309", "#fffbeb", "#fde68a"),
        "returning": ("#0369a1", "#eff6ff", "#bae6fd"),
        "charging": ("#15803d", "#ecfdf3", "#bbf7d0"),
        "cleaning": ("#4f46e5", "#eef2ff", "#c7d2fe"),
        "updating": ("#7c3aed", "#f5f3ff", "#ddd6fe"),
        "error": ("#dc2626", "#fef2f2", "#fecaca"),
    }

    def __init__(self):
        self._v94_state_badge = None
        self._v94_last_status_code = None
        self._v94_last_status_name = "Sin datos"
        self._v94_last_fault = 0
        self._v94_last_state_source = "inicio"
        super().__init__()
        self._v94_install_global_state_badge()
        self._v94_sync_global_state()

    # ============================================================ barra global
    def _v94_install_global_state_badge(self):
        if self._v94_state_badge is not None:
            return
        battery = getattr(self, "battery_header", None)
        if battery is None:
            return

        parent = battery.master
        badge = tk.Label(
            parent,
            text="ESTADO · Sin datos",
            bg="#f8fafc",
            fg="#64748b",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=8,
            highlightthickness=1,
            highlightbackground="#e2e8f0",
        )
        try:
            badge.pack(side="left", padx=(0, 8), after=battery)
        except Exception:
            badge.pack(side="left", padx=(0, 8))
        self._v94_state_badge = badge

    @classmethod
    def _v94_display_state(cls, status_code, status_name, fault, mapping_active=False):
        try:
            code = int(status_code)
        except Exception:
            code = None
        try:
            fault_code = int(fault or 0)
        except Exception:
            fault_code = 0

        if fault_code:
            return f"Error · código {fault_code}", "error"

        names = {
            0: ("Dormido", "idle"),
            1: ("En espera", "idle"),
            2: ("Pausado", "paused"),
            3: ("Volviendo a la base", "returning"),
            4: ("Cargando", "charging"),
            5: ("Aspirando", "cleaning"),
            6: ("Aspirando y trapeando", "cleaning"),
            7: ("Trapeando", "cleaning"),
            8: ("Actualizando firmware", "updating"),
        }
        text, style = names.get(
            code,
            (str(status_name or f"Estado {code if code is not None else '—'}"), "idle"),
        )
        if bool(mapping_active) and code in (5, 6, 7):
            text = f"{text} · mapeando"
        return text, style

    def _v94_apply_badge(self, text, style):
        self._v94_last_status_name = str(text or "Sin datos")
        badge = getattr(self, "_v94_state_badge", None)
        if badge is None:
            return
        fg, bg, border = self.STATE_COLORS.get(
            str(style),
            self.STATE_COLORS["idle"],
        )
        try:
            badge.configure(
                text=f"ESTADO · {self._v94_last_status_name}",
                fg=fg,
                bg=bg,
                highlightbackground=border,
            )
        except Exception:
            pass

    def _v94_sync_global_state(self):
        connected = bool(getattr(self, "vacuum", None))
        if not connected:
            self._v94_apply_badge("Sin conexión", "offline")
            return

        if self._v94_last_status_code is None:
            self._v94_apply_badge("Leyendo estado…", "idle")
            return

        text, style = self._v94_display_state(
            self._v94_last_status_code,
            self._v94_last_status_name,
            self._v94_last_fault,
            mapping_active=bool(getattr(self, "mapping_active", False)),
        )
        self._v94_apply_badge(text, style)

    # ======================================================= telemetría real
    def _render_status(self, status):
        try:
            self._v94_last_status_code = int(getattr(status, "status", -1))
        except Exception:
            self._v94_last_status_code = None
        try:
            self._v94_last_fault = int(getattr(status, "fault", 0) or 0)
        except Exception:
            self._v94_last_fault = 0
        try:
            self._v94_last_status_name = str(
                getattr(status, "status_name", "Estado desconocido")
            )
        except Exception:
            self._v94_last_status_name = "Estado desconocido"
        self._v94_last_state_source = "status()"

        result = super()._render_status(status)
        self._v94_sync_global_state()
        return result

    def _set_connection(self, connected, text=None):
        result = super()._set_connection(connected, text)
        if connected:
            if self._v94_last_status_code is None:
                self._v94_apply_badge("Leyendo estado…", "idle")
            else:
                self._v94_sync_global_state()
        else:
            self._v94_last_status_code = None
            self._v94_last_fault = 0
            self._v94_last_state_source = "conexión"
            self._v94_apply_badge("Sin conexión", "offline")
        return result

    # Si cambia el estado de mapeo entre dos polls, actualizamos el sufijo
    # inmediatamente sin inventar un estado físico nuevo.
    def _sync_mapping_step_buttons(self):
        result = super()._sync_mapping_step_buttons()
        self._v94_sync_global_state()
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V94 ACTIVO · estado global siempre visible",
            "=======================================================",
            (
                "estado superior: "
                f"code={self._v94_last_status_code!r} · "
                f"texto={self._v94_last_status_name!r} · "
                f"fault={self._v94_last_fault!r} · "
                f"fuente={self._v94_last_state_source}"
            ),
            (
                "regla V94: la barra superior refleja siempre la telemetría "
                "física status()/fault del E10 y no depende de la pestaña abierta"
            ),
            (
                "regla V94: durante status 5/6/7 agrega 'mapeando' únicamente "
                "si la sesión de mapeo local está activa"
            ),
            "",
            "",
        ]
        return "\n".join(lines) + inherited

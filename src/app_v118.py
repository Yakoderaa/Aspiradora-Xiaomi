import time

import app_v117
import app_v9


class App(app_v117.App):
    """V118: sesión física autoritativa + bloqueo de START duplicado."""

    def __init__(self):
        self._v118_physical_clean_active = False
        self._v118_physical_clean_seen = False
        self._v118_status_transitions = []
        self._v118_last_status_code = None
        self._v118_legacy_recovery_blocks = 0
        self._v118_logical_physical_mismatches = 0
        self._v118_last_mismatch = None
        super().__init__()

    # ===================================================== estado físico real
    def _v118_note_status(self, status_code):
        try:
            code = int(status_code)
        except Exception:
            return

        now = time.monotonic()
        previous = self._v118_last_status_code
        if previous != code:
            rows = list(self._v118_status_transitions)
            rows.append({
                "t": round(now, 3),
                "from": previous,
                "to": code,
            })
            self._v118_status_transitions = rows[-30:]
            self._v118_last_status_code = code

        if code in (5, 6, 7):
            self._v118_physical_clean_active = True
            self._v118_physical_clean_seen = True
        elif code == 3 and self._v118_physical_clean_seen:
            # El retorno todavía pertenece a la misma sesión física.
            self._v118_physical_clean_active = True
        elif code == 4:
            self._v118_physical_clean_active = False
            self._v118_physical_clean_seen = False

        logical = bool(getattr(self, "_v115_global_clean_active", False))
        physical = bool(self._v118_physical_clean_active)
        if physical and not logical:
            self._v118_logical_physical_mismatches += 1
            self._v118_last_mismatch = (
                f"status={code}: físico activo con worker V115 inactivo"
            )

    def _render_status(self, status):
        self._v118_note_status(getattr(status, "status", None))
        result = super()._render_status(status)
        self.after_idle(self._v118_force_clean_button_state)
        return result

    def _v118_device_guard_active(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            return False
        try:
            return bool(vacuum.global_clean_guard_active())
        except Exception:
            return False

    def _v118_force_clean_button_state(self):
        physical_busy = (
            bool(self._v118_physical_clean_active)
            or self._v118_device_guard_active()
        )
        if not physical_busy:
            return
        for button in self._v116_known_clean_buttons():
            try:
                button.configure(state="disabled")
            except Exception:
                pass

    def _v95_sync_global_controls(self):
        result = super()._v95_sync_global_controls()
        self._v118_force_clean_button_state()
        return result

    # =========================================== recovery sólo durante mapeo
    def _v73_schedule_recovery(self, phase, reason):
        if (
            not bool(getattr(self, "mapping_active", False))
            and (
                bool(self._v118_physical_clean_active)
                or self._v118_device_guard_active()
            )
        ):
            self._v118_legacy_recovery_blocks += 1
            return None
        return super()._v73_schedule_recovery(phase, reason)

    def _v75_recovery_valid(self, vacuum, mapping_serial, generation):
        if (
            not bool(getattr(self, "mapping_active", False))
            and (
                bool(self._v118_physical_clean_active)
                or self._v118_device_guard_active()
            )
        ):
            return False
        return super()._v75_recovery_valid(
            vacuum,
            mapping_serial,
            generation,
        )

    # ============================================================ START único
    def start_clean(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is not None:
            try:
                if vacuum.global_clean_guard_active():
                    self._set_banner(
                        "El E10 ya tiene una limpieza física activa. "
                        "No envié un segundo START."
                    )
                    return
            except Exception:
                pass
            try:
                vacuum.reset_motor_start_audit()
            except Exception:
                pass

        self._v118_status_transitions = []
        self._v118_last_status_code = None
        self._v118_legacy_recovery_blocks = 0
        self._v118_logical_physical_mismatches = 0
        self._v118_last_mismatch = None
        return super().start_clean()

    # =========================================================== diagnóstico
    @staticmethod
    def _v118_age(now, value):
        try:
            value = float(value or 0.0)
            if value <= 0:
                return "—"
            return f"{max(0.0, now - value):.1f}s"
        except Exception:
            return "—"

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        now = time.monotonic()

        if vacuum is None:
            guard = False
            source = "—"
            started = 0.0
            cleared = 0.0
            terminal_streak = 0
            blocked = 0
            last_blocked = None
            audit = []
        else:
            try:
                guard = bool(vacuum.global_clean_guard_active())
            except Exception:
                guard = False
            source = getattr(vacuum, "_global_clean_guard_source", None) or "—"
            started = float(
                getattr(vacuum, "_global_clean_guard_started_at", 0.0) or 0.0
            )
            cleared = float(
                getattr(vacuum, "_global_clean_guard_cleared_at", 0.0) or 0.0
            )
            terminal_streak = int(
                getattr(vacuum, "_global_clean_terminal_streak", 0) or 0
            )
            blocked = int(
                getattr(vacuum, "_blocked_duplicate_starts", 0) or 0
            )
            last_blocked = getattr(
                vacuum,
                "_last_blocked_duplicate_start",
                None,
            )
            audit = list(
                getattr(vacuum, "_motor_start_audit", []) or []
            )[-20:]

        transitions = self._v118_status_transitions[-20:]
        lines = [
            "DIAGNÓSTICO V118 ACTIVO · sesión física + START único",
            "=====================================================",
            (
                f"sesión física activa={self._v118_physical_clean_active} · "
                f"device guard={guard} · fuente={source}"
            ),
            (
                f"guard empezó hace={self._v118_age(now, started)} · "
                f"último clear hace={self._v118_age(now, cleared)} · "
                f"terminal streak 0/1={terminal_streak}/6"
            ),
            (
                f"START duplicados bloqueados={blocked} · "
                f"último={last_blocked or '—'}"
            ),
            (
                f"mismatch físico>worker V115="
                f"{self._v118_logical_physical_mismatches} · "
                f"último={self._v118_last_mismatch or '—'}"
            ),
            (
                f"recoveries legacy bloqueados fuera de mapeo="
                f"{self._v118_legacy_recovery_blocks}"
            ),
            "transiciones físicas recientes:",
        ]
        if transitions:
            for item in transitions:
                lines.append(
                    f"    {item.get('from')} -> {item.get('to')} "
                    f"@{item.get('t')}"
                )
        else:
            lines.append("    —")

        lines.append("auditoría de órdenes de ARRANQUE:")
        if audit:
            for item in audit:
                lines.append(
                    "    "
                    f"{item.get('operation')} · "
                    f"{item.get('siid')}/{item.get('aiid')} · "
                    f"blocked={item.get('blocked')} · "
                    f"params={item.get('params')} · "
                    f"resp={item.get('response')} · "
                    f"err={item.get('error')}"
                )
        else:
            lines.append("    —")

        lines.extend([
            "regla V118: una vez visto status 5/6/7, el candado vive hasta status=4 físico; dos 0/1 transitorios no lo liberan",
            "regla V118: mientras el candado está activo, una segunda limpieza global/bordes/espiral/habitación/zona se rechaza antes del START",
            "regla V118: el guard de mapeo también considera el candado físico aunque V116 haya soltado su worker antes de tiempo",
            "regla V118: si hay pitido con auditoría sin nuevos START ni locate, el sonido no fue provocado por una orden de nuestra app",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

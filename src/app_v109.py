import re
import tkinter as tk

import app_v108
import app_v9


class App(app_v108.App):
    """V109: diagnóstico a prueba de fallos + privacidad de IP en la UI."""

    _V109_IPV4_RE = re.compile(
        r"(?<!\d)(?:25[0-5]|2[0-4]\d|1?\d?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!\d)"
    )

    def __init__(self):
        self._v109_diag_full_ok = 0
        self._v109_diag_fallbacks = 0
        self._v109_diag_refreshes = 0
        self._v109_diag_copy_ok = 0
        self._v109_last_diag_error = "—"
        self._v109_redactions = 0
        super().__init__()

    # ========================================================= privacidad UI
    def _set_connection(self, connected, text=None):
        """Nunca mostrar la IP del robot en el estado visible de conexión."""
        if connected:
            return super()._set_connection(True, "Conectado")
        return super()._set_connection(False, text or "Desconectado")

    @classmethod
    def _v109_redact_ips(cls, value):
        text = str(value or "")

        def repl(_match):
            return "[IP OCULTA]"

        redacted, count = cls._V109_IPV4_RE.subn(repl, text)
        return redacted, int(count)

    # ============================================== diagnóstico de emergencia
    def _v109_emergency_diagnostic(self, exc):
        self._v109_diag_fallbacks += 1
        self._v109_last_diag_error = (
            f"{type(exc).__name__}: {str(exc).strip() or repr(exc)}"
        )

        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception as snap_exc:
            snapshot = {}
            snapshot_error = (
                f"{type(snap_exc).__name__}: "
                f"{str(snap_exc).strip() or repr(snap_exc)}"
            )
        else:
            snapshot_error = "—"

        try:
            map_id = self._v72_active_map_id() or "—"
        except Exception:
            map_id = "—"

        try:
            points = list((snapshot or {}).get("points") or [])
        except Exception:
            points = []

        try:
            robot = (snapshot or {}).get("robot")
        except Exception:
            robot = None

        try:
            base = (snapshot or {}).get("charging_base")
        except Exception:
            base = None

        try:
            native = (snapshot or {}).get("native_grid")
            native_cells = (
                sum(1 for value in list((native or {}).get("cells") or []) if int(value))
                if isinstance(native, dict)
                else 0
            )
        except Exception:
            native = None
            native_cells = 0

        lines = [
            "DIAGNÓSTICO V109 DE EMERGENCIA",
            "================================",
            "El diagnóstico completo heredado falló, pero V109 evita dejar la ventana vacía.",
            "",
            f"error diagnóstico: {self._v109_last_diag_error}",
            f"error snapshot: {snapshot_error}",
            f"mapa activo: {map_id}",
            f"mapping_active: {bool(getattr(self, 'mapping_active', False))}",
            f"mapping_phase: {getattr(self, 'mapping_phase', None)!r}",
            f"status físico: {getattr(self, '_v84_physical_status', None)!r}",
            f"retorno: {bool(getattr(self, '_v84_returning', False))}",
            f"dock: {bool(getattr(self, '_v84_dock_latched', False))}",
            f"puntos locales: {len(points)}",
            f"robot: {robot!r}",
            f"base: {base!r}",
            f"native_grid presente: {isinstance(native, dict)}",
            f"native_grid celdas: {native_cells}",
            f"V107 final guardado: {bool(getattr(self, '_v107_final_saved', False))}",
            f"V107 esperando final: {bool(getattr(self, '_v107_hide_surface_until_final', False))}",
            f"V108 modo visual: {getattr(self, '_v108_last_mode', '—')}",
            "",
            "Regla V109: esta salida mínima siempre debe aparecer aunque falle una sección heredada.",
        ]
        return "\n".join(lines)

    def _diagnostic_text(self):
        try:
            inherited = super()._diagnostic_text()
            self._v109_diag_full_ok += 1
            text = (
                "DIAGNÓSTICO V109 ACTIVO · diagnóstico seguro + privacidad IP\n"
                "================================================================\n"
                f"diagnósticos completos OK={self._v109_diag_full_ok} · "
                f"fallbacks={self._v109_diag_fallbacks} · "
                f"último error={self._v109_last_diag_error}\n"
                "privacidad: estado de conexión visible=Conectado · IP oculta en UI/diagnóstico\n"
                "regla V109: una excepción heredada no puede dejar F12 en blanco\n"
                "\n"
                + str(inherited or "")
            )
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)

        redacted, count = self._v109_redact_ips(text)
        self._v109_redactions += int(count)
        return redacted

    # ============================================ ventana F12 a prueba de fallo
    def _refresh_map_diag_window(self):
        win = getattr(self, "_map_diag_window", None)
        box = getattr(self, "_map_diag_text", None)

        try:
            if (
                not win
                or not win.winfo_exists()
                or not box
                or not box.winfo_exists()
            ):
                return
        except Exception:
            return

        try:
            text = self._diagnostic_text()
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)

        if not str(text or "").strip():
            self._v109_diag_fallbacks += 1
            text = (
                "DIAGNÓSTICO V109 DE EMERGENCIA\n"
                "================================\n"
                "La cadena de diagnóstico devolvió texto vacío.\n"
                f"mapping_active={bool(getattr(self, 'mapping_active', False))}\n"
                f"status={getattr(self, '_v84_physical_status', None)!r}\n"
                f"modo visual={getattr(self, '_v108_last_mode', '—')}\n"
            )

        try:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", str(text))
            box.configure(state="disabled")
            self._v109_diag_refreshes += 1
        except Exception:
            return

        try:
            win.after(700, self._refresh_map_diag_window)
        except Exception:
            pass

    def _copy_map_diagnostics(self):
        try:
            text = self._diagnostic_text()
        except Exception as exc:
            text = self._v109_emergency_diagnostic(exc)

        if not str(text or "").strip():
            text = self._v109_emergency_diagnostic(
                RuntimeError("diagnóstico vacío")
            )

        redacted, count = self._v109_redact_ips(text)
        self._v109_redactions += int(count)

        try:
            self.clipboard_clear()
            self.clipboard_append(redacted)
            self.update_idletasks()
            self._v109_diag_copy_ok += 1
            self._set_banner(
                "Diagnóstico copiado · direcciones IP ocultas."
            )
        except Exception:
            pass

    # =========================================================== diagnóstico
    # El propio bloque V109 se genera dentro de _diagnostic_text para poder
    # envolver con try/except toda la cadena heredada.


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

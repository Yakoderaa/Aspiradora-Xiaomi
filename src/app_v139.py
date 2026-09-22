import time
import tkinter as tk
from tkinter import messagebox

import app_v138
import app_v9


class App(app_v138.App):
    """V139: EDGE directo sin START global + UI/diagnóstico de prueba."""

    EDGE_CONFIRM_TIMEOUT = 6.0

    def __init__(self):
        self._v139_edge_diag = {}
        self._v139_top_clean_removed = False
        self._v139_diag_clear_count = 0
        self._v139_diag_cleared_at = 0.0
        self._v139_diag_baseline = {}
        self._v139_diag_clear_button = None
        super().__init__()

        # El usuario pidió quitar únicamente el acceso superior a limpieza
        # global. La limpieza de las pantallas correspondientes sigue intacta.
        self.after_idle(self._v139_remove_top_clean_button)
        self.after(800, self._v139_remove_top_clean_button)
        self.after(2600, self._v139_remove_top_clean_button)

    # ====================================================== Paso 1: EDGE puro
    def _v138_start_factory_edge(self, vacuum, label):
        """V139: una única orden de movimiento EDGE, sin 2/3 ni 2/1.

        V138 probó sweep_type=2 seguido de 2/3. El E10 anunció bordes y luego
        limpieza normal. V139 conserva el reset frío de V138 pero reemplaza
        ese START genérico por set-room-clean en modo Edge.
        """
        diag = {
            "route": "V139 EDGE directo: sweep_type=2 -> 7/3 ['',2,1]",
            "label": str(label),
            "status_before": None,
            "sweep_before": None,
            "sweep_after_set": None,
            "response": None,
            "status_after": None,
            "sweep_after": None,
            "success": False,
            "movement_commands": 0,
            "generic_start_sent": False,
            "error": None,
        }
        try:
            before = vacuum._get_many([
                ("status", 2, 1),
                ("sweep_type", 2, 8),
            ])
            diag["status_before"] = self._v138_int(before.get("status"))
            diag["sweep_before"] = self._v138_int(before.get("sweep_type"))

            # Seleccionamos bordes antes de la única acción de movimiento.
            vacuum.set_sweep_type(2)
            time.sleep(0.25)
            try:
                diag["sweep_after_set"] = self._v138_int(
                    vacuum._value(2, 8)
                )
            except Exception:
                pass
            if diag["sweep_after_set"] not in (None, 2):
                raise RuntimeError(
                    "El E10 no confirmó sweep_type=2 antes de iniciar EDGE"
                )

            response = vacuum._send_motor_start(
                "mapping_edge_v139/direct-edge",
                7,
                3,
                ["", 2, 1],
                allow_when_guarded=True,
            )
            diag["movement_commands"] = 1
            diag["response"] = repr(response)[:500]

            deadline = time.monotonic() + self.EDGE_CONFIRM_TIMEOUT
            while time.monotonic() < deadline:
                state = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status = self._v138_int(state.get("status"))
                sweep = self._v138_int(state.get("sweep_type"))
                diag["status_after"] = status
                diag["sweep_after"] = sweep

                # Exigimos movimiento físico. sweep_type=2 es evidencia extra,
                # pero algunos B112 dejan de publicarlo de forma estable luego
                # del START; por eso el gate físico final sigue siendo V138.
                if status in (5, 6, 7):
                    diag["success"] = True
                    self._v139_edge_diag = dict(diag)
                    return diag
                time.sleep(0.30)

            raise RuntimeError(
                "EDGE directo no confirmó movimiento físico "
                f"(status={diag.get('status_after')!r}, "
                f"sweep={diag.get('sweep_after')!r})"
            )
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            raise
        finally:
            self._v139_edge_diag = dict(diag)
            # V138 consulta este mismo bloque para su flujo/reintento.
            self._v138_factory_edge_diag = dict(diag)

    # =================================================== UI: limpieza superior
    def _v139_remove_top_clean_button(self):
        button = getattr(self, "_v95_clean_button", None)
        if button is None:
            return False
        try:
            button.pack_forget()
            self._v139_top_clean_removed = True
            return True
        except Exception:
            return False

    # ================================================ diagnóstico reiniciable
    @staticmethod
    def _v139_diag_sections(text):
        sections = []
        current = []
        for raw in str(text or "").splitlines():
            line = raw.rstrip()
            if line.startswith("DIAGNÓSTICO ") and current:
                block = "\n".join(current).strip()
                if block:
                    sections.append(block)
                current = [line]
            else:
                current.append(line)
        block = "\n".join(current).strip()
        if block:
            sections.append(block)
        return sections

    def _v139_full_diagnostic_text(self):
        inherited = super()._diagnostic_text()
        cleared = (
            f"{max(0.0, time.monotonic() - self._v139_diag_cleared_at):.1f}s"
            if self._v139_diag_cleared_at
            else "—"
        )
        lines = [
            "DIAGNÓSTICO V139 ACTIVO · EDGE directo + diagnóstico reiniciable",
            "==================================================================",
            f"EDGE V139={self._v139_edge_diag or '—'}",
            (
                "Paso1: UNA orden de movimiento 7/3 ['',2,1] · "
                "START genérico 2/3=PROHIBIDO · 2/1=PROHIBIDO"
            ),
            (
                f"botón superior Iniciar limpieza eliminado="
                f"{self._v139_top_clean_removed}"
            ),
            (
                f"reinicios diagnóstico={self._v139_diag_clear_count} · "
                f"último hace={cleared}"
            ),
            (
                "Borrar diagnóstico reinicia sólo la vista/captura diagnóstica; "
                "no modifica el estado operativo del robot"
            ),
            "",
            "",
        ]
        return "\n".join(lines) + inherited

    def _diagnostic_text(self):
        full = self._v139_full_diagnostic_text()
        baseline = dict(self._v139_diag_baseline or {})
        if not baseline:
            return full

        changed = []
        for block in self._v139_diag_sections(full):
            header = block.splitlines()[0] if block else ""
            if baseline.get(header) != block:
                changed.append(block)

        age = max(
            0.0,
            time.monotonic() - float(self._v139_diag_cleared_at or 0.0),
        )
        head = (
            "DIAGNÓSTICO REINICIADO V139\n"
            "============================\n"
            f"sesión={self._v139_diag_clear_count} · edad={age:.1f}s\n"
            "Sólo aparecen secciones que cambiaron desde Borrar diagnóstico.\n"
        )
        if not changed:
            return head + "\nSin actividad diagnóstica nueva desde el reinicio."
        return head + "\n\n" + "\n\n".join(changed)

    def _v139_install_diag_clear_button(self):
        win = getattr(self, "_map_diag_window", None)
        if win is None:
            return False
        try:
            if not win.winfo_exists():
                return False
        except Exception:
            return False

        existing = getattr(self, "_v139_diag_clear_button", None)
        try:
            if existing is not None and existing.winfo_exists():
                return True
        except Exception:
            pass

        copy_button = None

        def walk(widget):
            yield widget
            try:
                children = widget.winfo_children()
            except Exception:
                children = []
            for child in children:
                yield from walk(child)

        for widget in walk(win):
            try:
                if (
                    str(widget.winfo_class()) == "Button"
                    and str(widget.cget("text") or "").strip()
                    == "Copiar diagnóstico"
                ):
                    copy_button = widget
                    break
            except Exception:
                continue

        if copy_button is None:
            return False

        parent = copy_button.master
        button = tk.Button(
            parent,
            text="Borrar diagnóstico",
            command=self._v139_confirm_clear_diagnostics,
        )
        button.pack(side="right", padx=(0, 8))
        self._v139_diag_clear_button = button
        return True

    def _open_map_diagnostics(self):
        result = super()._open_map_diagnostics()
        self.after_idle(self._v139_install_diag_clear_button)
        return result

    def _v139_confirm_clear_diagnostics(self):
        ok = messagebox.askyesno(
            "Borrar diagnóstico",
            "¿Querés borrar el diagnóstico visible y empezar una captura nueva?\n\n"
            "Esto no modifica el mapa ni envía comandos a la aspiradora.",
            parent=getattr(self, "_map_diag_window", self),
        )
        if not ok:
            return False

        self._v139_diag_clear_count += 1
        self._v139_diag_cleared_at = time.monotonic()

        # Se toma una fotografía del diagnóstico actual. Desde acá la ventana
        # muestra únicamente las secciones cuyo contenido cambie.
        raw = self._v139_full_diagnostic_text()
        self._v139_diag_baseline = {
            block.splitlines()[0]: block
            for block in self._v139_diag_sections(raw)
            if block
        }

        try:
            box = getattr(self, "_map_diag_text", None)
            if box is not None and box.winfo_exists():
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", self._diagnostic_text())
                box.configure(state="disabled")
        except Exception:
            pass

        self._set_banner(
            "Diagnóstico borrado · nueva captura iniciada. "
            "El estado del robot no fue modificado."
        )
        return True


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise

import tkinter as tk

import app_v29


class App(app_v29.App):
    """v30: recuperación histórica por pose-id + diagnóstico MIoT visible."""

    def __init__(self):
        self._last_map_state_debug = {}
        self._map_diag_window = None
        self._map_diag_text = None
        super().__init__()

    def _build_map_page(self):
        super()._build_map_page()
        try:
            parent = self.map_status_label.master
            self.map_diag_button = self._button(
                parent,
                "Diagnóstico",
                self._open_map_diagnostics,
                compact=True,
            )
            self.map_diag_button.pack(side="right", padx=(8, 0))
        except Exception:
            pass

    @staticmethod
    def _short_raw(value, limit=700):
        try:
            text = repr(value)
        except Exception:
            text = str(value)
        if len(text) > limit:
            return text[:limit] + "…"
        return text

    def _diagnostic_text(self):
        state = dict(self._last_map_state_debug or {})
        snapshot = self.local_map.snapshot() if self.local_map else {}
        robot = snapshot.get("robot") if isinstance(snapshot, dict) else None
        lines = [
            "Xiaomi Robot Vacuum E10 · diagnóstico de mapa en vivo",
            "",
            f"fase: {getattr(self, 'mapping_phase', 0)} · mapping_active: {bool(getattr(self, 'mapping_active', False))}",
            f"posición local: {self._short_raw(robot)}",
            f"fuente posición: {state.get('position_source')}",
            f"fuente trayectoria: {state.get('path_source')}",
            f"pose-id encabezado 10/5: {state.get('direct_header_id')}",
            f"último pose-id: {state.get('last_pose_id')}",
            f"rango 10/12: {state.get('probe_start')} → {state.get('probe_end')}",
            f"puntos 10/5: {state.get('direct_path_count', 0)}",
            f"puntos 10/12: {state.get('action_path_count', 0)}",
            f"puntos acumulados: {state.get('accumulated_path_count', 0)}",
            f"nuevos en último sondeo: {state.get('new_path_count', 0)}",
            f"error 10/12: {state.get('path_action_error') or '—'}",
            "",
            f"10/5 crudo: {self._short_raw(state.get('raw_path_direct'))}",
            f"10/12 crudo: {self._short_raw(state.get('raw_path_action'))}",
            f"10/24 crudo: {self._short_raw(state.get('raw_robot'))}",
            f"10/22 crudo: {self._short_raw(state.get('raw_base'))}",
            "",
            f"nota: {state.get('telemetry_note') or '—'}",
        ]
        return "\n".join(lines)

    def _copy_map_diagnostics(self):
        text = self._diagnostic_text()
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            self._set_banner("Diagnóstico del mapa copiado al portapapeles.")
        except Exception:
            pass

    def _refresh_map_diag_window(self):
        win = self._map_diag_window
        box = self._map_diag_text
        try:
            if not win or not win.winfo_exists() or not box or not box.winfo_exists():
                return
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", self._diagnostic_text())
            box.configure(state="disabled")
            win.after(350, self._refresh_map_diag_window)
        except tk.TclError:
            return

    def _open_map_diagnostics(self):
        try:
            if self._map_diag_window and self._map_diag_window.winfo_exists():
                self._map_diag_window.lift()
                self._map_diag_window.focus_force()
                return
        except Exception:
            pass

        win = tk.Toplevel(self)
        win.title("Diagnóstico · mapa en vivo")
        win.geometry("760x520")
        win.minsize(620, 420)
        self._map_diag_window = win

        box = tk.Text(
            win,
            wrap="word",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        box.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        box.configure(state="disabled")
        self._map_diag_text = box

        row = tk.Frame(win)
        row.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(row, text="Copiar diagnóstico", command=self._copy_map_diagnostics).pack(side="right")
        tk.Label(
            row,
            text="Dejá esta ventana abierta mientras el robot se mueve; se actualiza sola.",
        ).pack(side="left")

        self._refresh_map_diag_window()

    def _apply_map_state(self, state):
        if isinstance(state, dict):
            self._last_map_state_debug = dict(state)
        result = super()._apply_map_state(state)

        # En la línea secundaria mostramos el pose-id real y el rango histórico
        # que se está solicitando. Si todavía falla, una captura ya nos dice dónde.
        if self.mapping_active and hasattr(self, "mapping_steps_info"):
            try:
                header = (state or {}).get("direct_header_id")
                start = (state or {}).get("probe_start")
                end = (state or {}).get("probe_end")
                if header is not None:
                    self.mapping_steps_info.configure(
                        text=f"10/5 pose-id {header} · recuperando 10/12 {start}→{end} · Diagnóstico disponible"
                    )
            except Exception:
                pass
        return result


if __name__ == "__main__":
    app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

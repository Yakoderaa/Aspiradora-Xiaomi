import tkinter as tk

import app_v30


class App(app_v30.App):
    """v31: diagnóstico MIoT imposible de ocultar + telemetría cruda en el mapa."""

    def __init__(self):
        super().__init__()
        self._install_global_diagnostics_access()
        self.bind_all("<F12>", lambda _event: self._open_map_diagnostics())

    def _install_global_diagnostics_access(self):
        """Instala acceso global fuera del layout interno del mapa.

        v30 intentaba insertar el botón dentro del encabezado del mapa y cualquier
        error quedaba silenciado. Acá lo ponemos en la cabecera principal, junto a
        conexión/actualizaciones, donde siempre hay un contenedor estable.
        """
        parent = self.connection_label.master
        self.global_map_diag_button = tk.Button(
            parent,
            text="DIAGNÓSTICO MIoT",
            command=self._open_map_diagnostics,
            bg="#ff6900",
            fg="white",
            activebackground="#ea5f00",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
        )
        self.global_map_diag_button.pack(side="left", padx=(8, 0))

    @staticmethod
    def _diag_inline(value, limit=95):
        try:
            text = repr(value)
        except Exception:
            text = str(value)
        text = text.replace("\n", " ")
        if len(text) > limit:
            return text[:limit] + "…"
        return text

    def _apply_map_state(self, state):
        result = super()._apply_map_state(state)

        # Si seguimos sin una trayectoria útil, mostramos los paquetes crudos en
        # la propia pantalla. Esto permite diagnosticar incluso si la ventana
        # secundaria no llegara a abrir por algún problema de Windows/Tk.
        if self.mapping_active and hasattr(self, "mapping_steps_info"):
            try:
                accumulated = int((state or {}).get("accumulated_path_count", 0) or 0)
                if accumulated <= 1:
                    raw_105 = self._diag_inline((state or {}).get("raw_path_direct"))
                    raw_1012 = self._diag_inline((state or {}).get("raw_path_action"))
                    raw_1024 = self._diag_inline((state or {}).get("raw_robot"), 65)
                    self.mapping_steps_info.configure(
                        text=(
                            f"DIAG v31 · 10/5={raw_105} · 10/12={raw_1012} · "
                            f"10/24={raw_1024} · F12 para diagnóstico completo"
                        )
                    )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        base = super()._diagnostic_text()
        return (
            "DIAGNÓSTICO V31 ACTIVO · acceso global F12\n"
            "=============================================\n"
            + base
        )


if __name__ == "__main__":
    app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

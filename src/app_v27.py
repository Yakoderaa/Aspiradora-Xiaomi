import app_v26


class App(app_v26.App):
    """v27: posición fresca y succión en caliente."""

    def _choose_suction(self, value):
        """Cambia potencia sin detener ni reiniciar la limpieza actual."""
        level = max(1, min(4, int(value)))
        self.suction_var.set(level)
        self.settings["suction"] = level
        self.store.save(self.settings)
        self._refresh_choice_buttons()

        if not self.vacuum:
            return

        labels = {1: "Silenciosa", 2: "Normal", 3: "Fuerte", 4: "Turbo"}
        self._run_command(
            f"Cambiando succión a {labels.get(level, level)}…",
            lambda: self.vacuum.set_suction(level),
        )


if __name__ == "__main__":
    app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
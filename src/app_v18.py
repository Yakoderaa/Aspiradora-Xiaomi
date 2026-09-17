import app_v17

# app_v9 sólo reexportaba parte de la paleta. v17 usa APP_BG al crear la página
# Programar, así que lo dejamos disponible antes de construir la interfaz.
app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9.APP_BG = "#f4f5f7"


class App(app_v17.App):
    """v18: integración estable de zonas, bloqueos y programaciones."""
    pass


if __name__ == "__main__":
    app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise

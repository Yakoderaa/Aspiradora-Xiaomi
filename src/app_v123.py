import app_v122
import app_v9


class App(app_v122.App):
    """V123: whole-home preparado por 7/3 + trigger físico 2/3."""

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        native = (
            dict(
                getattr(
                    vacuum,
                    "_last_mapping_whole_home_diag",
                    {},
                )
                or {}
            )
            if vacuum is not None
            else {}
        )
        lines = [
            "DIAGNÓSTICO V123 ACTIVO · whole-home 7/3 + trigger 2/3",
            "=======================================================",
            f"fase2 E10 V123={native or '—'}",
            "ruta V123: 7/3 ids-vacíos modo0 Start -> espera -> si status=4, 2/3 start-only-sweep",
            "regla V123: 2/3 sólo se emite si 7/3 fue aceptado pero el robot sigue físicamente en dock",
            "regla V123: jamás usa start-sweep 2/1 en la transición de Fase 2",
            "regla V123: no ejecuta segundo build-map, STOP/manual/recovery ni borra la sesión Xiaomi",
            "regla V123: V121/V122 conservan primer dock intermedio, segundo dock final y rechazo de grids inválidos",
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

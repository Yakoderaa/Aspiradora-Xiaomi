import app_v86


class App(app_v86.App):
    """V87: modos nativos Bordes/Espiral del Xiaomi E10."""

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V87 ACTIVO · modos nativos de limpieza",
            "===================================================",
            "sweep-type E10: global=0 · bordes=2 · espiral=4 · remoto=5",
            "regla V87: Limpiar bordes usa sweep-type=2 antes de iniciar",
            "regla V87: Espiral usa sweep-type=4 antes de iniciar",
            "regla V87: Iniciar normal fuerza sweep-type=0 para no heredar el patrón anterior",
            "regla V87: Bordes/Espiral respetan Aspirar, Aspirar + trapear o Trapear seleccionados",
        ]
        return "\n".join(lines) + "\n\n" + inherited

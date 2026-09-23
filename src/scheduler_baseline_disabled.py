"""V153 Safe Baseline: Scheduler deliberadamente deshabilitado.

Se conserva el ejecutable por compatibilidad del instalador, pero esta release
no puede iniciar tareas físicas en segundo plano.
"""


def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

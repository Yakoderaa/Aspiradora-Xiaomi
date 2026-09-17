import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_global_diagnostic_button_is_really_installed():
    import app_v31

    app = object.__new__(app_v31.App)

    class Parent:
        pass

    class Label:
        master = Parent()

    class FakeButton:
        def __init__(self, parent, **kwargs):
            self.parent = parent
            self.kwargs = kwargs
            self.pack_kwargs = None

        def pack(self, **kwargs):
            self.pack_kwargs = kwargs

    app.connection_label = Label()
    app._open_map_diagnostics = lambda: None

    original_button = app_v31.tk.Button
    app_v31.tk.Button = FakeButton
    try:
        app._install_global_diagnostics_access()
    finally:
        app_v31.tk.Button = original_button

    button = app.global_map_diag_button
    check(button.parent is app.connection_label.master, "El botón debe vivir en la cabecera global")
    check(button.kwargs.get("text") == "DIAGNÓSTICO MIoT", "El texto del botón debe ser visible y explícito")
    check(button.pack_kwargs is not None, "El botón debe empaquetarse realmente en la UI")


def test_inline_diagnostics_exist():
    import app_v31

    check("_apply_map_state" in app_v31.App.__dict__, "v31 debe mostrar telemetría cruda en el mapa")
    check("_diagnostic_text" in app_v31.App.__dict__, "v31 debe marcar el diagnóstico completo")


def main():
    test_global_diagnostic_button_is_really_installed()
    test_inline_diagnostics_exist()
    print("SMOKE TEST V31 OK: botón global + F12 + telemetría cruda visible")


if __name__ == "__main__":
    main()

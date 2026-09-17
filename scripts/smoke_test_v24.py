import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    import app_v23
    import app_v24
    import device_metadata_patch

    check(issubclass(app_v24.App, app_v23.App), "v24 debe conservar toda la interfaz/funciones v23")
    for method in (
        "_build_devices_home",
        "_show_devices_home",
        "_open_device",
        "_rename_device_dialog",
        "_refresh_device_card",
        "_draw_e10_visual",
    ):
        check(method in app_v24.App.__dict__, f"Falta la función de dispositivos: {method}")

    # v23 sigue siendo responsable de las mejoras solicitadas inmediatamente
    # antes: mapa movible de Inicio, pestaña activa y Programar moderno.
    for method in (
        "_home_map_press",
        "_home_map_drag",
        "_home_map_release",
        "_build_scheduler_page",
    ):
        check(method in app_v23.App.__dict__, f"La v24 perdió una mejora de v23: {method}")

    check(hasattr(app_v23.App, "_v23_nav") or "_nav_button_v22" in app_v23.App.__dict__, "Falta navegación visual activa")
    check(callable(device_metadata_patch.install), "Falta persistencia de nombre/did/región del QR")

    # El nombre genérico debe migrar a Emilia en esta instalación y un nombre
    # explícito debe conservarse.
    dummy = object.__new__(app_v24.App)
    dummy.settings = {"device_name": "Xiaomi Robot Vacuum E10"}
    check(dummy._device_display_name() == "Emilia", "No se aplicó la migración del nombre Emilia")
    dummy.settings = {"device_name": "Living"}
    check(dummy._device_display_name() == "Living", "Se pisó un nombre personalizado")

    print("SMOKE TEST V24 OK: selector de dispositivos, Emilia, navegación v23, mapa Inicio y Programar")


if __name__ == "__main__":
    main()

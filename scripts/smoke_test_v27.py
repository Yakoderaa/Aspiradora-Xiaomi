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
    import app_v27
    import updater
    from settings_store import SettingsStore
    from xiaomi_e10_live import XiaomiE10Live

    live = object.__new__(XiaomiE10Live)
    calls = []
    samples = [
        {"path": "", "path_start": None, "path_end": None, "charging_base": "0,0,0", "robot": "0,0,0"},
        {"path": "", "path_start": None, "path_end": None, "charging_base": "0,0,0", "robot": "1.5,0,0"},
    ]

    def fake_get_many(defs):
        calls.append(list(defs))
        return samples[min(len(calls) - 1, 1)]

    live._get_many = fake_get_many
    s1 = live.local_map_state()
    s2 = live.local_map_state()
    check(s1["robot"]["x"] == 0.0, "Primera posición robot incorrecta")
    check(s2["robot"]["x"] == 1.5, "10/24 debe refrescarse entre sondeos")
    check(any(item[1:] == (10, 24) for item in calls[0]), "El sondeo fresco debe incluir 10/24")

    check("_choose_suction" in app_v27.App.__dict__, "v27 debe implementar succión en caliente")
    check("github_token" not in SettingsStore.PROTECTED_FIELDS, "No debe quedar soporte de token GitHub privado")
    check(not hasattr(updater, "_github_token"), "Updater público no debe pedir credenciales GitHub")

    print("SMOKE TEST V27 OK: posición fresca, succión caliente y updater público")


if __name__ == "__main__":
    main()

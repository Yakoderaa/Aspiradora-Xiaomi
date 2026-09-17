import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v46
import app_v47
from xiaomi_e10_map_v47 import XiaomiE10MapV47


class FakeDevice:
    def __init__(self, state):
        self.state = state
        self.set_calls = []

    def get_property_by(self, siid, piid):
        assert (siid, piid) == (10, 23)
        return [{"code": 0, "value": self.state}]

    def set_property_by(self, siid, piid, value):
        assert (siid, piid) == (10, 23)
        self.set_calls.append((siid, piid, value))
        self.state = value
        return [{"code": 0}]


class FakeVacuum:
    def __init__(self, state):
        self.device = FakeDevice(state)


def make_client(state):
    client = XiaomiE10MapV47.__new__(XiaomiE10MapV47)
    client.vacuum = FakeVacuum(state)
    client.privacy_original = None
    client.privacy_temporarily_enabled = False
    return client


# Caso principal detectado por V46: 1 significa subida Cloud deshabilitada.
client = make_client(1)
assert client.enable_map_upload_temporarily() is True
assert client.vacuum.device.state == 0
assert client.vacuum.device.set_calls == [(10, 23, 0)]
assert client.privacy_original == 1
assert client.privacy_temporarily_enabled is True

# Al terminar debe volver exactamente al valor original.
assert client.restore_map_privacy() is True
assert client.vacuum.device.state == 1
assert client.vacuum.device.set_calls[-1] == (10, 23, 1)
assert client.privacy_temporarily_enabled is False

# Si el usuario ya tenía Cloud habilitado, V47 no cambia nada ni programa restore.
already_enabled = make_client(0)
assert already_enabled.enable_map_upload_temporarily() is True
assert already_enabled.vacuum.device.state == 0
assert already_enabled.vacuum.device.set_calls == []
assert already_enabled.privacy_original == 0
assert already_enabled.privacy_temporarily_enabled is False
assert already_enabled.restore_map_privacy() is False

# La nueva app sólo añade la puerta de privacidad sobre la lógica segura de V46.
assert issubclass(app_v47.App, app_v46.App)

print("SMOKE TEST V47 OK: map-privacy 1->0 temporal + restore + preservación de 0")

import base64
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v50
import app_v51
import xiaomi_e10_map_v51 as map_v51_module
from xiaomi_e10_map_v41 import ExhaustiveMapSnapshot
from xiaomi_e10_map_v47 import XiaomiE10MapV47
from xiaomi_e10_map_v51 import XiaomiE10MapV51


# 1) V51 debe volver a la rama segura V47/V45, no a V44 como hizo V50.
assert issubclass(XiaomiE10MapV51, XiaomiE10MapV47)
assert issubclass(app_v51.App, app_v50.App)


# 2) El esquema profundo debe revelar code/message y encontrar URLs bajo claves arbitrarias.
probe = XiaomiE10MapV51.__new__(XiaomiE10MapV51)
probe.session_data = {"user_id": "123456789012", "cuser_id": "987654321098"}
probe.did = "123456789012345678"
response = json.dumps({
    "code": -6,
    "message": "invalid config for fds",
    "unknown": {"signedThing": "https://example.invalid/signed"},
}).encode("utf-8")
diag, candidates, urls = probe._analyze_pro_response(response)
assert diag["app_code"] == -6
assert diag["message"] == "invalid config for fds"
assert "unknown" in diag["top_keys"]
assert diag["url_count"] == 1
assert urls[0][0].startswith("https://")
assert any("unknown.signedThing" in path for path in diag["url_paths"])
assert candidates == []


# 3) Payload base64 bajo una clave no documentada también debe convertirse en candidato.
raw_payload = bytes(range(64))
encoded = base64.b64encode(raw_payload).decode("ascii")
diag2, candidates2, urls2 = probe._analyze_pro_response({
    "code": 0,
    "result": {"cipher_blob": encoded},
})
assert diag2["app_code"] == 0
assert diag2["result_kind"] == "dict"
assert "cipher_blob" in diag2["result_keys"]
assert urls2 == []
assert any(raw == raw_payload for raw, _ in candidates2)


# 4) Guardia crítica: con map_id=0 no se puede ejecutar NINGUNA acción del robot.
class FakeDevice:
    def __init__(self):
        self.calls = []

    def call_action_by(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"code": 0}


class FakeVacuum:
    def __init__(self):
        self.device = FakeDevice()


safe = XiaomiE10MapV51.__new__(XiaomiE10MapV51)
safe.vacuum = FakeVacuum()
safe.privacy_original = None
safe.privacy_temporarily_enabled = False
safe.last_upload_diagnostics = {}
safe.last_v45_upload_diagnostics = {}
safe.active_map_id = types.MethodType(lambda self: (0, []), safe)
safe.map_privacy_state = types.MethodType(lambda self: 0, safe)
result = safe.request_fresh_upload()
assert result["skipped"] is True
assert safe.vacuum.device.calls == []


# 5) Si _pro esconde una URL, load() debe descargarla y probarla antes del fallback.
direct = XiaomiE10MapV51.__new__(XiaomiE10MapV51)
direct.last_v51_diagnostics = {}
direct.last_v50_diagnostics = {}
direct.last_v44_diagnostics = {}
direct.last_key_diagnostics = {}
direct.CLOUD_SLOTS = ("0",)
direct._ordered_key_material = types.MethodType(
    lambda self: ([('WIFI', 'wifi-test')], [('OWNER', 'owner-test')], [('DID', 'did-test')], [('MAC', 'mac-test')]),
    direct,
)
direct._probe_pro_slot = types.MethodType(
    lambda self, slot: ({
        "transport_ok": True,
        "application_ok": True,
        "response_kind": "bytes",
        "parsed_kind": "dict",
        "top_keys": ["code", "mystery"],
        "result_kind": None,
        "result_keys": [],
        "app_code": 0,
        "message": None,
        "url_count": 1,
        "url_paths": ["response.mystery.link"],
        "candidate_count": 0,
        "candidates": [],
        "schema": [],
        "error": None,
    }, [], [("https://example.invalid/blob", "response.mystery.link")]),
    direct,
)


class FakeResponse:
    status_code = 200
    content = b"ciphertext-00000"

    def raise_for_status(self):
        return None


old_get = map_v51_module.requests.get
map_v51_module.requests.get = lambda *args, **kwargs: FakeResponse()


def fake_native(self, raw, wifi, owners, dids, macs, slot, endpoint):
    snap = ExhaustiveMapSnapshot(
        raw_size=len(raw),
        decrypted_size=123,
        raw_prefix_hex=raw[:16].hex(),
        blob_sha256="b" * 64,
        raw_robot=(1.0, 2.0),
        raw_base=(0.0, 0.0),
        raw_path=[(0.0, 0.0), (1.0, 2.0)],
        slot=str(slot),
        endpoint=endpoint,
        wifi_sn_source="wifi-test",
        wifi_sn_length=4,
        owner_source="owner-test",
        did_source="did-test",
        mac_source="mac-test",
        mac_available=True,
    )
    return snap, {"attempts": 1, "unpack_ok": 1, "protobuf_ok": 1, "parse_ok": 1}


direct._decode_native = types.MethodType(fake_native, direct)
direct._decode_xiaomi = types.MethodType(
    lambda self, *args, **kwargs: (_ for _ in ()).throw(AssertionError("IJAI ya debía haber ganado")),
    direct,
)
try:
    selected = direct.load()
finally:
    map_v51_module.requests.get = old_get

assert selected.endpoint == "get_interim_file_url_pro/v51"
assert direct.last_v51_diagnostics["success"] is True
assert direct.last_v51_diagnostics["winner_decoder"] == "ijai"
assert direct.last_v51_diagnostics["fallback_classic"] is False
assert direct.last_v51_diagnostics["pro_slots"]["0"]["downloads"][0]["bytes"] == len(FakeResponse.content)

print("SMOKE TEST V51 OK: herencia segura + esquema _pro profundo + descarga URL oculta")

import ast
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for path in (
    SRC / "chatgpt_bridge.py",
    SRC / "app_v124.py",
    SRC / "main_v124.py",
):
    ast.parse(path.read_text(encoding="utf-8"))

import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_v124
import chatgpt_bridge

assert issubclass(app_v124.App, app_v124.app_v123.App)

# El servidor se construye realmente para detectar cambios de API del SDK MCP,
# pero no se abre ningún puerto durante el smoke.
server = chatgpt_bridge.AspiradoraMCPServer(
    snapshot_path=Path(tempfile.gettempdir()) / "aspiradora-v124-smoke.json"
)
mcp = server._build()
assert mcp is not None

cmd = chatgpt_bridge.TunnelClientManager.build_command(
    Path("tunnel-client.exe"),
    "tunnel_" + ("a" * 32),
    "http://127.0.0.1:8765/mcp",
)
joined = " ".join(cmd)
assert "--control-plane.tunnel-id=tunnel_" in joined
assert "--mcp.server-url=http://127.0.0.1:8765/mcp" in joined
assert "--control-plane.api-key=env:CONTROL_PLANE_API_KEY" in joined
assert "sk-" not in joined

safe = chatgpt_bridge.sanitize({
    "token": "0123456789abcdef",
    "ip": "192.168.1.100",
    "diagnostic": "api sk-testsecret123456789 and 192.168.1.2",
})
assert safe["token"] == "[redacted]"
assert safe["ip"] == "[redacted]"
assert "sk-testsecret" not in safe["diagnostic"]
assert "192.168.1.2" not in safe["diagnostic"]

source = (SRC / "app_v124.py").read_text(encoding="utf-8")
assert "Conectar ChatGPT" in source
assert "SOLO LECTURA" in source
assert "get_full_diagnostic" in (SRC / "chatgpt_bridge.py").read_text(encoding="utf-8")
assert "clean_point" not in (SRC / "chatgpt_bridge.py").read_text(encoding="utf-8")
assert "vacuum.stop" not in (SRC / "chatgpt_bridge.py").read_text(encoding="utf-8")

print(
    "SMOKE TEST V124 OK: MCP read-only + DPAPI + Secure MCP Tunnel "
    "sin credenciales en args ni acciones físicas"
)

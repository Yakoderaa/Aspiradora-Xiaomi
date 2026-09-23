from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]

build = (ROOT / "build.ps1").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
main_current = (ROOT / "src/main_current.py").read_text(encoding="utf-8")
meta = json.loads((ROOT / "release_meta.json").read_text(encoding="utf-8"))

# Contrato estable: el build NO cambia de entry point con cada Vxxx.
entry_lines = [
    line.strip()
    for line in build.splitlines()
    if re.fullmatch(r"src\\main_[A-Za-z0-9_]+\.py", line.strip())
]
assert entry_lines == ["src\\main_current.py"], entry_lines
assert 'Invoke-PythonChecked "scripts\\smoke_test_release_contract.py"' in build

# El wrapper actual puede cambiar qué app importa, pero su nombre permanece fijo.
assert "def main():" in main_current
assert "--packaging-smoke-test" in main_current
assert ".App().mainloop()" in main_current

# El workflow obtiene generación/notas desde metadata y no se edita por versión.
assert "release_meta.json" in workflow
assert "$generation" in workflow
assert "$meta.notes" in workflow
assert "--title" in workflow
assert re.fullmatch(r"V\d+-IA", str(meta["generation"])), meta
assert isinstance(meta.get("notes"), str) and len(meta["notes"]) >= 40

# Protección contra volver al antipatrón: nada de main_vNNN como entry real.
for line in entry_lines:
    assert not re.fullmatch(r"src\\main_v\d+\.py", line), line

print(f"RELEASE CONTRACT OK: {meta['generation']} · entry estable main_current.py")

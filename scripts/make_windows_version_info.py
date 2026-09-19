import os
import re
from pathlib import Path


def version_tuple(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text or ""))[:4]]
    nums += [0] * (4 - len(nums))
    return tuple(nums[:4])


version = os.environ.get("APP_VERSION", "0.1.0")
parts = version_tuple(version)
out = Path("build") / "aspiradora_version_info.txt"
out.parent.mkdir(parents=True, exist_ok=True)

content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={parts},
    prodvers={parts},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'Yakoderaa'),
          StringStruct(u'FileDescription', u'Aspiradora'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'Aspiradora'),
          StringStruct(u'LegalCopyright', u'Yakoderaa'),
          StringStruct(u'OriginalFilename', u'Aspiradora Xiaomi.exe'),
          StringStruct(u'ProductName', u'Aspiradora'),
          StringStruct(u'ProductVersion', u'{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
out.write_text(content, encoding="utf-8")
print(out)

$ErrorActionPreference = "Stop"

if (-not $env:APP_VERSION) {
    $env:APP_VERSION = "0.1.0"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller==6.22.3

"VERSION = `"$($env:APP_VERSION)`"" | Set-Content -Encoding UTF8 src\_build_version.py

# Genera el icono multi-resolución desde el icono de Xiaomi Home.
python scripts\make_mihome_icon.py

# Helper independiente: sigue vivo cuando la app principal se cierra para
# instalar la actualización y volver a abrir la versión nueva.
pyinstaller --noconfirm --clean --windowed --onefile `
    --name "Aspiradora Xiaomi Updater" `
    --icon "assets\mi_home.ico" `
    src\update_helper.py

pyinstaller --noconfirm --clean --windowed --onedir `
    --name "Aspiradora Xiaomi" `
    --icon "assets\mi_home.ico" `
    --collect-all miio `
    --collect-all micloud `
    --collect-all PIL `
    src\app_v16.py

Copy-Item `
    "dist\Aspiradora Xiaomi Updater.exe" `
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe" `
    -Force

$pf86 = ${env:ProgramFiles(x86)}
$inno = @(
    "$pf86\Inno Setup 7\ISCC.exe",
    "$pf86\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $inno) {
    throw "No se encontró Inno Setup. Instalalo y volvé a ejecutar build.ps1."
}

& $inno installer\AspiradoraXiaomi.iss

$installer = "installer_output\Aspiradora-Xiaomi-Setup.exe"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  Aspiradora-Xiaomi-Setup.exe" | Set-Content -Encoding ASCII "$installer.sha256"
Write-Host "Instalador generado: $installer"

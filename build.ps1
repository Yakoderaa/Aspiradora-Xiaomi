$ErrorActionPreference = "Stop"

if (-not $env:APP_VERSION) {
    $env:APP_VERSION = "0.1.0"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller==6.22.3

"VERSION = `"$($env:APP_VERSION)`"" | Set-Content -Encoding UTF8 src\_build_version.py

pyinstaller --noconfirm --clean --windowed --onedir `
    --name "Aspiradora Xiaomi" `
    --collect-all miio `
    --collect-all micloud `
    --collect-all PIL `
    src\app_v2.py

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

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

# Antes de empaquetar: sintaxis/imports + persistencia de mapas/planes/backups.
python -m compileall -q src scripts
python scripts\smoke_test.py

# Helper independiente de actualizaciones. Incluye los recursos para que su
# ventana Tk use el mismo icono que el ejecutable/instalador.
pyinstaller --noconfirm --clean --windowed --onefile `
    --name "Aspiradora Xiaomi Updater" `
    --icon "assets\mi_home.ico" `
    --add-data "assets\mi_home.ico;assets" `
    --add-data "assets\mi_home.png;assets" `
    src\update_helper.py

# Agente de programaciones. Corre en segundo plano al iniciar Windows.
pyinstaller --noconfirm --clean --windowed --onefile `
    --name "Aspiradora Xiaomi Scheduler" `
    --icon "assets\mi_home.ico" `
    --collect-all miio `
    src\scheduler_agent.py

# Aplicación principal: icono en EXE + recursos para Tk/barra de tareas/bandeja.
pyinstaller --noconfirm --clean --windowed --onedir `
    --name "Aspiradora Xiaomi" `
    --icon "assets\mi_home.ico" `
    --add-data "assets\mi_home.ico;assets" `
    --add-data "assets\mi_home.png;assets" `
    --collect-all miio `
    --collect-all micloud `
    --collect-all PIL `
    --collect-all pystray `
    src\app_v19.py

Copy-Item `
    "dist\Aspiradora Xiaomi Updater.exe" `
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe" `
    -Force

Copy-Item `
    "dist\Aspiradora Xiaomi Scheduler.exe" `
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe" `
    -Force

# Verificación post-build de los tres ejecutables y recursos de icono.
$required = @(
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe",
    "dist\Aspiradora Xiaomi\_internal\assets\mi_home.ico",
    "dist\Aspiradora Xiaomi\_internal\assets\mi_home.png"
)
foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Falta un archivo requerido del build: $path"
    }
}

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
if (-not (Test-Path $installer)) {
    throw "Inno Setup no generó el instalador esperado."
}
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  Aspiradora-Xiaomi-Setup.exe" | Set-Content -Encoding ASCII "$installer.sha256"
Write-Host "Instalador generado: $installer"

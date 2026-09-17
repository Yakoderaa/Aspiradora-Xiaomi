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

# Verificaciones antes de empaquetar.
python -m compileall -q src scripts
python scripts\smoke_test.py

# Helper independiente de actualizaciones, con el mismo icono de Mi Home.
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

# Aplicación principal: icono en EXE + Tk + barra de tareas + bandeja.
pyinstaller --noconfirm --clean --windowed --onedir `
    --name "Aspiradora Xiaomi" `
    --icon "assets\mi_home.ico" `
    --add-data "assets\mi_home.ico;assets" `
    --add-data "assets\mi_home.png;assets" `
    --collect-all miio `
    --collect-all micloud `
    --collect-all PIL `
    --collect-all pystray `
    src\app_v21.py

Copy-Item `
    "dist\Aspiradora Xiaomi Updater.exe" `
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe" `
    -Force

Copy-Item `
    "dist\Aspiradora Xiaomi Scheduler.exe" `
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe" `
    -Force

# Verificación post-build de ejecutables y recursos de icono.
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

# Comprueba que Windows puede extraer un icono válido de cada ejecutable.
Add-Type -AssemblyName System.Drawing
$iconTargets = @(
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe"
)
foreach ($target in $iconTargets) {
    $resolved = (Resolve-Path $target).Path
    $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($resolved)
    if ($null -eq $icon -or $icon.Width -lt 16 -or $icon.Height -lt 16) {
        throw "Windows no pudo extraer un icono válido de: $target"
    }
    $icon.Dispose()
}

# Smoke runtime: la app y el agente deben seguir vivos unos segundos. Esto
# captura errores de importación/arranque que compileall y PyInstaller no ven.
$appExe = (Resolve-Path "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe").Path
$appProcess = Start-Process -FilePath $appExe -ArgumentList "--tray" -PassThru
Start-Sleep -Seconds 5
$appProcess.Refresh()
if ($appProcess.HasExited) {
    throw "La aplicación empaquetada se cerró durante el smoke test de arranque. Código: $($appProcess.ExitCode)"
}
Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue

$schedulerExe = (Resolve-Path "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe").Path
$schedulerProcess = Start-Process -FilePath $schedulerExe -PassThru
Start-Sleep -Seconds 3
$schedulerProcess.Refresh()
if ($schedulerProcess.HasExited) {
    throw "El programador se cerró durante el smoke test de arranque. Código: $($schedulerProcess.ExitCode)"
}
Stop-Process -Id $schedulerProcess.Id -Force -ErrorAction SilentlyContinue

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
$installerIcon = [System.Drawing.Icon]::ExtractAssociatedIcon((Resolve-Path $installer).Path)
if ($null -eq $installerIcon -or $installerIcon.Width -lt 16) {
    throw "El instalador no contiene un icono válido."
}
$installerIcon.Dispose()

$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  Aspiradora-Xiaomi-Setup.exe" | Set-Content -Encoding ASCII "$installer.sha256"
Write-Host "Instalador generado: $installer"

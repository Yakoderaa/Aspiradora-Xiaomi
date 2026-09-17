$ErrorActionPreference = "Stop"

if (-not $env:APP_VERSION) {
    $env:APP_VERSION = "0.1.0"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller==6.22.3

"VERSION = `"$($env:APP_VERSION)`"" | Set-Content -Encoding UTF8 src\_build_version.py

python scripts\make_mihome_icon.py
python scripts\fetch_e10_product_image.py

python -m compileall -q src scripts
python scripts\smoke_test.py
python scripts\smoke_test_v24.py
python scripts\smoke_test_v25.py
python scripts\smoke_test_v26.py
python scripts\smoke_test_v27.py
python scripts\smoke_test_v28.py
python scripts\smoke_test_v29.py
python scripts\smoke_test_v30.py
python scripts\smoke_test_v31.py
python scripts\smoke_test_v32.py
python scripts\smoke_test_v33.py
python scripts\smoke_test_v34.py
python scripts\smoke_test_v35.py
python scripts\smoke_test_v36.py
python scripts\smoke_test_v37.py
python scripts\smoke_test_v38.py
python scripts\smoke_test_v39.py
python scripts\smoke_test_v40.py
python scripts\smoke_test_v41.py
python scripts\smoke_test_v41_all.py
python scripts\smoke_test_v42.py
python scripts\smoke_test_v43.py
python scripts\smoke_test_v44.py
python scripts\smoke_test_v45.py
python scripts\smoke_test_v46.py
python scripts\smoke_test_v47.py
python scripts\smoke_test_v48.py
python scripts\smoke_test_v49.py
python scripts\smoke_test_v50.py
python scripts\smoke_test_v51.py
python scripts\smoke_test_v52.py
python scripts\smoke_test_v53.py
python scripts\smoke_test_v54.py
python scripts\smoke_test_v55.py

pyinstaller --noconfirm --clean --windowed --onefile `
    --name "Aspiradora Xiaomi Updater" `
    --icon "assets\mi_home.ico" `
    --add-data "assets\mi_home.ico;assets" `
    --add-data "assets\mi_home.png;assets" `
    src\update_helper.py

pyinstaller --noconfirm --clean --windowed --onefile `
    --name "Aspiradora Xiaomi Scheduler" `
    --icon "assets\mi_home.ico" `
    --collect-all miio `
    src\scheduler_agent.py

pyinstaller --noconfirm --clean --windowed --onedir `
    --name "Aspiradora Xiaomi" `
    --icon "assets\mi_home.ico" `
    --add-data "assets\mi_home.ico;assets" `
    --add-data "assets\mi_home.png;assets" `
    --add-data "assets\xiaomi_robot_vacuum_e10.jpg;assets" `
    --collect-all miio `
    --collect-all micloud `
    --collect-all Crypto `
    --collect-all PIL `
    --collect-all pystray `
    --collect-all google.protobuf `
    --collect-all vacuum_map_parser_base `
    --collect-all vacuum_map_parser_xiaomi `
    --collect-all vacuum_map_parser_ijai `
    src\main_v55.py

Copy-Item "dist\Aspiradora Xiaomi Updater.exe" "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe" -Force
Copy-Item "dist\Aspiradora Xiaomi Scheduler.exe" "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe" -Force

$required = @(
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe",
    "dist\Aspiradora Xiaomi\_internal\assets\mi_home.ico",
    "dist\Aspiradora Xiaomi\_internal\assets\mi_home.png",
    "dist\Aspiradora Xiaomi\_internal\assets\xiaomi_robot_vacuum_e10.jpg"
)
foreach ($path in $required) {
    if (-not (Test-Path $path)) { throw "Falta un archivo requerido del build: $path" }
}

Add-Type -AssemblyName System.Drawing
foreach ($target in @(
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Updater.exe",
    "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe"
)) {
    $icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Resolve-Path $target).Path)
    if ($null -eq $icon -or $icon.Width -lt 16 -or $icon.Height -lt 16) { throw "Windows no pudo extraer un icono válido de: $target" }
    $icon.Dispose()
}

$appExe = (Resolve-Path "dist\Aspiradora Xiaomi\Aspiradora Xiaomi.exe").Path

# Prueba de imports DENTRO del ejecutable empaquetado. Una excepción de
# PyInstaller abre un diálogo y deja el proceso vivo; por eso exigimos que este
# modo de prueba termine por sí mismo con código 0 en menos de 15 segundos.
$probeProcess = Start-Process -FilePath $appExe -ArgumentList "--packaging-smoke-test" -PassThru
$probeExited = $probeProcess.WaitForExit(15000)
if (-not $probeExited) {
    Stop-Process -Id $probeProcess.Id -Force -ErrorAction SilentlyContinue
    throw "El EXE no superó el self-test de imports empaquetados (posible diálogo de excepción o dependencia faltante)."
}
if ($probeProcess.ExitCode -ne 0) {
    throw "El self-test del EXE terminó con código $($probeProcess.ExitCode)."
}

$appProcess = Start-Process -FilePath $appExe -ArgumentList "--tray" -PassThru
Start-Sleep -Seconds 6
$appProcess.Refresh()
if ($appProcess.HasExited) { throw "La aplicación v55 se cerró durante el smoke test de arranque. Código: $($appProcess.ExitCode)" }
Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue

$schedulerExe = (Resolve-Path "dist\Aspiradora Xiaomi\Aspiradora Xiaomi Scheduler.exe").Path
$schedulerProcess = Start-Process -FilePath $schedulerExe -PassThru
Start-Sleep -Seconds 3
$schedulerProcess.Refresh()
if ($schedulerProcess.HasExited) { throw "El programador se cerró durante el smoke test de arranque. Código: $($schedulerProcess.ExitCode)" }
Stop-Process -Id $schedulerProcess.Id -Force -ErrorAction SilentlyContinue

$pf86 = ${env:ProgramFiles(x86)}
$inno = @("$pf86\Inno Setup 7\ISCC.exe", "$pf86\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $inno) { throw "No se encontró Inno Setup. Instalalo y volvé a ejecutar build.ps1." }

& $inno installer\AspiradoraXiaomi.iss
$installer = "installer_output\Aspiradora-Xiaomi-Setup.exe"
if (-not (Test-Path $installer)) { throw "Inno Setup no generó el instalador esperado." }
$installerIcon = [System.Drawing.Icon]::ExtractAssociatedIcon((Resolve-Path $installer).Path)
if ($null -eq $installerIcon -or $installerIcon.Width -lt 16) { throw "El instalador no contiene un icono válido." }
$installerIcon.Dispose()

$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  Aspiradora-Xiaomi-Setup.exe" | Set-Content -Encoding ASCII "$installer.sha256"
Write-Host "Instalador generado: $installer"

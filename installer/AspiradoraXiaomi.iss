#define MyAppName "Aspiradora Xiaomi"
#define MyAppPublisher "Yakoderaa"
#define MyAppURL "https://github.com/Yakoderaa/Aspiradora-Xiaomi"
#define MyAppExeName "Aspiradora Xiaomi.exe"
#define MySchedulerExeName "Aspiradora Xiaomi Scheduler.exe"
#define MyAppVersion GetEnv("APP_VERSION")

[Setup]
AppId={{A6DCA7D0-FF5E-4D83-B84B-9E4F22D4F610}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\Aspiradora Xiaomi
DefaultGroupName=Aspiradora Xiaomi
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=Aspiradora-Xiaomi-Setup
SetupIconFile=..\assets\mi_home.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
; El helper de actualización relanza explícitamente la app. Evitamos que Inno
; cree una segunda instancia o reabra una ventana antes de restaurar geometría.
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Control de Xiaomi Robot Vacuum E10 para Windows

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\dist\Aspiradora Xiaomi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Aspiradora Xiaomi"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\Aspiradora Xiaomi"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked



[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Cierra procesos viejos antes de reemplazar archivos. V157 vuelve a registrar
    únicamente el Scheduler liviano después de instalar. }
  Exec(
    ExpandConstant('{sys}\\taskkill.exe'),
    '/IM "{#MySchedulerExeName}" /F',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Exec(
    ExpandConstant('{sys}\\taskkill.exe'),
    '/IM "{#MyAppExeName}" /F',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  { Se limpia primero cualquier registro viejo; [Registry] instala el nuevo. }
  RegDeleteValue(
    HKCU,
    'Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    'AspiradoraXiaomiScheduler'
  );
  RegDeleteValue(
    HKCU,
    'Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    'Aspiradora Xiaomi'
  );

  Result := '';
end;

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AspiradoraXiaomiScheduler"; ValueData: """{app}\{#MySchedulerExeName}"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MySchedulerExeName}"; Description: "Iniciar programador de Aspiradora Xiaomi"; Flags: nowait runhidden

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM ""{#MySchedulerExeName}"" /F"; Flags: runhidden; RunOnceId: "StopScheduler"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""Aspiradora Xiaomi"" /f"; Flags: runhidden; RunOnceId: "RemoveAppAutostart"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""AspiradoraXiaomiScheduler"" /f"; Flags: runhidden; RunOnceId: "RemoveSchedulerAutostart"

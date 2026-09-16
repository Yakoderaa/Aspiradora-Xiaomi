#define MyAppName "Aspiradora Xiaomi"
#define MyAppPublisher "Yakoderaa"
#define MyAppURL "https://github.com/Yakoderaa/Aspiradora-Xiaomi"
#define MyAppExeName "Aspiradora Xiaomi.exe"
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
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
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

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Aspiradora Xiaomi"; Flags: nowait postinstall skipifsilent

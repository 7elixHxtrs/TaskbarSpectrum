; Instalador de Taskbar Spectrum (Inno Setup 6)
#define MyAppName "Taskbar Spectrum"
#define MyAppVersion "1.0.0"
#define MyAppExe "TaskbarSpectrum.exe"

[Setup]
AppId={{B3F1C2A4-6D7E-4A59-9C1B-5E2F8A7D3C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=7elixHxtrs
AppPublisherURL=https://github.com/7elixHxtrs
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=TaskbarSpectrum-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Si el programa esta abierto, el instalador/desinstalador pide cerrarlo
AppMutex=TaskbarSpectrumSingleton
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Iniciar {#MyAppName} al encender el PC"; GroupDescription: "Opciones:"
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Opciones:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Misma clave que usa el programa en su opcion "Iniciar con Windows"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TaskbarSpectrum"; ValueData: """{app}\{#MyAppExe}"""; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Parameters: "--installed"; Description: "Abrir {#MyAppName} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\TaskbarSpectrum"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Quita el inicio automatico aunque el usuario lo haya activado desde el programa
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'TaskbarSpectrum');
end;

; Inno Setup script: wraps the PyInstaller onedir build into Setup.exe.
;
;   iscc /DAppVersion=0.1.0 packaging\lotoconfere.iss
;
; Per-user install by default (PrivilegesRequired=lowest): the build is unsigned
; by decision, and asking an unsigned installer for administrator rights turns
; one SmartScreen warning into two prompts for the same non-profit app.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "LotoConfere"
#define AppExeName "LotoConfere.exe"
#define AppPublisher "Matheus Tiengo"
#define AppUrl "https://github.com/mtiengo/lotoconfere"

[Setup]
AppId={{B3C6F4E2-6A2E-4D7E-9C4B-2F7A1D5E8C31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icons\lotoconfere.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na area de trabalho"; \
  GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir o {#AppName}"; \
  Flags: nowait postinstall skipifsilent

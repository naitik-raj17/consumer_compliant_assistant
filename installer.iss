#define AppName "ConsumerGuard"
#define AppVersion "1.0.0"

[Setup]
AppId={{6F1E3C52-8B7A-4D3E-9C21-5A0B7E2D4C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ConsumerGuard
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=ConsumerGuard_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ConsumerGuard.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\ConsumerGuard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ConsumerGuard.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ConsumerGuard.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ConsumerGuard.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

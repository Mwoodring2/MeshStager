; Inno Setup script — MeshStager (PyInstaller onedir payload from dist\MeshStager).
; Requires Inno Setup 6.3+. Compile from the repo root via scripts\build_installer_windows.ps1.
;
; This is a packaging wrapper only: it installs the frozen bundle exactly as PyInstaller built it
; and changes no application behavior. The build is NOT produced here — run the portable build
; first (scripts\build_shareable_windows.py), which verifies the bundle's dependencies.
;
; RC3 change: per-user installation. PrivilegesRequired=lowest means no UAC prompt and no
; administrator rights, and {autopf} resolves to {localappdata}\Programs, so the app lands in
; %LOCALAPPDATA%\Programs\MeshStager. Artists can install without IT involvement.

#define MyAppName "MeshStager"
#define MyAppVersion "0.1.0-rc3"
#define MyAppPublisher "Woodring Tools"
#define MyAppUrl "https://github.com/Mwoodring2/MeshStager"
#define MyAppExeName "MeshStager.exe"

; Payload root (relative to this .iss in installer\) — unchanged app layout from PyInstaller
#define DistPayload "..\dist\MeshStager"
#define AppIcon "..\assets\icons\MeshStager_icon.ico"

[Setup]
; Stable GUID for UpgradeCode-style identity across builds of this product line (do not reuse for
; other apps). Kept from the RC1 installer so Windows still correlates installs and uninstalls.
AppId={{B5CF77B4-9884-4964-A6BC-50E6A5327817}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}
AppUpdatesURL={#MyAppUrl}

; Per-user install: no administrator rights, no UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Keep the tester's path short: welcome -> license -> shortcut option -> install -> launch.
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE

OutputDir=..\release
OutputBaseFilename={#MyAppName}_v{#MyAppVersion}_Setup
SetupIconFile={#AppIcon}

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Name and RC version in Add/Remove Programs, with the app's own icon.
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}

; Let Restart Manager close a running MeshStager instead of failing on locked files during an
; upgrade or reinstall.
CloseApplications=yes
RestartApplications=no

; Numeric version stamp for installer / Add/Remove Programs (hyphenated AppVersion stays
; human-readable). Fourth field tracks the RC number; APP_VERSION in the app is untouched.
VersionInfoVersion=0.1.0.3
VersionInfoTextVersion=v{#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductTextVersion=v{#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Entire frozen bundle (MeshStager.exe plus the _internal\ runtime directory). _internal is
; required at runtime; testers never need to open it, and nothing here creates shortcuts into it.
Source: "{#DistPayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the install directory only if nothing unexpected is left in it.
;
; Deliberately absent: any entry under %LOCALAPPDATA%\MeshStager or %LOCALAPPDATA%\Roundup.
; Uninstalling removes the program, not the user's settings, caches, thumbnails, or bridge
; output — same as most desktop apps, and it keeps the legacy-Roundup migration intact if the
; tester reinstalls later.
Type: dirifempty; Name: "{app}"

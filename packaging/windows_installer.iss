; Inno Setup script for nlmclean - wraps the self-contained PyInstaller bundle
; (dist\nlmclean) into a Windows installer. No system dependencies are installed:
; Python, all libraries, and ffmpeg are already inside the bundle.
;
; Build:
;   1. pyinstaller packaging/nlmclean.spec --noconfirm      (produces dist\nlmclean)
;   2. ISCC packaging\windows_installer.iss                 (produces dist\nlmclean-v0.1.0-windows-setup.exe)

#define MyAppName "nlmclean"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "alpinist-GH"
#define MyAppURL "https://github.com/alpinist-GH/notebooklm-watermark-remover"
#define MyAppExeName "nlmclean.exe"

[Setup]
; AppId uniquely identifies this app for upgrades/uninstall - do not change it between releases.
AppId={{B7E4D2A1-9C3F-4E8B-A6D5-1F2C3B4A5E6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=nlmclean-v{#MyAppVersion}-windows-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The bundle is 64-bit; only install on x64 Windows and use the 64-bit Program Files.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Recursively pack the entire PyInstaller one-folder bundle.
Source: "..\dist\nlmclean\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

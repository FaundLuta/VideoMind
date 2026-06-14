; VideoMind Inno Setup Script

#define AppName "VideoMind"
#define AppVersion "1.0"
#define AppPublisher "Somto"
#define AppExeName "VideoMind.exe"

[Setup]
AppId={{A8B1C2D3-E4F5-4G6H-8I9J-K0L1M2N3O4P5}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=c:\Users\SOMTO\Desktop\projects\video summariser\installer
OutputBaseFilename=VideoMind_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Source is the folder created by PyInstaller
Source: "C:\Users\SOMTO\Desktop\projects\video summariser\dist\VideoMind\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Ensure ffmpeg.exe and ffprobe.exe are physically inside the dist\VideoMind folder before compiling Inno Setup.

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Optional: You could add a check here to ensure the user has enough disk space, 
// as Whisper and its dependencies can be quite large.

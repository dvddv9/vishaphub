; Per-user installer: no administrator rights, nothing outside the user's own folders.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "build\app"
#endif

[Setup]
AppId={{6B0E5D5A-4D0B-4E58-9E57-5F1B6C4D9A11}
AppName=VishapHub
AppVersion={#AppVersion}
AppPublisher=Vishap
DefaultDirName={autopf}\VishapHub
DefaultGroupName=VishapHub
PrivilegesRequired=lowest
OutputBaseFilename=VishapHub-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=VishapHub
DisableProgramGroupPage=yes

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{group}\VishapHub"; Filename: "{app}\start-hub.cmd"; WorkingDir: "{app}"
Name: "{group}\VishapHub settings"; Filename: "{app}\setup.cmd"; WorkingDir: "{app}"
Name: "{group}\Uninstall VishapHub"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\setup.cmd"; Description: "Choose the model and privacy settings now"; Flags: postinstall nowait skipifsilent
Filename: "{app}\start-hub.cmd"; Description: "Start VishapHub"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Settings and runs live in %USERPROFILE%\.vishaphub and are left alone on purpose: they hold the model key and history.
Type: filesandordirs; Name: "{app}\python"

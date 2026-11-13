#ifndef AppSourceDir
  #error AppSourceDir must name the verified assembled product.
#endif
#ifndef ReleaseVersion
  #error ReleaseVersion is required.
#endif
#ifndef ReleaseOutputDir
  #error ReleaseOutputDir is required.
#endif

[Setup]
AppId={{B9E45522-9FA5-4748-AFE1-E08804D1A578}
AppName=OpenPyCharm
AppVersion={#ReleaseVersion}
AppPublisher=OpenPyCharm contributors
AppPublisherURL=https://github.com/shubolab/openpycharm
AppSupportURL=https://github.com/shubolab/openpycharm/issues
DefaultDirName={localappdata}\Programs\OpenPyCharm
DefaultGroupName=OpenPyCharm
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#ReleaseOutputDir}
OutputBaseFilename=OpenPyCharm-{#ReleaseVersion}-windows-x64-setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=OpenPyCharm
UninstallDisplayIcon={app}\bin\pycharm64.exe
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "associatepy"; Description: "Associate .py files with OpenPyCharm"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\OpenPyCharm"; Filename: "{app}\bin\pycharm64.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\OpenPyCharm"; Filename: "{app}\bin\pycharm64.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Register as an available editor without overwriting the user's current .py default.
Root: HKCU; Subkey: "Software\Classes\.py\OpenWithProgids"; ValueType: string; ValueName: "OpenPyCharm.Python"; ValueData: ""; Tasks: associatepy; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\OpenPyCharm.Python"; ValueType: string; ValueData: "Python source file"; Tasks: associatepy; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\OpenPyCharm.Python\DefaultIcon"; ValueType: string; ValueData: "{app}\bin\pycharm64.exe,0"; Tasks: associatepy
Root: HKCU; Subkey: "Software\Classes\OpenPyCharm.Python\shell\open\command"; ValueType: string; ValueData: """{app}\bin\pycharm64.exe"" ""%1"""; Tasks: associatepy

[Run]
Filename: "{app}\bin\pycharm64.exe"; Description: "Launch OpenPyCharm"; Flags: nowait postinstall skipifsilent

[Setup]
AppName=AditivaFlow Hub
AppVersion=1.2.0
DefaultDirName={autopf}\AditivaFlow Hub
DefaultGroupName=AditivaFlow Hub
OutputDir=dist
OutputBaseFilename=AditivaFlowHub-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\AditivaFlowHub.exe
SetupIconFile=favicon.ico
WizardStyle=modern

[Files]
Source: "dist\AditivaFlowHub.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\AditivaFlow Hub"; Filename: "{app}\AditivaFlowHub.exe"
Name: "{autodesktop}\AditivaFlow Hub"; Filename: "{app}\AditivaFlowHub.exe"; Tasks: desktopicon
Name: "{userstartup}\AditivaFlow Hub"; Filename: "{app}\AditivaFlowHub.exe"; Tasks: startupicon

[Tasks]
Name: "desktopicon"; Description: "Criar um icone na Area de Trabalho"; GroupDescription: "Atalhos:"
Name: "startupicon"; Description: "Iniciar automaticamente com o Windows"; GroupDescription: "Inicializacao:"

[Run]
Filename: "{app}\AditivaFlowHub.exe"; Description: "Iniciar AditivaFlow Hub"; Flags: nowait postinstall skipifsilent

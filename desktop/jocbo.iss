; 우리의 족보 - 설치 파일(jocbo-setup.exe)을 만듭니다.
; desktop\build.py 로 build\app 을 먼저 만든 뒤 ISCC desktop\jocbo.iss 로 엮습니다.
; 관리자 권한 없이 이 사용자에게만 설치합니다. 족보 데이터는 %LocalAppData%\jocbo 에
; 따로 있어 다시 설치하거나 지워도 남습니다.

#define AppVersion GetEnv("JOCBO_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{681C7776-0B61-4FC0-BB1E-478ED4C8CE0F}}
AppName=우리의 족보
AppVersion={#AppVersion}
AppPublisher=kimheunghan
AppPublisherURL=https://github.com/kimheunghan/jocbo
DefaultDirName={localappdata}\Programs\jocbo
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\build
OutputBaseFilename=jocbo-setup
SetupIconFile=jocbo.ico
UninstallDisplayIcon={app}\jocbo.ico
UninstallDisplayName=우리의 족보
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"

[InstallDelete]
; 새 판으로 덮을 때 옛 판에만 있던 파일이 남지 않게 합니다.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\frontend"
Type: filesandordirs; Name: "{app}\db"

[Files]
Source: "..\build\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\우리의 족보"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jocbo.ico"
Name: "{autodesktop}\우리의 족보"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jocbo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; Description: "우리의 족보 실행"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; 프로그램 폴더만 지웁니다. 족보 데이터(%LocalAppData%\jocbo)는 남습니다.
Type: filesandordirs; Name: "{app}"

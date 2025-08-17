; Inno Setup Script for Remote-Controls
; 打包包含：RC-GUI.exe、RC-main.exe、RC-tray.exe、config.json、logs 目录
; 生成一个离线安装包，安装到 Program Files（需要管理员权限）

#define MyAppName "Remote Controls"
#define MyAppVersion "2.2.3"
#define MyAppPublisher "chen6019"
#define MyAppURL "https://github.com/chen6019/Remote-Controls"
#define MyAppExeName "RC-tray.exe"

[Setup]
AppId={{A9F7F8E7-8A1F-4C4D-8CF1-6B9E0D0B7A23}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={pf}\Remote-Controls
DefaultGroupName=Remote Controls
DisableDirPage=no
DisableProgramGroupPage=no
OutputBaseFilename=Remote-Controls-Installer-{#MyAppVersion}
OutputDir=..\dist\installer
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
WizardStyle=modern
LicenseFile=..\LICENSE
; 使用自签或正式证书签名安装包/卸载程序，注意本机需可调用 signtool.exe（建议将 Windows SDK 的 signtool 加入 PATH）
; 如未在 PATH，可将 signtool.exe 的完整路径替换下行的 "signtool.exe"
SignTool=ms; "signtool.exe" sign /fd sha256 /f "..\installer\rc_codesign.pfx" /p " " /tr http://timestamp.digicert.com /td sha256 $f  //#gitignore
SignedUninstaller=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Dirs]
; 确保安装时创建 logs 目录（即使源中为空）
Name: "{app}\logs"; Flags: uninsalwaysuninstall

[Files]
; 注意：以下源路径默认指向项目根的 dist 目录；请在构建 PyInstaller 后确认路径
Source: "..\dist\RC-GUI.exe"; DestDir: "{app}"; Flags: ignoreversion; SignTool=ms
Source: "..\dist\RC-main.exe"; DestDir: "{app}"; Flags: ignoreversion; SignTool=ms
Source: "..\dist\RC-tray.exe"; DestDir: "{app}"; Flags: ignoreversion; SignTool=ms
; 配置文件：如需自定义，替换项目根的 config.json 再编译安装包
Source: "..\config.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
; logs 目录中已有的文件（可选）；若不存在将仅创建空目录
; Source: "..\logs\*"; DestDir: "{app}\logs"; Flags: ignoreversion recurses createallsubdirs; Excludes: "*.log" 

[Icons]
; 开始菜单
Name: "{group}\远程控制托盘"; Filename: "{app}\RC-tray.exe"; WorkingDir: "{app}"
Name: "{group}\主程序"; Filename: "{app}\RC-main.exe"; WorkingDir: "{app}"
Name: "{group}\配置界面"; Filename: "{app}\RC-GUI.exe"; WorkingDir: "{app}"
; 桌面快捷方式（可选任务）
Name: "{commondesktop}\远程控制托盘"; Filename: "{app}\RC-tray.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; GroupDescription: "其他选项"; Flags: unchecked
Name: autoruntray; Description: "安装完成后启动托盘程序"; GroupDescription: "其他选项"; Flags: checkedonce

[Run]
; 安装完成后可选启动托盘（不提升权限，由程序自行处理 UAC）
Filename: "{app}\RC-tray.exe"; Description: "启动托盘程序"; Flags: nowait postinstall skipifsilent; Tasks: autoruntray

[UninstallDelete]
; 卸载时保留日志文件，仅当目录为空时删除目录
Type: dirifempty; Name: "{app}\logs"

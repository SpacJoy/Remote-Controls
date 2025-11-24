;用于遥控器的 Inno 设置脚本
;包包括：RC-GUI.exe、RC-main.exe、RC-tray.exe、config.json、日志目录
;生成脱机安装程序，安装到 Program Files（需要管理员权限）

; 通过命令行参数或临时文件动态读取版本信息
#ifndef MyAppVersion
  #if FileExists("version.tmp")
    #define MyAppVersion Trim(FileRead("version.tmp"))
  #else
    #define MyAppVersion "0.0.0"
  #endif
#endif

[Setup]
AppId={{A9F7F8E7-8A1F-4C4D-8CF1-6B9E0D0B7A23}}
AppName=Remote Controls
AppVersion={#MyAppVersion}
AppVerName=Remote Controls {#MyAppVersion}
AppPublisher=chen6019
AppPublisherURL=https://github.com/chen6019/Remote-Controls
DefaultDirName={commonpf}\Remote-Controls
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=dist\installer
OutputBaseFilename=Remote-Controls-Installer-{#MyAppVersion}
SetupIconFile=..\res\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin


[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项"; Flags: unchecked
Name: "autoruntray"; Description: "安装完成后启动托盘程序"; GroupDescription: "附加选项"; Flags: unchecked
Name: "autostart_main"; Description: "系统启动时运行主程序（以 SYSTEM 最高权限）"; GroupDescription: "自启动"; Flags: unchecked
Name: "autostart_tray"; Description: "用户登录时运行托盘（当前用户，最高权限）"; GroupDescription: "自启动"; Flags: unchecked

[Files]
Source: "dist\RC-GUI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\RC-main.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\RC-tray.exe"; DestDir: "{app}"; Flags: ignoreversion
; Optional: ship default config, but do not overwrite user changes
; Source: "..\config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{autoprograms}\Remote Controls"; Filename: "{app}\RC-tray.exe"
Name: "{autodesktop}\Remote Controls"; Filename: "{app}\RC-tray.exe"; Tasks: desktopicon
Name: "{autoprograms}\Remote Controls GUI"; Filename: "{app}\RC-GUI.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\RC-tray.exe"; ValueData: "RUNASADMIN"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\RC-main.exe"; ValueData: "RUNASADMIN"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\RC-GUI.exe"; ValueData: "RUNASADMIN"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\RC-tray.exe"; Description: "启动托盘程序"; Flags: nowait postinstall skipifsilent shellexec; Tasks: autoruntray

[UninstallDelete]
Type: dirifempty; Name: "{app}\logs"

[Code]
var
  CbKeepCfg: TNewCheckBox;
  KeepConfig: Boolean; // 是否保留配置文件，默认保留

function IsProcessRunning(ProcessName: String): Boolean;
var
  ResultCode: Integer;
begin
  // 使用tasklist检查特定进程，如果进程存在会在输出中包含进程名
  Result := Exec('cmd', '/C tasklist /FI "IMAGENAME eq ' + ProcessName + '" | findstr /I "' + ProcessName + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  ProcessesRunning: Boolean;
begin
  Result := True;
  ProcessesRunning := False;
  
  // 检查是否有程序正在运行
  if IsProcessRunning('RC-main.exe') then
    ProcessesRunning := True;
  if IsProcessRunning('RC-GUI.exe') then
    ProcessesRunning := True;
  if IsProcessRunning('RC-tray.exe') then
    ProcessesRunning := True;
  
  // 如果有程序运行且不是静默安装，提示用户
  if ProcessesRunning and not WizardSilent then begin
    if MsgBox('检测到 Remote Controls 程序正在运行。安装程序将自动关闭这些程序以确保安装成功。是否继续？', mbConfirmation, MB_YESNO) = IDNO then begin
      Result := False;
      Exit;
    end;
  end;
  
  // 强制关闭可能运行的程序进程
  try
    Exec('taskkill', '/F /IM RC-main.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', '/F /IM RC-GUI.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', '/F /IM RC-tray.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  // 等待进程完全终止
  Sleep(1000);
  
  // 使用过滤条件再次确保进程终止
  try
    Exec('taskkill', '/F /FI "IMAGENAME eq RC-main.exe" /FI "CPUTIME gt 00:00:00"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', '/F /FI "IMAGENAME eq RC-GUI.exe" /FI "CPUTIME gt 00:00:00"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', '/F /FI "IMAGENAME eq RC-tray.exe" /FI "CPUTIME gt 00:00:00"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
end;

procedure CreateScheduledTasks();
var
  TaskService, RootFolder, TaskDefinition, RegistrationInfo, Settings, Triggers, Actions: Variant;
  LogonTrigger, BootTrigger, Action: Variant;
  Principal: Variant;
begin
  try
    TaskService := CreateOleObject('Schedule.Service');
    TaskService.Connect();
    RootFolder := TaskService.GetFolder('\');
    
    if WizardIsTaskSelected('autostart_main') then begin
      try
        try
          RootFolder.DeleteTask('Remote Controls Main Service', 0);
        except
        end;
        
        TaskDefinition := TaskService.NewTask(0);
        
        RegistrationInfo := TaskDefinition.RegistrationInfo;
  RegistrationInfo.Description := '远程控制主程序 - 开机自启';
  RegistrationInfo.Author := 'spacejoy';
        
        Principal := TaskDefinition.Principal;
        Principal.UserId := 'SYSTEM';
        Principal.LogonType := 5; // TASK_LOGON_SERVICE_ACCOUNT
        Principal.RunLevel := 1;  // TASK_RUNLEVEL_HIGHEST
        
        Settings := TaskDefinition.Settings;
        Settings.Enabled := True;
        Settings.Hidden := False;
        Settings.StartWhenAvailable := True;
        Settings.DisallowStartIfOnBatteries := False;
        Settings.StopIfGoingOnBatteries := False;
        Settings.MultipleInstances := 3; // Match GUI: stop existing
        Settings.ExecutionTimeLimit := 'PT0S'; // unlimited
        
        Triggers := TaskDefinition.Triggers;
        // GUI uses ONSTART; no delay
        BootTrigger := Triggers.Create(8); // TASK_TRIGGER_BOOT
        BootTrigger.Enabled := True;
        
        Actions := TaskDefinition.Actions;
        Action := Actions.Create(0); // TASK_ACTION_EXEC
        Action.Path := ExpandConstant('{app}\RC-main.exe');
        Action.WorkingDirectory := ExpandConstant('{app}');
        
        RootFolder.RegisterTaskDefinition('Remote Controls Main Service', TaskDefinition, 6, '', '', 5);
      except
      end;
    end;
    
    if WizardIsTaskSelected('autostart_tray') then begin
      try
        try
          RootFolder.DeleteTask('Remote Controls Tray', 0);
        except
        end;
        
        TaskDefinition := TaskService.NewTask(0);
        
        RegistrationInfo := TaskDefinition.RegistrationInfo;
  RegistrationInfo.Description := '远程控制托盘程序 - 用户登录时启动';
  RegistrationInfo.Author := 'spacejoy';
        
        Principal := TaskDefinition.Principal;
        Principal.LogonType := 3; // TASK_LOGON_INTERACTIVE_TOKEN
        Principal.RunLevel := 1;  // TASK_RUNLEVEL_HIGHEST
        
        Settings := TaskDefinition.Settings;
        Settings.Enabled := True;
        Settings.Hidden := False;
        Settings.StartWhenAvailable := True;
        Settings.DisallowStartIfOnBatteries := False;
        Settings.StopIfGoingOnBatteries := False;
        Settings.MultipleInstances := 0; // Match GUI for tray
        Settings.ExecutionTimeLimit := 'PT0S'; // unlimited
        
        Triggers := TaskDefinition.Triggers;
        LogonTrigger := Triggers.Create(9); // TASK_TRIGGER_LOGON
        LogonTrigger.Enabled := True;
        
        Actions := TaskDefinition.Actions;
        Action := Actions.Create(0); // TASK_ACTION_EXEC
        Action.Path := ExpandConstant('{app}\RC-tray.exe');
        Action.WorkingDirectory := ExpandConstant('{app}');
        
        RootFolder.RegisterTaskDefinition('Remote Controls Tray', TaskDefinition, 6, '', '', 3);
      except
      end;
    end;
  except
  end;
end;

procedure DeleteScheduledTasks();
var
  TaskService, RootFolder: Variant;
begin
  try
    TaskService := CreateOleObject('Schedule.Service');
    TaskService.Connect();
    RootFolder := TaskService.GetFolder('\');
    
    try
      RootFolder.DeleteTask('Remote Controls Main Service', 0);
    except
    end;
    
    try
      RootFolder.DeleteTask('Remote Controls Tray', 0);
    except
    end;
  except
  end;
end;

procedure ForceCloseRunningProcesses();
var
  ResultCode: Integer;
  AppPath: String;
begin
  AppPath := ExpandConstant('{app}');
  
  // 强制终止可能运行的程序进程
  // 使用taskkill命令强制终止，忽略错误（程序可能没有运行）
  try
    // 终止主程序
    Exec('taskkill', '/F /IM RC-main.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    // 终止GUI程序
    Exec('taskkill', '/F /IM RC-GUI.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    // 终止托盘程序
    Exec('taskkill', '/F /IM RC-tray.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  // 等待进程完全终止
  Sleep(1000);
  
  // 使用完整路径终止进程（防止同名进程干扰）
  try
    Exec('taskkill', Format('/F /FI "IMAGENAME eq RC-main.exe" /FI "CPUTIME gt 00:00:00"', []), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', Format('/F /FI "IMAGENAME eq RC-GUI.exe" /FI "CPUTIME gt 00:00:00"', []), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  
  try
    Exec('taskkill', Format('/F /FI "IMAGENAME eq RC-tray.exe" /FI "CPUTIME gt 00:00:00"', []), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
end;

function InitializeUninstall(): Boolean;
var
  UninstallForm: TSetupForm;
  Panel: TPanel;
  InfoLabel: TNewStaticText;
  OkBtn, CancelBtn: TNewButton;
  YPos: Integer;
begin
  // 首先强制关闭可能运行的程序
  ForceCloseRunningProcesses();
  
  // 默认保留配置文件（静默卸载也保留）
  KeepConfig := True;
  Result := True;

  // 静默卸载：不显示界面，直接按默认策略保留配置
  if UninstallSilent then
    exit;

  // 交互卸载：提供选项
  UninstallForm := CreateCustomForm();
  UninstallForm.Caption := '卸载选项';
  UninstallForm.ClientWidth := 460;
  UninstallForm.ClientHeight := 200;
  UninstallForm.Position := poScreenCenter;

  Panel := TPanel.Create(UninstallForm);
  Panel.Parent := UninstallForm;
  Panel.Left := 20;
  Panel.Top := 20;
  Panel.Width := 420;
  Panel.Height := 130;
  Panel.BevelOuter := bvNone;

  YPos := 10;

  // 提示：日志将自动删除；配置文件由程序运行时生成
  InfoLabel := TNewStaticText.Create(Panel);
  InfoLabel.Parent := Panel;
  InfoLabel.Left := 10;
  InfoLabel.Top := YPos;
  InfoLabel.Width := 400;
  InfoLabel.Height := 40;
  InfoLabel.AutoSize := False;
  InfoLabel.Caption := '提示：卸载将自动删除日志目录（logs）。配置文件由程序运行时生成，可选择是否保留。';

  YPos := YPos + 50;

  // 是否保留配置文件 config.json（默认勾选=保留）
  CbKeepCfg := TNewCheckBox.Create(Panel);
  CbKeepCfg.Parent := Panel;
  CbKeepCfg.Left := 10;
  CbKeepCfg.Top := YPos;
  CbKeepCfg.Width := 400;
  CbKeepCfg.Height := 19;
  CbKeepCfg.Caption := '保留配置文件（config.json）';
  CbKeepCfg.Checked := True;

  // 确认/取消按钮
  OkBtn := TNewButton.Create(UninstallForm);
  OkBtn.Parent := UninstallForm;
  OkBtn.Width := ScaleX(80);
  OkBtn.Height := ScaleY(25);
  OkBtn.Left := UninstallForm.ClientWidth - ScaleX(180);
  OkBtn.Top := UninstallForm.ClientHeight - ScaleY(45);
  OkBtn.Caption := '确认';
  OkBtn.ModalResult := mrOk;

  CancelBtn := TNewButton.Create(UninstallForm);
  CancelBtn.Parent := UninstallForm;
  CancelBtn.Width := ScaleX(80);
  CancelBtn.Height := ScaleY(25);
  CancelBtn.Left := UninstallForm.ClientWidth - ScaleX(90);
  CancelBtn.Top := UninstallForm.ClientHeight - ScaleY(45);
  CancelBtn.Caption := '取消';
  CancelBtn.ModalResult := mrCancel;

  UninstallForm.ActiveControl := OkBtn;

  if UninstallForm.ShowModal = mrOk then begin
    KeepConfig := CbKeepCfg.Checked;
    Result := True;
  end else begin
    // 用户取消卸载
    Result := False;
  end;

  UninstallForm.Free;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then begin
    // 在文件复制前再次确保程序已完全关闭
    try
      Exec('taskkill', '/F /IM RC-main.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    
    try
      Exec('taskkill', '/F /IM RC-GUI.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    
    try
      Exec('taskkill', '/F /IM RC-tray.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    
    // 短暂等待进程终止
    Sleep(500);
  end;
  
  if CurStep = ssPostInstall then begin
    CreateScheduledTasks();
  end;
end;



procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigFile, LogsDir: String;
begin
  if CurUninstallStep = usUninstall then begin
    // 再次确保程序已完全关闭
    ForceCloseRunningProcesses();
    
    // 删除计划任务
    DeleteScheduledTasks();
    
    // Always remove logs
    LogsDir := ExpandConstant('{app}\logs');
    if DirExists(LogsDir) then
      DelTree(LogsDir, True, True, True);

  // 根据用户选择删除或保留配置文件（默认保留；静默卸载也保留）
  if not KeepConfig then begin
      ConfigFile := ExpandConstant('{app}\config.json');
      if FileExists(ConfigFile) then
        DeleteFile(ConfigFile);
    end;
  end;
end;



; Inno Setup Script for Remote-Controls
; Package includes: RC-GUI.exe, RC-main.exe, RC-tray.exe, config.json, logs directory
; Generate an offline installer, install to Program Files (requires admin privileges)

#define MyAppVersion "2.2.4"

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
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional options"; Flags: checkedonce
Name: "autoruntray"; Description: "Start tray program after installation"; GroupDescription: "Additional options"; Flags: checkedonce
Name: "autostart_main"; Description: "Run main program on system startup (as SYSTEM, highest privileges)"; GroupDescription: "Auto startup"; Flags: checkedonce
Name: "autostart_tray"; Description: "Run tray on user login (current user, highest privileges)"; GroupDescription: "Auto startup"; Flags: checkedonce

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
Filename: "{app}\RC-tray.exe"; Description: "Start tray program"; Flags: nowait postinstall skipifsilent shellexec; Tasks: autoruntray

[UninstallDelete]
Type: dirifempty; Name: "{app}\logs"

[Code]
var
  CbCfg, CbLogs: TNewCheckBox;

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
        RegistrationInfo.Description := 'Remote Controls Main Service - Auto startup';
        RegistrationInfo.Author := 'chen6019';
        
        Principal := TaskDefinition.Principal;
        Principal.UserId := 'SYSTEM';
        Principal.LogonType := 5;
        Principal.RunLevel := 1;
        
        Settings := TaskDefinition.Settings;
        Settings.Enabled := True;
        Settings.Hidden := False;
        Settings.StartWhenAvailable := True;
        Settings.DisallowStartIfOnBatteries := False;
        Settings.StopIfGoingOnBatteries := False;
        Settings.AllowHardTerminate := True;
        Settings.RestartOnFailure := True;
        Settings.RestartInterval := 'PT1M';
        Settings.RestartCount := 3;
        Settings.ExecutionTimeLimit := 'PT0S';
        
        Triggers := TaskDefinition.Triggers;
        BootTrigger := Triggers.Create(8);
        BootTrigger.Enabled := True;
        BootTrigger.Delay := 'PT30S';
        
        Actions := TaskDefinition.Actions;
        Action := Actions.Create(0);
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
        RegistrationInfo.Description := 'Remote Controls Tray Program - Start on user login';
        RegistrationInfo.Author := 'chen6019';
        
        Principal := TaskDefinition.Principal;
        Principal.LogonType := 3;
        Principal.RunLevel := 1;
        
        Settings := TaskDefinition.Settings;
        Settings.Enabled := True;
        Settings.Hidden := False;
        Settings.StartWhenAvailable := True;
        Settings.DisallowStartIfOnBatteries := False;
        Settings.StopIfGoingOnBatteries := False;
        Settings.AllowHardTerminate := True;
        Settings.RestartOnFailure := True;
        Settings.RestartInterval := 'PT1M';
        Settings.RestartCount := 3;
        Settings.ExecutionTimeLimit := 'PT0S';
        
        Triggers := TaskDefinition.Triggers;
        LogonTrigger := Triggers.Create(9);
        LogonTrigger.Enabled := True;
        LogonTrigger.Delay := 'PT10S';
        
        Actions := TaskDefinition.Actions;
        Action := Actions.Create(0);
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

function InitializeUninstall(): Boolean;
var
  UninstallForm: TSetupForm;
  Panel: TPanel;
  YPos: Integer;
begin
  Result := True;
  
  UninstallForm := CreateCustomForm();
  UninstallForm.Caption := 'Uninstall Options';
  UninstallForm.ClientWidth := 400;
  UninstallForm.ClientHeight := 200;
  UninstallForm.Position := poScreenCenter;
  
  Panel := TPanel.Create(UninstallForm);
  Panel.Parent := UninstallForm;
  Panel.Left := 20;
  Panel.Top := 20;
  Panel.Width := 360;
  Panel.Height := 120;
  Panel.BevelOuter := bvNone;
  
  YPos := 20;
  
  CbCfg := TNewCheckBox.Create(Panel);
  CbCfg.Parent := Panel;
  CbCfg.Left := 10;
  CbCfg.Top := YPos;
  CbCfg.Width := 340;
  CbCfg.Height := 17;
  CbCfg.Caption := 'Delete configuration file config.json';
  CbCfg.Checked := False;
  
  YPos := YPos + 30;
  
  CbLogs := TNewCheckBox.Create(Panel);
  CbLogs.Parent := Panel;
  CbLogs.Left := 10;
  CbLogs.Top := YPos;
  CbLogs.Width := 340;
  CbLogs.Height := 17;
  CbLogs.Caption := 'Delete logs directory (including all files)';
  CbLogs.Checked := False;
  
  if UninstallForm.ShowModal = mrOk then begin
    Result := True;
  end else begin
    Result := False;
  end;
  
  UninstallForm.Free;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    CreateScheduledTasks();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigFile, LogsDir: String;
begin
  if CurUninstallStep = usUninstall then begin
    DeleteScheduledTasks();
    
    if Assigned(CbCfg) and CbCfg.Checked then begin
      ConfigFile := ExpandConstant('{app}\config.json');
      if FileExists(ConfigFile) then
        DeleteFile(ConfigFile);
    end;
    
    if Assigned(CbLogs) and CbLogs.Checked then begin
      LogsDir := ExpandConstant('{app}\logs');
      if DirExists(LogsDir) then
        DelTree(LogsDir, True, True, True);
    end;
  end;
end;


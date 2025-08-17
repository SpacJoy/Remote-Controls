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
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional options"; Flags: unchecked
Name: "autoruntray"; Description: "Start tray program after installation"; GroupDescription: "Additional options"; Flags: unchecked
Name: "autostart_main"; Description: "Run main program on system startup (as SYSTEM, highest privileges)"; GroupDescription: "Auto startup"; Flags: unchecked
Name: "autostart_tray"; Description: "Run tray on user login (current user, highest privileges)"; GroupDescription: "Auto startup"; Flags: unchecked

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
  CbKeepCfg: TNewCheckBox;

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
        RegistrationInfo.Description := 'Remote Controls Tray Program - Start on user login';
        RegistrationInfo.Author := 'chen6019';
        
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

function InitializeUninstall(): Boolean;
var
  UninstallForm: TSetupForm;
  Panel: TPanel;
  InfoLabel: TNewStaticText;
  YPos: Integer;
begin
  Result := True;
  
  UninstallForm := CreateCustomForm();
  UninstallForm.Caption := 'Uninstall Options';
  UninstallForm.ClientWidth := 420;
  UninstallForm.ClientHeight := 180;
  UninstallForm.Position := poScreenCenter;
  
  Panel := TPanel.Create(UninstallForm);
  Panel.Parent := UninstallForm;
  Panel.Left := 20;
  Panel.Top := 20;
  Panel.Width := 380;
  Panel.Height := 110;
  Panel.BevelOuter := bvNone;
  
  YPos := 10;
  
  // Info about logs
  InfoLabel := TNewStaticText.Create(Panel);
  InfoLabel.Parent := Panel;
  InfoLabel.Left := 10;
  InfoLabel.Top := YPos;
  InfoLabel.Width := 360;
  InfoLabel.Height := 30;
  InfoLabel.AutoSize := False;
  InfoLabel.Caption := 'Logs directory will be removed automatically during uninstall.';
  
  YPos := YPos + 40;
  
  // Only allow choosing whether to keep config.json
  CbKeepCfg := TNewCheckBox.Create(Panel);
  CbKeepCfg.Parent := Panel;
  CbKeepCfg.Left := 10;
  CbKeepCfg.Top := YPos;
  CbKeepCfg.Width := 360;
  CbKeepCfg.Height := 17;
  CbKeepCfg.Caption := 'Keep configuration file (config.json)';
  CbKeepCfg.Checked := True; // default keep
  
  if UninstallForm.ShowModal = mrOk then
    Result := True
  else
    Result := False;
  
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
    
    // Always remove logs
    LogsDir := ExpandConstant('{app}\logs');
    if DirExists(LogsDir) then
      DelTree(LogsDir, True, True, True);

    // Delete config.json unless user chose to keep
    if not (Assigned(CbKeepCfg) and CbKeepCfg.Checked) then begin
      ConfigFile := ExpandConstant('{app}\config.json');
      if FileExists(ConfigFile) then
        DeleteFile(ConfigFile);
    end;
  end;
end;







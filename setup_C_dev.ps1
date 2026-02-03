# Remote Controls 开发环境一键部署脚本 (仅限 C 语言与构建工具)
# 用法: .\setup_C_dev.ps1 (需要管理员权限以安装软件)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "===== 开始部署 Remote Controls C 语言开发环境 =====" -ForegroundColor Cyan

$Global:SkipAllConfirm = $false

# 函数：分步确认
function Confirm-Step {
    param([string]$StepDescription)
    if ($Global:SkipAllConfirm) { return $true }
    
    Write-Host "`n>>> 准备执行: $StepDescription" -ForegroundColor Magenta
    $choice = Read-Host "是否继续执行? [Y] 是 / [N] 跳过 / [A] 全部执行并不再提示(默认N)"
    switch ($choice.ToUpper()) {
        "Y" { return $true }
        "A" { $Global:SkipAllConfirm = $true; return $true }
        default { 
            Write-Host "已跳过该步骤。" -ForegroundColor Gray
            return $false 
        }
    }
}

# 函数：检查并安装软件 (通过 Winget)
function Install-App {
    param([string]$AppName, [string]$PackageId, [string]$ExecutableName, [string[]]$DefaultPaths)
    Write-Host "`n正在检查 $AppName..." -ForegroundColor Yellow
    
    # 1. 优先检查系统 PATH 中是否已有可执行文件
    $ExePath = Get-Command $ExecutableName -ErrorAction SilentlyContinue
    $InstalledInfo = $null
    $IsInstalled = $false

    if ($ExePath) {
        $IsInstalled = $true
        $InstalledInfo = "在 PATH 中找到: $($ExePath.Source)"
    } 
    # 2. 检查指定的默认安装路径 (支持数组)
    else {
        foreach ($path in $DefaultPaths) {
            if ($path -and (Test-Path $path)) {
                $IsInstalled = $true
                $InstalledInfo = "在路径找到: $path"
                # 如果不在 PATH 中，尝试临时加入
                $dir = Split-Path $path
                if ($env:PATH -notlike "*$dir*") { $env:PATH = "$dir;" + $env:PATH }
                break
            }
        }
    }
    
    # 3. 针对 Inno Setup 的额外注册表检查 (包含用户级安装)
    if (-not $IsInstalled -and $AppName -eq "Inno Setup") {
        $SearchKeys = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1"
        )

        foreach ($key in $SearchKeys) {
            if (Test-Path $key) {
                $item = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
                $loc = $item.InstallLocation
                $exe = "iscc.exe"

                if ($loc -and (Test-Path (Join-Path $loc $exe))) {
                    $IsInstalled = $true
                    $fullPath = Join-Path $loc $exe
                    $InstalledInfo = "在注册表中找到: $fullPath"
                    if ($env:PATH -notlike "*$loc*") { $env:PATH = "$loc;" + $env:PATH }
                    break
                }
            }
        }
    }

    # 4. 尝试通过 winget 查找
    if (-not $IsInstalled) {
        $WingetInfo = winget list --id $PackageId -e -q 2>$null
        if ($? -and $WingetInfo) {
            $IsInstalled = $true
            $InstalledInfo = ($WingetInfo | Select-String -Pattern $PackageId) -join " "
        }
    }

    if ($IsInstalled) {
        Write-Host "检测到已安装 $AppName。" -ForegroundColor Green
        Write-Host "当前信息: $InstalledInfo" -ForegroundColor Gray
        
        if ($Global:SkipAllConfirm) { return $false }

        $choice = Read-Host "是否重新安装/更新 $AppName? [R] 重新安装 / [S] 跳过 (默认 S)"
        if ($choice.ToUpper() -ne "R") {
            Write-Host "已跳过安装。" -ForegroundColor Gray
            return $false
        }
    } else {
        Write-Host "未检测到 $AppName。" -ForegroundColor Cyan
        
        if (-not $Global:SkipAllConfirm) {
            $choice = Read-Host "是否现在安装 $AppName? [Y] 是 / [N] 否 (默认 Y)"
            if ($choice.ToUpper() -eq "N") {
                Write-Host "已取消安装 $AppName。" -ForegroundColor Gray
                return $false
            }
        }
    }

    Write-Host "正在通过 winget 安装 $AppName..." -ForegroundColor Cyan
    winget install --id $PackageId --accept-package-agreements --accept-source-agreements
    return $true
}

# 1. 安装构建工具 (Inno Setup)
if (Confirm-Step "管理系统构建工具 (Inno Setup)") {
    Write-Host "`n[1/3] 检查系统构建工具..." -ForegroundColor White
    $NeedRestart = $false
    
    $InnoPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\iscc.exe",
        "${env:ProgramFiles}\Inno Setup 6\iscc.exe",
        "${env:LocalAppData}\Programs\Inno Setup 6\iscc.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\iscc.exe",
        "${env:ProgramFiles}\Inno Setup 5\iscc.exe"
    )
    $NeedRestart = $NeedRestart -or (Install-App "Inno Setup" "JRSoftware.InnoSetup" "iscc" $InnoPaths)

    if ($NeedRestart) {
        Write-Host "提示: 部分软件新安装或更新成功，如果后续步骤失败，请重启 Terminal 后再次运行此脚本。" -ForegroundColor Magenta
    }
}

# 2. 配置 C 语言开发环境 (GCC & Paho MQTT)
if (Confirm-Step "配置 C 语言开发环境 (GCC & Paho MQTT)") {
    Write-Host "`n[2/3] 配置 C 语言开发环境..." -ForegroundColor White
    
    # 2.1 检查 GCC
    $Gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if ($Gcc) {
        Write-Host "检测到系统 GCC: $($Gcc.Source)" -ForegroundColor Green
    } else {
        Write-Host "未在 PATH 中找到 GCC。" -ForegroundColor Yellow
        # 尝试常用路径
        $CommonGccPaths = @(
            "C:\msys64\mingw64\bin\gcc.exe",
            "C:\msys64\ucrt64\bin\gcc.exe"
        )
        foreach ($path in $CommonGccPaths) {
            if (Test-Path $path) {
                Write-Host "在常用路径找到 GCC: $path" -ForegroundColor Cyan
                $GccDir = Split-Path $path
                if ($env:PATH -notlike "*$GccDir*") {
                    $env:PATH = "$GccDir;" + $env:PATH
                    Write-Host "已临时将 GCC 路径加入当前会话 PATH。" -ForegroundColor Gray
                }
                $Gcc = Get-Command gcc -ErrorAction SilentlyContinue
                break
            }
        }
    }

    # 2.2 检查 Paho MQTT C
    $PahoFound = $false
    if ($env:PAHO_MQTT_C_ROOT -and (Test-Path (Join-Path $env:PAHO_MQTT_C_ROOT "include\MQTTClient.h"))) {
        Write-Host "检测到 Paho MQTT C (通过环境变量): $env:PAHO_MQTT_C_ROOT" -ForegroundColor Green
        $PahoFound = $true
    } else {
        $CommonPahoPaths = @(
            "C:\msys64\mingw64",
            "C:\msys64\ucrt64"
        )
        foreach ($path in $CommonPahoPaths) {
            if (Test-Path (Join-Path $path "include\MQTTClient.h")) {
                Write-Host "在常用路径找到 Paho MQTT C: $path" -ForegroundColor Green
                $env:PAHO_MQTT_C_ROOT = $path
                $PahoFound = $true
                break
            }
        }
    }

    # 2.3 如果缺失，尝试通过 MSYS2 补全
    if (-not $Gcc -or -not $PahoFound) {
        Write-Host "C 环境不完整，尝试寻找或安装 MSYS2 以补全依赖..." -ForegroundColor Yellow
        
        # 只有在找不到 C 编译器时才尝试寻找/安装 MSYS2
        if (Test-Path "C:\msys64\usr\bin\bash.exe") {
             Write-Host "检测到已安装 MSYS2 (物理路径)。" -ForegroundColor Green
        } else {
             Install-App "MSYS2" "MSYS2.MSYS2" "msys2" "C:\msys64\msys2_shell.cmd" | Out-Null
        }
        
        $MsysPath = "C:\msys64"
        $Bash = Join-Path $MsysPath "usr\bin\bash.exe"
        if (Test-Path $Bash) {
            $ToInstall = @()
            if (-not $Gcc) { $ToInstall += "mingw-w64-x86_64-gcc" }
            if (-not $PahoFound) { $ToInstall += "mingw-w64-x86_64-paho.mqtt.c" }
            
            if ($ToInstall.Count -gt 0) {
                $PkgList = $ToInstall -join " "
                if (Confirm-Step "通过 MSYS2 安装缺失包: $PkgList") {
                    & $Bash -lc "pacman -S --noconfirm --needed $PkgList"
                    # 安装后重新设置变量
                    if ($ToInstall -contains "mingw-w64-x86_64-paho.mqtt.c") {
                        $env:PAHO_MQTT_C_ROOT = "C:\msys64\mingw64"
                        $PahoFound = $true
                    }
                    if ($ToInstall -contains "mingw-w64-x86_64-gcc") {
                        $GccDir = "C:\msys64\mingw64\bin"
                        if ($env:PATH -notlike "*$GccDir*") { $env:PATH = "$GccDir;" + $env:PATH }
                        $Gcc = Get-Command gcc -ErrorAction SilentlyContinue
                    }
                }
            }
        } else {
            Write-Host "未找到 MSYS2，无法自动安装缺失的 C 开发组件。" -ForegroundColor Red
            Write-Host "请手动安装 GCC 并配置 Paho MQTT C 库。" -ForegroundColor White
        }
    }

    # 2.4 永久添加 PATH (可选)
    if ($Gcc) {
        $GccBin = Split-Path $Gcc.Source
        $UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($UserPath -notlike "*$GccBin*") {
            if (Confirm-Step "永久将 GCC 路径添加到用户 PATH 环境变量?") {
                [Environment]::SetEnvironmentVariable("PATH", $UserPath + ";" + $GccBin, "User")
                Write-Host "已永久添加 PATH，重启 IDE 后生效。" -ForegroundColor Green
            }
        }
    }

    # 2.5 永久添加 PAHO_MQTT_C_ROOT (可选)
    if ($PahoFound) {
        $CurrentPahoRoot = [Environment]::GetEnvironmentVariable("PAHO_MQTT_C_ROOT", "User")
        if ($CurrentPahoRoot -ne $env:PAHO_MQTT_C_ROOT) {
            if (Confirm-Step "永久设置 PAHO_MQTT_C_ROOT 环境变量?") {
                [Environment]::SetEnvironmentVariable("PAHO_MQTT_C_ROOT", $env:PAHO_MQTT_C_ROOT, "User")
                Write-Host "环境变量 PAHO_MQTT_C_ROOT 已设置。" -ForegroundColor Green
            }
        }
    }
}

# 3. 最终验证
Write-Host "`n[3/3] 最终环境验证..." -ForegroundColor White
$Gcc = Get-Command gcc -ErrorAction SilentlyContinue
if ($Gcc) { Write-Host "GCC: OK ($($Gcc.Source))" -ForegroundColor Green } else { Write-Host "GCC: 未找到 (请确保 C:\msys64\mingw64\bin 在 PATH 中)" -ForegroundColor Red }

if (Test-Path (Join-Path $env:PAHO_MQTT_C_ROOT "include\MQTTClient.h")) {
    Write-Host "Paho MQTT C: OK" -ForegroundColor Green
} else {
    Write-Host "Paho MQTT C: 未找到" -ForegroundColor Red
}

$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($Iscc) { Write-Host "Inno Setup (ISCC): OK ($($Iscc.Source))" -ForegroundColor Green } else { Write-Host "Inno Setup: 未找到" -ForegroundColor Red }

Write-Host "`n===== 部署完成 =====" -ForegroundColor Cyan
Write-Host "提示: 如果这是您第一次运行，建议关闭并重新打开 Terminal 以应用所有环境变量。" -ForegroundColor Gray
Write-Host "Python 环境与依赖请使用 setup_python_env.ps1 管理" -ForegroundColor White

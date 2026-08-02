# Remote Controls 开发环境一键部署脚本 (仅限 C 语言与构建工具)
# 用法: .\setup_C_dev.ps1 (需要管理员权限以安装软件)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "===== 开始部署 Remote Controls C 语言开发环境 =====" -ForegroundColor Cyan

$Global:SkipAllConfirm = $false

# 函数：分步确认 (支持回到上一步，空输入不执行任何操作以防误触回车)
# 返回值: 'proceed' (继续) / 'skip' (跳过) / 'back' (回到上一步)
function Confirm-Step {
    param(
        [string]$StepDescription,
        [switch]$NoBack
    )
    if ($Global:SkipAllConfirm) { return 'proceed' }

    while ($true) {
        Write-Host "`n>>> 准备执行: $StepDescription" -ForegroundColor Magenta
        if ($NoBack) {
            $prompt = "是否继续执行? [Y] 是 / [N] 跳过 / [A] 全部执行并不再提示"
        } else {
            $prompt = "是否继续执行? [Y] 是 / [N] 跳过 / [B] 回到上一步 / [A] 全部执行并不再提示"
        }
        $choice = (Read-Host $prompt).Trim()
        switch ($choice.ToUpper()) {
            "Y" { return 'proceed' }
            "A" { $Global:SkipAllConfirm = $true; return 'proceed' }
            "B" {
                if ($NoBack) {
                    Write-Host "无效输入，请重新选择。" -ForegroundColor Yellow
                } else {
                    Write-Host "返回上一步..." -ForegroundColor Gray
                    return 'back'
                }
            }
            "N" {
                Write-Host "已跳过该步骤。" -ForegroundColor Gray
                return 'skip'
            }
            "" {
                Write-Host "未输入选项，请重新选择 (误触回车不会执行任何操作)。" -ForegroundColor Yellow
            }
            default {
                Write-Host "无效输入 '$choice'，请重新选择。" -ForegroundColor Yellow
            }
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
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget 安装 $AppName 失败 (退出码: $LASTEXITCODE)。" -ForegroundColor Red
        return $false
    }
    return $true
}

# 主流程: 支持回到上一步的步骤循环
$CurrentStep = 1
while ($CurrentStep -le 2) {
    if ($CurrentStep -eq 1) {
        $action = Confirm-Step "管理系统构建工具 (Inno Setup)"
        if ($action -eq 'back') {
            Write-Host "已是第一步，重新确认。" -ForegroundColor Gray
            continue
        }
        if ($action -eq 'proceed') {
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
        } # end proceed step 1
        $CurrentStep = 2
    } elseif ($CurrentStep -eq 2) {
        $action = Confirm-Step "配置 C 语言开发环境 (GCC & Paho MQTT)"
        if ($action -eq 'back') { $CurrentStep = 1; continue }
        if ($action -eq 'proceed') {
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
        
        # 多路径检测已安装的 MSYS2
        $MsysPath = $null
        $CandidateMsysPaths = @(
            "C:\msys64",
            "${env:LocalAppData}\msys64",
            "D:\msys64",
            "E:\msys64"
        )
        # 过滤掉驱动器不存在的候选路径，避免 Join-Path 在 ErrorActionPreference=Stop 下抛出 DriveNotFoundException
        $CandidateMsysPaths = $CandidateMsysPaths | Where-Object {
            $_ -and ($_ -match '^([A-Za-z]:)') -and (Test-Path "$($Matches[1])\")
        }
        foreach ($cand in $CandidateMsysPaths) {
            if (Test-Path (Join-Path $cand "usr\bin\bash.exe") -ErrorAction SilentlyContinue) {
                $MsysPath = $cand
                Write-Host "检测到已安装 MSYS2: $MsysPath" -ForegroundColor Green
                break
            }
        }
        
        # 未检测到则尝试安装 (winget -> GitHub 直接下载回退)
        if (-not $MsysPath) {
            $WingetOk = Install-App "MSYS2" "MSYS2.MSYS2" "msys2" @("C:\msys64\msys2_shell.cmd")
            if ($WingetOk) {
                foreach ($cand in $CandidateMsysPaths) {
                    if (Test-Path (Join-Path $cand "usr\bin\bash.exe") -ErrorAction SilentlyContinue) {
                        $MsysPath = $cand
                        break
                    }
                }
            }
            
            # winget 失败或仍未检测到 -> 直接从 GitHub 下载安装器
            if (-not $MsysPath -and ((Confirm-Step "winget 安装 MSYS2 失败，是否从 GitHub 直接下载安装器?" -NoBack) -eq 'proceed')) {
                $ApiUrl = "https://api.github.com/repos/msys2/msys2-installer/releases/latest"
                try {
                    Write-Host "正在查询 MSYS2 最新发布版本..." -ForegroundColor Cyan
                    $Release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ "User-Agent" = "setup_C_dev.ps1" } -ErrorAction Stop
                    $Asset = $Release.assets | Where-Object { $_.name -like "msys2-x86_64-*.exe" } | Select-Object -First 1
                    if (-not $Asset) {
                        Write-Host "未在 GitHub release 中找到 MSYS2 安装器资产。" -ForegroundColor Red
                    } else {
                        $Installer = Join-Path $env:TEMP $Asset.name
                        Write-Host "正在下载 $($Asset.name) ..." -ForegroundColor Cyan
                        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $Installer -UseBasicParsing
                        Write-Host "正在静默安装 MSYS2 到 C:\msys64 ..." -ForegroundColor Cyan
                        $Proc = Start-Process -FilePath $Installer -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-" -Wait -PassThru -NoNewWindow
                        if ($Proc.ExitCode -ne 0) {
                            Write-Host "MSYS2 安装器返回非零退出码: $($Proc.ExitCode)" -ForegroundColor Red
                        }
                        if (Test-Path "C:\msys64\usr\bin\bash.exe") {
                            $MsysPath = "C:\msys64"
                            Write-Host "MSYS2 安装成功: $MsysPath" -ForegroundColor Green
                        } else {
                            Write-Host "MSYS2 静默安装后仍未检测到 bash.exe。" -ForegroundColor Red
                        }
                        Remove-Item $Installer -Force -ErrorAction SilentlyContinue
                    }
                } catch {
                    Write-Host "GitHub 下载回退失败: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
        }
        
        # 初始化 MSYS2 并安装缺失包
        if ($MsysPath -and (Test-Path (Join-Path $MsysPath "usr\bin\bash.exe"))) {
            $Bash = Join-Path $MsysPath "usr\bin\bash.exe"
            $MingwRoot = Join-Path $MsysPath "mingw64"
            
            # 首次安装后初始化 pacman 密钥与数据库 (否则后续 pacman -S 会失败)
            if ((Confirm-Step "初始化 MSYS2 pacman 密钥与数据库 (首次安装必需)" -NoBack) -eq 'proceed') {
                Write-Host "正在初始化 pacman-key 与数据库..." -ForegroundColor Cyan
                & $Bash -lc "pacman-key --init; pacman-key --populate msys2; pacman -Sy --noconfirm" 2>&1 | Out-Host
            }
            
            $ToInstall = @()
            if (-not $Gcc) { $ToInstall += "mingw-w64-x86_64-gcc" }
            if (-not $PahoFound) { $ToInstall += "mingw-w64-x86_64-paho.mqtt.c" }
            
            if ($ToInstall.Count -gt 0) {
                $PkgList = $ToInstall -join " "
                if ((Confirm-Step "通过 MSYS2 安装缺失包: $PkgList" -NoBack) -eq 'proceed') {
                    & $Bash -lc "pacman -S --noconfirm --needed $PkgList"
                    # 安装后重新设置变量
                    if ($ToInstall -contains "mingw-w64-x86_64-paho.mqtt.c") {
                        $env:PAHO_MQTT_C_ROOT = $MingwRoot
                        $PahoFound = $true
                    }
                    if ($ToInstall -contains "mingw-w64-x86_64-gcc") {
                        $GccDir = Join-Path $MingwRoot "bin"
                        if ($env:PATH -notlike "*$GccDir*") { $env:PATH = "$GccDir;" + $env:PATH }
                        $Gcc = Get-Command gcc -ErrorAction SilentlyContinue
                    }
                }
            }
        } else {
            Write-Host "未找到 MSYS2，无法自动安装缺失的 C 开发组件。" -ForegroundColor Red
            Write-Host "请手动安装 MSYS2 (https://www.msys2.org/) 并配置 GCC 与 Paho MQTT C 库。" -ForegroundColor White
        }
    }

    # 2.4 永久添加 PATH (可选)
    if ($Gcc) {
        $GccBin = Split-Path $Gcc.Source
        $UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($UserPath -notlike "*$GccBin*") {
            if ((Confirm-Step "永久将 GCC 路径添加到用户 PATH 环境变量?" -NoBack) -eq 'proceed') {
                [Environment]::SetEnvironmentVariable("PATH", $UserPath + ";" + $GccBin, "User")
                Write-Host "已永久添加 PATH，重启 IDE 后生效。" -ForegroundColor Green
            }
        }
    }

    # 2.5 永久添加 PAHO_MQTT_C_ROOT (可选)
    if ($PahoFound) {
        $CurrentPahoRoot = [Environment]::GetEnvironmentVariable("PAHO_MQTT_C_ROOT", "User")
        if ($CurrentPahoRoot -ne $env:PAHO_MQTT_C_ROOT) {
            if ((Confirm-Step "永久设置 PAHO_MQTT_C_ROOT 环境变量?" -NoBack) -eq 'proceed') {
                [Environment]::SetEnvironmentVariable("PAHO_MQTT_C_ROOT", $env:PAHO_MQTT_C_ROOT, "User")
                Write-Host "环境变量 PAHO_MQTT_C_ROOT 已设置。" -ForegroundColor Green
            }
        }
    }
        } # end proceed step 2
        $CurrentStep = 3
    }
} # end mainLoop

# 3. 最终验证
Write-Host "`n[3/3] 最终环境验证..." -ForegroundColor White
$Gcc = Get-Command gcc -ErrorAction SilentlyContinue
if ($Gcc) { Write-Host "GCC: OK ($($Gcc.Source))" -ForegroundColor Green } else { Write-Host "GCC: 未找到 (请确保 C:\msys64\mingw64\bin 在 PATH 中)" -ForegroundColor Red }

if ($env:PAHO_MQTT_C_ROOT -and (Test-Path (Join-Path $env:PAHO_MQTT_C_ROOT "include\MQTTClient.h"))) {
    Write-Host "Paho MQTT C: OK ($env:PAHO_MQTT_C_ROOT)" -ForegroundColor Green
} else {
    Write-Host "Paho MQTT C: 未找到 (PAHO_MQTT_C_ROOT 未设置或路径无效)" -ForegroundColor Red
}

$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($Iscc) { Write-Host "Inno Setup (ISCC): OK ($($Iscc.Source))" -ForegroundColor Green } else { Write-Host "Inno Setup: 未找到" -ForegroundColor Red }

Write-Host "`n===== 部署完成 =====" -ForegroundColor Cyan
Write-Host "提示: 如果这是您第一次运行，建议关闭并重新打开 Terminal 以应用所有环境变量。" -ForegroundColor Gray
Write-Host "Python 环境与依赖请使用 setup_python_env.ps1 管理" -ForegroundColor White

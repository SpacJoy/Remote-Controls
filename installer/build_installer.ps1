<#
Remote Controls 项目打包脚本 (PowerShell)
用法：
    - 双击运行（推荐）
    - 或在任意目录执行：pwsh -NoProfile -ExecutionPolicy Bypass -File installer/build_installer.ps1 [版本号]
说明：
    - 脚本使用自身路径解析，不依赖当前工作目录。
#>

param(
    [string]$Version = "",
    [switch]$NoPause
)

# 统一编码：避免 PowerShell 5.1 下脚本/外部命令中文输出出现乱码
try {
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch {
}

function Pause-IfNeeded {
    param([string]$Message = '按Enter键退出')
    if (-not $NoPause) {
        Read-Host $Message
    }
}

Write-Host "========================================"
Write-Host "远程控制 项目打包脚本"
Write-Host "========================================"
Write-Host ""

# 显示版本信息
if ($Version) {
    Write-Host "指定版本: $Version" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "请输入版本号 (格式: X.Y.Z，如 1.0.0)" -ForegroundColor Yellow
    Write-Host "留空使用当前版本信息" -ForegroundColor Cyan
    $InputVersion = Read-Host "版本号"
    if ($InputVersion.Trim()) {
        $Version = $InputVersion.Trim()
        Write-Host "输入版本: $Version" -ForegroundColor Green
    } else {
        Write-Host "使用当前版本信息" -ForegroundColor Cyan
    }
}

# 计算脚本与项目根路径（与当前目录无关）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = $ScriptDir
$Root = (Resolve-Path (Join-Path $ScriptDir '..')).Path

# 检查项目根目录（C 版主程序/托盘）
$BuildMainPs1 = (Join-Path $Root 'build_main.ps1')
$BuildTrayPs1 = (Join-Path $Root 'build_tray.ps1')
if (-not (Test-Path $BuildMainPs1) -or -not (Test-Path $BuildTrayPs1)) {
    Write-Host "错误：未找到 C 版构建脚本 build_main.ps1/build_tray.ps1" -ForegroundColor Red
    Write-Host "请在项目根目录包含 build_main.ps1 与 build_tray.ps1" -ForegroundColor Yellow
    Pause-IfNeeded
    exit 1
}

# 切换到项目根目录
Set-Location $Root

# 日志目录（集中保存详细日志，主输出尽量中文）
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-LogSummary {
    param(
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    $summary = [ordered]@{
        Path = $LogPath
        ErrorCount = 0
        WarningCount = 0
        FirstError = $null
        FirstWarning = $null
    }

    if (-not (Test-Path -LiteralPath $LogPath)) {
        return [pscustomobject]$summary
    }

    # 注意：这些关键字匹配主要用于“统计与摘要”，不会修改英文原文日志。
    # 尽量避免宽泛关键字（如“exception”）造成误报，优先匹配工具常见错误标记。
    $errorPatterns = @(
        '(?im)Traceback \(most recent call last\):',
        '(?im)^\s*\d+\s+ERROR:',
        '(?im)^\s*ERROR:',
        '(?im)\bfatal error\b',
        '(?im)(^|\s)error:'
    )
    $warningPatterns = @(
        '(?im)^\s*\d+\s+WARNING:',
        '(?im)^\s*WARNING:',
        '(?im)(^|\s)warning:',
        '(?im)deprecated'
    )

    try {
        foreach ($p in $errorPatterns) {
            $m = Select-String -LiteralPath $LogPath -Pattern $p -AllMatches -ErrorAction SilentlyContinue
            if ($m) {
                $summary.ErrorCount += @($m).Count
                if (-not $summary.FirstError) { $summary.FirstError = @($m)[0].Line }
            }
        }
        foreach ($p in $warningPatterns) {
            $m = Select-String -LiteralPath $LogPath -Pattern $p -AllMatches -ErrorAction SilentlyContinue
            if ($m) {
                $summary.WarningCount += @($m).Count
                if (-not $summary.FirstWarning) { $summary.FirstWarning = @($m)[0].Line }
            }
        }
    } catch {
        # 统计失败不应影响构建
    }

    return [pscustomobject]$summary
}

function Write-ToolLogSummary {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    $s = Get-LogSummary -LogPath $LogPath
    $leaf = Split-Path -Leaf $LogPath
    Write-Host ("  摘要（{0}）：错误 {1} 条，警告 {2} 条。详见 logs\\{3}" -f $Title, $s.ErrorCount, $s.WarningCount, $leaf) -ForegroundColor DarkCyan
    if ($s.FirstError) {
        Write-Host ("  首条错误（英文原文摘录）：{0}" -f $s.FirstError) -ForegroundColor DarkYellow
    } elseif ($s.FirstWarning) {
        Write-Host ("  首条警告（英文原文摘录）：{0}" -f $s.FirstWarning) -ForegroundColor DarkYellow
    }
}

# 兼容：优先使用 pwsh（PowerShell 7+），否则回退到当前会话直接调用
$Pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
function Invoke-ChildBuildScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $false)][string]$CVersion = ""
    )

    if ($Pwsh) {
        if ($CVersion) { & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $ScriptPath -Version $CVersion }
        else { & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $ScriptPath }
    } else {
        if ($CVersion) { & $ScriptPath -Version $CVersion }
        else { & $ScriptPath }
    }
}

function Remove-FileWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Retries = 10,
        [int]$DelayMs = 300
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
            }
            return $true
        } catch {
            Start-Sleep -Milliseconds $DelayMs
        }
    }

    return (-not (Test-Path -LiteralPath $Path))
}

# 资源绝对路径（避免 --specpath 导致的相对路径解析到 installer/）
$ResDir   = Join-Path $Root 'res'
$IconGUI  = Join-Path $ResDir 'icon_GUI.ico'
$TopIco   = Join-Path $ResDir 'top.ico'
# 旧版彩蛋图片 (cd1~cd5) 已不再需要打包，托盘改为仅访问远程随机图片接口。

# 检查Python环境（仅用于：更新版本信息 + 打包 GUI）
Write-Host "[1/7] 检查Python环境（仅 GUI/版本脚本）..." -ForegroundColor Yellow

# 优先检查虚拟环境
$PythonCmd = "python"
if (Test-Path "venv\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: venv" -ForegroundColor Green
    $PythonCmd = "venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: .venv" -ForegroundColor Green
    $PythonCmd = ".venv\Scripts\python.exe"
} elseif (Test-Path "env\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: env" -ForegroundColor Green
    $PythonCmd = "env\Scripts\python.exe"
} elseif ($env:VIRTUAL_ENV) {
    Write-Host "检测到激活的虚拟环境: $env:VIRTUAL_ENV" -ForegroundColor Green
    $PythonCmd = "python"
} else {
    Write-Host "使用系统Python环境" -ForegroundColor Cyan
}

# 检查Python是否可用
try {
    & $PythonCmd --version | Out-Null
} catch {
    Write-Host "错误：未找到Python，请确保Python已安装并添加到PATH，或创建虚拟环境" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}

# 检查PyInstaller
try {
    & $PythonCmd -c "import PyInstaller" 2>$null
} catch {
    Write-Host "错误：PyInstaller未安装，请运行: $PythonCmd -m pip install pyinstaller" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Write-Host "Python环境检查完成" -ForegroundColor Green

# 更新版本信息
Write-Host ""
Write-Host "[2/8] 更新版本信息..." -ForegroundColor Yellow
if ($Version) {
    & $PythonCmd (Join-Path $InstallerDir 'update_version.py') $Version
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误：版本信息更新失败" -ForegroundColor Red
        Pause-IfNeeded
        exit 1
    }
    Write-Host "版本已更新为: $Version" -ForegroundColor Green
} else {
    Write-Host "保持当前版本信息" -ForegroundColor Cyan
}

# 清理旧的构建文件
Write-Host ""
Write-Host "[3/7] 清理旧的构建文件..." -ForegroundColor Yellow
if (Test-Path (Join-Path $InstallerDir 'dist')) { Remove-Item -Path (Join-Path $InstallerDir 'dist') -Recurse -Force }
if (Test-Path (Join-Path $InstallerDir 'build')) { Remove-Item -Path (Join-Path $InstallerDir 'build') -Recurse -Force }
Write-Host "完成清理" -ForegroundColor Green

# 为 dist 准备目录
$DistDir = (Join-Path $InstallerDir 'dist')
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# 注意：不再把 res\top.ico 安装到 {app} 目录。
# 安装器本身的图标仍由 Remote-Controls.iss 的 SetupIconFile=..\res\top.ico 提供。

# 构建 C 版主程序（RC-main.exe）
Write-Host ""
Write-Host "[4/8] 构建 C 版主程序 RC-main.exe..." -ForegroundColor Yellow

# 统一给 C 构建脚本传入形如 V1.2.3 的版本字符串
$CVersion = ""
if ($Version) { $CVersion = $Version } else { $CVersion = "" }
if (-not $CVersion) {
    # 与后续 FinalVersion 一致：如果用户未指定版本，则稍后会从 version_info 解析；
    # 这里先占位，让 build_main/build_tray 自己提示。
    $CVersion = ""
}
if ($CVersion -and -not $CVersion.StartsWith('V')) { $CVersion = "V$CVersion" }

$MainBuildLog = Join-Path $LogDir 'build_main.log'
Write-Host "  详细日志：logs\build_main.log" -ForegroundColor Cyan
if ($CVersion) {
    Invoke-ChildBuildScript -ScriptPath $BuildMainPs1 -CVersion $CVersion *>&1 | Out-File -FilePath $MainBuildLog -Encoding utf8
} else {
    Invoke-ChildBuildScript -ScriptPath $BuildMainPs1 *>&1 | Out-File -FilePath $MainBuildLog -Encoding utf8
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：C 版主程序构建失败" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Write-ToolLogSummary -Title 'C 主程序构建' -LogPath $MainBuildLog

$BuiltMainExe = (Join-Path $Root 'bin\RC-main.exe')
if (-not (Test-Path $BuiltMainExe)) {
    Write-Host "错误：未找到构建产物 $BuiltMainExe" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Copy-Item -LiteralPath $BuiltMainExe -Destination (Join-Path $DistDir 'RC-main.exe') -Force

# ---- 打包 C 主程序的运行时依赖 DLL（例如 Paho MQTT C）----
function Copy-RuntimeDllIfImported {
    param(
        [Parameter(Mandatory = $true)][string]$ExePath,
        [Parameter(Mandatory = $true)][string]$DllName,
        [Parameter(Mandatory = $true)][string]$DestDir
    )

    try {
        $objdumpCmd = Get-Command objdump -ErrorAction SilentlyContinue
        $need = $true
        if ($objdumpCmd) {
            $imports = & $objdumpCmd.Path -p $ExePath 2>$null |
                Select-String -Pattern 'DLL Name:' -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty Line

            $need = $false
            foreach ($line in @($imports)) {
                if ($line -match ([regex]::Escape($DllName))) { $need = $true; break }
            }
        }
        if (-not $need) { return }

        $candidates = @()
        if ($env:PAHO_MQTT_C_ROOT) {
            $candidates += (Join-Path $env:PAHO_MQTT_C_ROOT (Join-Path 'bin' $DllName))
        }
        if ($objdumpCmd) {
            $candidates += (Join-Path (Split-Path -Parent $objdumpCmd.Path) $DllName)
        }
        $candidates += (Join-Path 'C:\msys64\mingw64\bin' $DllName)
        $candidates += (Join-Path 'C:\msys64\ucrt64\bin' $DllName)

        $found = $null
        foreach ($p in $candidates) {
            if ($p -and (Test-Path -LiteralPath $p)) { $found = $p; break }
        }

        if (-not $found) {
            Write-Host ("  警告：检测到依赖 DLL '{0}'，但未找到可复制文件。请确认已安装/可访问 Paho MQTT C (MSYS2) 或设置 PAHO_MQTT_C_ROOT。" -f $DllName) -ForegroundColor Yellow
            return
        }

        Copy-Item -LiteralPath $found -Destination (Join-Path $DestDir $DllName) -Force
        Write-Host ("  已打包依赖 DLL：{0}" -f $DllName) -ForegroundColor Green
    } catch {
        Write-Host ("  警告：尝试打包依赖 DLL '{0}' 失败：{1}" -f $DllName, $_.Exception.Message) -ForegroundColor Yellow
    }
}

Copy-RuntimeDllIfImported -ExePath $BuiltMainExe -DllName 'libpaho-mqtt3c.dll' -DestDir $DistDir

# 打包GUI程序
Write-Host ""
Write-Host "[5/8] 打包GUI程序 RC-GUI.exe..." -ForegroundColor Yellow
$PyInstallerLog = Join-Path $LogDir 'pyinstaller.log'
Write-Host "  详细日志：logs\pyinstaller.log" -ForegroundColor Cyan
& $PythonCmd -m PyInstaller `
    -F -n RC-GUI --noconsole --noconfirm `
    --specpath $InstallerDir `
    --icon=$IconGUI `
    --add-data "$IconGUI;res" `
    --add-data "$TopIco;res" `
    --distpath (Join-Path $InstallerDir 'dist') `
    --workpath (Join-Path $InstallerDir 'build') `
    src\python\GUI.py *>&1 | Out-File -FilePath $PyInstallerLog -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：GUI程序打包失败" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Write-Host "  GUI 打包完成" -ForegroundColor Green
Write-ToolLogSummary -Title 'PyInstaller' -LogPath $PyInstallerLog

# 构建 C 版托盘（RC-tray.exe）
Write-Host ""
Write-Host "[6/8] 构建 C 版托盘程序 RC-tray.exe..." -ForegroundColor Yellow
$TrayBuildLog = Join-Path $LogDir 'build_tray.log'
Write-Host "  详细日志：logs\build_tray.log" -ForegroundColor Cyan
if ($CVersion) {
    Invoke-ChildBuildScript -ScriptPath $BuildTrayPs1 -CVersion $CVersion *>&1 | Out-File -FilePath $TrayBuildLog -Encoding utf8
} else {
    Invoke-ChildBuildScript -ScriptPath $BuildTrayPs1 *>&1 | Out-File -FilePath $TrayBuildLog -Encoding utf8
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：C 版托盘程序构建失败" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Write-ToolLogSummary -Title 'C 托盘构建' -LogPath $TrayBuildLog

$BuiltTrayExe = (Join-Path $Root 'bin\RC-tray.exe')
if (-not (Test-Path $BuiltTrayExe)) {
    Write-Host "错误：未找到构建产物 $BuiltTrayExe" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}
Copy-Item -LiteralPath $BuiltTrayExe -Destination (Join-Path $DistDir 'RC-tray.exe') -Force

# 检查Inno Setup是否安装
Write-Host ""
Write-Host "[7/8] 生成安装包..." -ForegroundColor Yellow

# 确定最终使用的版本号
$FinalVersion = ""
if ($Version) {
    $FinalVersion = $Version
    Write-Host "  使用指定版本：$FinalVersion" -ForegroundColor Cyan
} else {
    # 如果没有指定版本，尝试从 src/python/version_info.py 读取
    $VersionInfoFile = (Join-Path $Root 'src\python\version_info.py')
    if (Test-Path $VersionInfoFile) {
        $VersionInfoContent = Get-Content -Path $VersionInfoFile -Raw

        # 使用 here-string 定义正则，避免在 PowerShell 5.1 中嵌套引号导致解析错误
        $regex = @'
VERSION\s*=\s*(['"])([^'"']+)\1
'@

        if ($VersionInfoContent -match $regex) {
            # 正则中第2个捕获组为实际版本号
            $FinalVersion = $matches[2]
            Write-Host "  从 src/python/version_info.py 检测到版本：$FinalVersion" -ForegroundColor Cyan
        } else {
            $FinalVersion = "0.0.0"
            Write-Host "  警告：无法从 src/python/version_info.py 解析版本号，使用默认版本：$FinalVersion" -ForegroundColor Yellow
        }
    } else {
        $FinalVersion = "0.0.0"
        Write-Host "  警告：未找到 src/python/version_info.py，使用默认版本：$FinalVersion" -ForegroundColor Yellow
    }
}

# 创建临时版本文件供 Inno Setup 读取
$VersionTmpFile = (Join-Path $InstallerDir 'version.tmp')
Set-Content -Path $VersionTmpFile -Value $FinalVersion -Encoding ASCII -NoNewline
Write-Host "  版本信息已写入临时文件：$FinalVersion" -ForegroundColor Green

$InnoPath = "C:\Program Files (x86)\Inno Setup 6\iscc.exe"
if (-not (Test-Path $InnoPath)) {
    Write-Host "错误：未找到 Inno Setup 6，请确保已安装到默认路径" -ForegroundColor Red
    Write-Host "或手动运行：& '$InnoPath' 'installer\Remote-Controls.iss'" -ForegroundColor Yellow
    Pause-IfNeeded
    exit 1
}

# 生成安装包
$IssPath = (Join-Path $InstallerDir 'Remote-Controls.iss')

# 创建临时的Inno Setup脚本，包含版本信息
$TempIssPath = (Join-Path $InstallerDir 'Remote-Controls-temp.iss')
$IssContent = Get-Content -Path $IssPath -Raw
$IssContentWithVersion = "#define MyAppVersion `"$FinalVersion`"`r`n" + $IssContent
$IssEncoding = if ($PSVersionTable.PSVersion.Major -ge 6) { 'utf8BOM' } else { 'utf8' }
Set-Content -Path $TempIssPath -Value $IssContentWithVersion -Encoding $IssEncoding

Write-Host "  生成临时Inno Setup脚本，版本：$FinalVersion" -ForegroundColor Cyan

# 若上一次生成的安装包仍被占用（例如被打开/正在运行），iscc.exe 会以 Error 32 失败。
# 这里提前尝试删除目标输出文件，失败则给出明确提示。
$ExpectedInstallerExe = Join-Path $InstallerDir ("dist\installer\Remote-Controls-Installer-{0}.exe" -f $FinalVersion)
if (Test-Path -LiteralPath $ExpectedInstallerExe) {
    if (-not (Remove-FileWithRetry -Path $ExpectedInstallerExe -Retries 12 -DelayMs 400)) {
        Write-Host "错误：无法覆盖安装包（文件被占用）：$ExpectedInstallerExe" -ForegroundColor Red
        Write-Host "请关闭/退出正在运行的安装程序或资源管理器预览后重试。" -ForegroundColor Yellow
        Pause-IfNeeded
        exit 1
    }
}

$InnoLog = Join-Path $LogDir 'inno_setup.log'
Write-Host "  详细日志：logs\inno_setup.log" -ForegroundColor Cyan
& $InnoPath $TempIssPath *>&1 | Out-File -FilePath $InnoLog -Encoding utf8
$ExitCode = $LASTEXITCODE
Write-ToolLogSummary -Title 'Inno Setup' -LogPath $InnoLog

# 清理临时文件
if (Test-Path $TempIssPath) {
    Remove-Item $TempIssPath -Force
}
if (Test-Path $VersionTmpFile) {
    Remove-Item $VersionTmpFile -Force
}

if ($ExitCode -ne 0) {
    Write-Host "错误：安装包生成失败" -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}

# 清理临时版本文件
$VersionTmpFile = (Join-Path $InstallerDir 'version.tmp')
if (Test-Path $VersionTmpFile) {
    Remove-Item $VersionTmpFile -Force
    Write-Host "  已清理临时版本文件" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "打包完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "EXE 文件位置：installer\dist\" -ForegroundColor Cyan
Write-Host "安装包位置：installer\dist\installer\" -ForegroundColor Cyan
Write-Host "构建版本：$FinalVersion" -ForegroundColor Green
Write-Host ""
Pause-IfNeeded

<#
Remote Controls 项目打包脚本 (PowerShell)
用法：
    - 双击运行（推荐）
    - 或在任意目录执行：pwsh -NoProfile -ExecutionPolicy Bypass -File installer/build_installer.ps1 [版本号]
说明：
    - 脚本使用自身路径解析，不依赖当前工作目录。
#>

param(
    [string]$Version = ""
)

Write-Host "========================================"
Write-Host "Remote Controls 项目打包脚本"
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

# 检查项目根目录
if (-not (Test-Path (Join-Path $Root 'main.py'))) {
    Write-Host "错误：未找到项目根目录或 main.py" -ForegroundColor Red
    Write-Host "请从任意位置运行：pwsh -File installer/build_installer.ps1 [版本号]" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

# 切换到项目根目录
Set-Location $Root

# 资源绝对路径（避免 --specpath 导致的相对路径解析到 installer/）
$ResDir   = Join-Path $Root 'res'
$IconIco  = Join-Path $ResDir 'icon.ico'
$IconGUI  = Join-Path $ResDir 'icon_GUI.ico'
$TopIco   = Join-Path $ResDir 'top.ico'
# 旧版彩蛋图片 (cd1~cd5) 已不再需要打包，托盘改为仅访问远程随机图片接口。

# 检查Python环境
Write-Host "[1/7] 检查Python环境..." -ForegroundColor Yellow

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
    Read-Host "按Enter键退出"
    exit 1
}

# 检查PyInstaller
try {
    & $PythonCmd -c "import PyInstaller" 2>$null
} catch {
    Write-Host "错误：PyInstaller未安装，请运行: $PythonCmd -m pip install pyinstaller" -ForegroundColor Red
    Read-Host "按Enter键退出"
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
        Read-Host "按Enter键退出"
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

# 打包主程序
Write-Host ""
Write-Host "[4/8] 打包主程序 RC-main.exe..." -ForegroundColor Yellow
& $PythonCmd -m PyInstaller `
    -F -n RC-main --windowed --noconfirm `
    --specpath $InstallerDir `
    --icon=$IconIco `
    --add-data "$IconIco;." `
    --distpath (Join-Path $InstallerDir 'dist') `
    --workpath (Join-Path $InstallerDir 'build') `
    main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：主程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 打包GUI程序
Write-Host ""
Write-Host "[5/8] 打包GUI程序 RC-GUI.exe..." -ForegroundColor Yellow
& $PythonCmd -m PyInstaller `
    -F -n RC-GUI --noconsole --noconfirm `
    --specpath $InstallerDir `
    --icon=$IconGUI `
    --add-data "$IconGUI;res" `
    --add-data "$TopIco;res" `
    --distpath (Join-Path $InstallerDir 'dist') `
    --workpath (Join-Path $InstallerDir 'build') `
    GUI.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：GUI程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 打包托盘程序
Write-Host ""
Write-Host "[6/8] 打包托盘程序 RC-tray.exe..." -ForegroundColor Yellow
# 托盘现仅使用 icon.ico 与远程随机图片接口，不再打包本地 cdX.* 彩蛋
& $PythonCmd -m PyInstaller `
    -F -n RC-tray --windowed --noconfirm `
    --icon=$IconIco `
    --add-data "$IconIco;." `
    --distpath (Join-Path $InstallerDir 'dist') `
    --workpath (Join-Path $InstallerDir 'build') `
    tray.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：托盘程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 检查Inno Setup是否安装
Write-Host ""
Write-Host "[7/8] 生成安装包..." -ForegroundColor Yellow

# 确定最终使用的版本号
$FinalVersion = ""
if ($Version) {
    $FinalVersion = $Version
    Write-Host "  使用指定版本：$FinalVersion" -ForegroundColor Cyan
} else {
    # 如果没有指定版本，尝试从 version_info.py 读取
    $VersionInfoFile = (Join-Path $Root 'version_info.py')
    if (Test-Path $VersionInfoFile) {
        $VersionInfoContent = Get-Content -Path $VersionInfoFile -Raw

        # 使用 here-string 定义正则，避免在 PowerShell 5.1 中嵌套引号导致解析错误
        $regex = @'
VERSION\s*=\s*(['"])([^'"']+)\1
'@

        if ($VersionInfoContent -match $regex) {
            # 正则中第2个捕获组为实际版本号
            $FinalVersion = $matches[2]
            Write-Host "  从 version_info.py 检测到版本：$FinalVersion" -ForegroundColor Cyan
        } else {
            $FinalVersion = "0.0.0"
            Write-Host "  警告：无法从 version_info.py 解析版本号，使用默认版本：$FinalVersion" -ForegroundColor Yellow
        }
    } else {
        $FinalVersion = "0.0.0"
        Write-Host "  警告：未找到 version_info.py，使用默认版本：$FinalVersion" -ForegroundColor Yellow
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
    Read-Host "按Enter键退出"
    exit 1
}

# 生成安装包
$IssPath = (Join-Path $InstallerDir 'Remote-Controls.iss')

# 创建临时的Inno Setup脚本，包含版本信息
$TempIssPath = (Join-Path $InstallerDir 'Remote-Controls-temp.iss')
$IssContent = Get-Content -Path $IssPath -Raw
$IssContentWithVersion = "#define MyAppVersion `"$FinalVersion`"`r`n" + $IssContent
Set-Content -Path $TempIssPath -Value $IssContentWithVersion -Encoding UTF8

Write-Host "  生成临时Inno Setup脚本，版本：$FinalVersion" -ForegroundColor Cyan

& $InnoPath $TempIssPath
$ExitCode = $LASTEXITCODE

# 清理临时文件
if (Test-Path $TempIssPath) {
    Remove-Item $TempIssPath -Force
}
if (Test-Path $VersionTmpFile) {
    Remove-Item $VersionTmpFile -Force
}

if ($ExitCode -ne 0) {
    Write-Host "错误：安装包生成失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
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
Read-Host "按Enter键退出"

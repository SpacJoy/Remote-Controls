<#
Remote Controls 项目 Nuitka 打包脚本 (PowerShell)
说明：
  - 生成与 PyInstaller 相同命名的三款 EXE（RC-GUI.exe / RC-main.exe / RC-tray.exe）
  - Nuitka 编译产物目录：installer/build-nuitka（.build 等中间文件集中于此）
  - 最终 EXE 输出目录：installer/dist（与安装器对接不变）
  - 资源打包：GUI(top.ico/icon_GUI.ico)、Main(icon.ico 顶层)、Tray(icon.ico 顶层 + res/cd1~cd5)
  - 可选参数版本号：更新 version_info.py 与 Inno 宏
依赖：
  - Python 3.12+
  - Nuitka（首次运行自动安装）
  - zstandard（建议，提升一体化压缩性能）
使用：
  - 双击根目录 build-nuitka.ps1，或执行：
    pwsh -NoProfile -ExecutionPolicy Bypass -File installer/build_nuitka.ps1 1.0.0
#>
param(
  [string]$Version = ""
)

Write-Host "========================================"
Write-Host "Remote Controls Nuitka 打包脚本" -ForegroundColor Cyan
Write-Host "========================================"

# 解析路径
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = $ScriptDir
$Root         = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$DistDir      = Join-Path $InstallerDir 'dist'
$BuildDir     = Join-Path $InstallerDir 'build-nuitka'

# 校验根目录
if (-not (Test-Path (Join-Path $Root 'main.py'))) {
  Write-Host "错误：未找到项目根目录或 main.py" -ForegroundColor Red
  Read-Host "按Enter键退出"
  exit 1
}
Set-Location $Root

# 选择 Python 解释器（优先已激活的虚拟环境）
$PythonCmd = "python"
if ($env:VIRTUAL_ENV) {
  $venvPy = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
  if (Test-Path $venvPy) { $PythonCmd = $venvPy }
}
if ($PythonCmd -eq 'python') {
  foreach ($venv in @('.venv','venv','env')) {
    $candidate = Join-Path $Root (Join-Path $venv 'Scripts\python.exe')
    if (Test-Path $candidate) { $PythonCmd = $candidate; break }
  }
}
try { & $PythonCmd --version | Out-Null } catch {
  Write-Host "错误：未找到 Python，可在根目录创建虚拟环境后重试" -ForegroundColor Red
  Read-Host "按Enter键退出"; exit 1
}
Write-Host ("使用 Python: " + (& $PythonCmd -c "import sys;print(sys.executable)")) -ForegroundColor Green

# 安装 Nuitka（如缺失）
Write-Host "[1/7] 检查/安装 Nuitka..." -ForegroundColor Yellow
# 通过 -m nuitka --version 验证可用性
& $PythonCmd -m nuitka --version *> $null
$needInstall = ($LASTEXITCODE -ne 0)
if ($needInstall) {
  Write-Host "未检测到 Nuitka，正在安装 nuitka zstandard..." -ForegroundColor Cyan
  & $PythonCmd -m pip install -U nuitka zstandard
  if ($LASTEXITCODE -ne 0) { Write-Host "安装 Nuitka 失败" -ForegroundColor Red; Read-Host "按Enter键退出"; exit 1 }
  # 重新校验
  & $PythonCmd -m nuitka --version *> $null
  if ($LASTEXITCODE -ne 0) { Write-Host "错误：Nuitka 安装后仍不可用，请检查 Python 环境" -ForegroundColor Red; Read-Host "按Enter键退出"; exit 1 }
}
Write-Host "Nuitka 已就绪" -ForegroundColor Green

# 更新版本（可选）
Write-Host "[2/7] 版本信息处理..." -ForegroundColor Yellow
if ($Version) {
  & $PythonCmd (Join-Path $InstallerDir 'update_version.py') $Version
  if ($LASTEXITCODE -ne 0) { Write-Host "版本更新失败" -ForegroundColor Red; Read-Host "按Enter键退出"; exit 1 }
  # 同步 Inno 宏
  $IssFile = (Join-Path $InstallerDir 'Remote-Controls.iss')
  if (Test-Path $IssFile) {
    $Iss = Get-Content -Path $IssFile -Raw
  $Iss = $Iss -replace '#define MyAppVersion "[\d\.]+"', ('#define MyAppVersion "' + $Version + '"')
    Set-Content -Path $IssFile -Value $Iss -Encoding UTF8BOM
  }
  Write-Host "版本同步完成：$Version" -ForegroundColor Green
} else {
  Write-Host "保持 version_info.py 当前版本" -ForegroundColor Cyan
}

# 清理输出目录
Write-Host "[3/7] 准备输出目录..." -ForegroundColor Yellow
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }

# 通用 Nuitka 选项
# 提取版本号为纯字符串，避免数组展开导致参数断裂
$verFile = Join-Path $Root 'version_info.py'
$verRaw  = if (Test-Path $verFile) { Get-Content -Path $verFile -Raw } else { '' }
$verMatch = [regex]::Match($verRaw, 'VERSION\s*=\s*"([^"]+)"')
[string]$FileVersion = if ($verMatch.Success) { $verMatch.Groups[1].Value } else { '1.0.0' }
[string]$BuildDirStr = "$BuildDir"

$Common = @(
  '--onefile',
  '--assume-yes-for-downloads', # 允许自动下载依赖组件
  '--windows-company-name=chen6019',
  '--windows-product-name=Remote Controls',
  "--windows-file-version=$FileVersion",
  '--remove-output',
  "--output-dir=$BuildDirStr"
)

function Invoke-Nuitka {
  param([string]$Entry, [string[]]$Opts)
  Write-Host "  -> nuitka $Entry" -ForegroundColor Cyan
  Write-Host ("     opts: " + ($Opts -join ' ')) -ForegroundColor DarkGray
  & $PythonCmd -m nuitka @Opts $Entry
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka 构建失败：$Entry" -ForegroundColor Red
    Read-Host "按Enter键退出"; exit 1
  }
}

# [4/7] RC-main
Write-Host "[4/7] 打包 RC-main.exe..." -ForegroundColor Yellow
$MainArgs = $Common + @(
  '--windows-console-mode=disable',
  '--windows-icon-from-ico=res\\icon.ico',
  '--include-data-files=res\\icon.ico=icon.ico',
  '--output-filename=RC-main.exe'
)
Invoke-Nuitka -Entry 'main.py' -Opts $MainArgs

# [5/7] RC-GUI
Write-Host "[5/7] 打包 RC-GUI.exe..." -ForegroundColor Yellow
$GuiArgs = $Common + @(
  '--enable-plugin=tk-inter',
  '--windows-console-mode=disable',
  '--windows-icon-from-ico=res\\icon_GUI.ico',
  '--include-data-files=res\\icon_GUI.ico=res\\icon_GUI.ico',
  '--include-data-files=res\\top.ico=res\\top.ico',
  '--output-filename=RC-GUI.exe'
)
Invoke-Nuitka -Entry 'GUI.py' -Opts $GuiArgs

# [6/7] RC-tray (不再包含本地彩蛋图片，仅 icon.ico)
Write-Host "[6/7] 打包 RC-tray.exe..." -ForegroundColor Yellow
$TrayArgs = $Common + @(
  '--follow-imports',
  '--windows-console-mode=disable',
  '--windows-icon-from-ico=res\\icon.ico',
  '--include-data-files=res\\icon.ico=icon.ico',
  '--output-filename=RC-tray.exe'
)
Invoke-Nuitka -Entry 'tray.py' -Opts $TrayArgs

# 将生成的 EXE 从 build-nuitka 移动到 dist
Write-Host "[7/7] 整理输出（移动 EXE 到 dist）..." -ForegroundColor Yellow
$exeMap = @('RC-main.exe','RC-GUI.exe','RC-tray.exe')
foreach ($name in $exeMap) {
  $src = Join-Path $BuildDir $name
  $dst = Join-Path $DistDir $name
  if (Test-Path $src) {
    Move-Item -Force -Path $src -Destination $dst
    Write-Host ("  ✔ " + $name + " -> dist/") -ForegroundColor Green
  } else {
    Write-Host ("  ! 未找到：" + $src) -ForegroundColor Yellow
  }
}

# [7/7] 生成安装包
Write-Host "生成安装包..." -ForegroundColor Yellow
$InnoPath = 'C:\\Program Files (x86)\\Inno Setup 6\\iscc.exe'
if (-not (Test-Path $InnoPath)) {
  Write-Host "警告：未找到 Inno Setup，已跳过安装包生成。EXE 已在 $DistDir" -ForegroundColor Yellow
  Write-Host "完成。" -ForegroundColor Green
  exit 0
}
& $InnoPath (Join-Path $InstallerDir 'Remote-Controls.iss')
if ($LASTEXITCODE -ne 0) {
  Write-Host "错误：安装包生成失败" -ForegroundColor Red
  Read-Host "按Enter键退出"; exit 1
}

Write-Host "========================================" -ForegroundColor Green
Write-Host "Nuitka 构建完成！" -ForegroundColor Green
Write-Host "编译产物（中间文件）：$BuildDir" -ForegroundColor Cyan
Write-Host "最终 EXE：$DistDir" -ForegroundColor Cyan
Write-Host "安装包输出：$(Join-Path $DistDir 'installer')" -ForegroundColor Cyan
Read-Host "按Enter键退出"

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

# 统一编码：避免 PowerShell 5.1 下中文输出出现乱码
try {
  [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [Console]::OutputEncoding
} catch {
}

Write-Host "========================================"
Write-Host "远程控制 Nuitka 打包脚本" -ForegroundColor Cyan
Write-Host "========================================"

# 解析路径
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = $ScriptDir
$Root         = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$DistDir      = Join-Path $InstallerDir 'dist'
$BuildDir     = Join-Path $InstallerDir 'build-nuitka'

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

  # 仅用于“统计与摘要”，不改动英文原文日志；避免宽泛关键字造成误报
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

# 校验根目录
$BuildMainPs1 = (Join-Path $Root 'build_main.ps1')
$BuildTrayPs1 = (Join-Path $Root 'build_tray.ps1')
if (-not (Test-Path $BuildMainPs1) -or -not (Test-Path $BuildTrayPs1)) {
  Write-Host "错误：未找到 C 版构建脚本 build_main.ps1/build_tray.ps1" -ForegroundColor Red
  Read-Host "按Enter键退出"
  exit 1
}
Set-Location $Root

# 兼容：优先 pwsh（PowerShell 7+），否则回退当前 PowerShell
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
    $IssEncoding = if ($PSVersionTable.PSVersion.Major -ge 6) { 'utf8BOM' } else { 'utf8' }
    Set-Content -Path $IssFile -Value $Iss -Encoding $IssEncoding
  }
  Write-Host "版本同步完成：$Version" -ForegroundColor Green
} else {
  Write-Host "保持 version_info.py 当前版本" -ForegroundColor Cyan
}

# 清理输出目录
Write-Host "[3/7] 准备输出目录..." -ForegroundColor Yellow
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }

# 通用 Nuitka 选项（仅用于 GUI）
# 提取版本号为纯字符串，避免数组展开导致参数断裂
$verFile = Join-Path $Root 'src\python\version_info.py'
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
  Write-Host "  执行 Nuitka：$Entry" -ForegroundColor Cyan
  Write-Host ("  参数：" + ($Opts -join ' ')) -ForegroundColor DarkGray

  $safeName = [IO.Path]::GetFileNameWithoutExtension($Entry) -replace '[^a-zA-Z0-9_\-]+','_'
  $nuitkaLog = Join-Path $LogDir ("nuitka_" + $safeName + ".log")
  Write-Host ("  详细日志：logs\\" + (Split-Path -Leaf $nuitkaLog)) -ForegroundColor Cyan

  & $PythonCmd -m nuitka @Opts $Entry *>&1 | Out-File -FilePath $nuitkaLog -Encoding utf8
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka 构建失败：$Entry" -ForegroundColor Red
    Read-Host "按Enter键退出"; exit 1
  }
  Write-ToolLogSummary -Title ("Nuitka: " + $safeName) -LogPath $nuitkaLog
}

# [4/7] 构建 C 版 RC-main / RC-tray
Write-Host "[4/7] 构建 C 版 RC-main.exe / RC-tray.exe..." -ForegroundColor Yellow

$CVersion = ""
if ($Version) { $CVersion = $Version }
if ($CVersion -and -not $CVersion.StartsWith('V')) { $CVersion = "V$CVersion" }

if ($CVersion) {
  $MainBuildLog = Join-Path $LogDir 'build_main.log'
  Write-Host "  详细日志：logs\\build_main.log" -ForegroundColor Cyan
  Invoke-ChildBuildScript -ScriptPath $BuildMainPs1 -CVersion $CVersion *>&1 | Out-File -FilePath $MainBuildLog -Encoding utf8
} else {
  $MainBuildLog = Join-Path $LogDir 'build_main.log'
  Write-Host "  详细日志：logs\\build_main.log" -ForegroundColor Cyan
  Invoke-ChildBuildScript -ScriptPath $BuildMainPs1 *>&1 | Out-File -FilePath $MainBuildLog -Encoding utf8
}
if ($LASTEXITCODE -ne 0) { Write-Host "RC-main C 构建失败" -ForegroundColor Red; Read-Host "按Enter键退出"; exit 1 }
Write-ToolLogSummary -Title 'C 主程序构建' -LogPath $MainBuildLog

if ($CVersion) {
  $TrayBuildLog = Join-Path $LogDir 'build_tray.log'
  Write-Host "  详细日志：logs\\build_tray.log" -ForegroundColor Cyan
  Invoke-ChildBuildScript -ScriptPath $BuildTrayPs1 -CVersion $CVersion *>&1 | Out-File -FilePath $TrayBuildLog -Encoding utf8
} else {
  $TrayBuildLog = Join-Path $LogDir 'build_tray.log'
  Write-Host "  详细日志：logs\\build_tray.log" -ForegroundColor Cyan
  Invoke-ChildBuildScript -ScriptPath $BuildTrayPs1 *>&1 | Out-File -FilePath $TrayBuildLog -Encoding utf8
}
if ($LASTEXITCODE -ne 0) { Write-Host "RC-tray C 构建失败" -ForegroundColor Red; Read-Host "按Enter键退出"; exit 1 }
Write-ToolLogSummary -Title 'C 托盘构建' -LogPath $TrayBuildLog

# 复制 C 构建产物到 dist
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
Copy-Item -LiteralPath (Join-Path $Root 'bin\RC-main.exe') -Destination (Join-Path $DistDir 'RC-main.exe') -Force
Copy-Item -LiteralPath (Join-Path $Root 'bin\RC-tray.exe') -Destination (Join-Path $DistDir 'RC-tray.exe') -Force

# 同步 res\icon.ico（C 版主程序/托盘会用到）
New-Item -ItemType Directory -Force -Path (Join-Path $DistDir 'res') | Out-Null
Copy-Item -LiteralPath (Join-Path $Root 'res\icon.ico') -Destination (Join-Path $DistDir 'res\icon.ico') -Force

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
Invoke-Nuitka -Entry 'src\\python\\GUI.py' -Opts $GuiArgs

# 将生成的 GUI EXE 从 build-nuitka 移动到 dist
Write-Host "[6/7] 整理输出（移动 RC-GUI.exe 到 dist）..." -ForegroundColor Yellow
$exeMap = @('RC-GUI.exe')
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
Write-Host "[7/7] 生成安装包..." -ForegroundColor Yellow
$InnoPath = 'C:\\Program Files (x86)\\Inno Setup 6\\iscc.exe'
if (-not (Test-Path $InnoPath)) {
  Write-Host "警告：未找到 Inno Setup，已跳过安装包生成。EXE 已在 $DistDir" -ForegroundColor Yellow
  Write-Host "完成。" -ForegroundColor Green
  exit 0
}
$InnoLog = Join-Path $LogDir 'inno_setup.log'
Write-Host "  详细日志：logs\\inno_setup.log" -ForegroundColor Cyan
& $InnoPath (Join-Path $InstallerDir 'Remote-Controls.iss') *>&1 | Out-File -FilePath $InnoLog -Encoding utf8
if ($LASTEXITCODE -ne 0) {
  Write-Host "错误：安装包生成失败" -ForegroundColor Red
  Read-Host "按Enter键退出"; exit 1
}
Write-ToolLogSummary -Title 'Inno Setup' -LogPath $InnoLog

Write-Host "========================================" -ForegroundColor Green
Write-Host "Nuitka 构建完成！" -ForegroundColor Green
Write-Host "编译产物（中间文件）：$BuildDir" -ForegroundColor Cyan
Write-Host "最终 EXE：$DistDir" -ForegroundColor Cyan
Write-Host "安装包输出：$(Join-Path $DistDir 'installer')" -ForegroundColor Cyan
Read-Host "按Enter键退出"

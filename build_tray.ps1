param(
  [Parameter(Mandatory = $false)]
  [string]$Version
)

$ErrorActionPreference = 'Stop'

# Force UTF-8 output (helps avoid garbled Chinese in terminals)
try {
  [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}
$OutputEncoding = [Console]::OutputEncoding

function Invoke-Exe {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $false)][string[]]$Arguments = @()
  )

  Write-Host ("`n> {0} {1}" -f $FilePath, ($Arguments -join ' '))
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
    throw "错误：命令执行失败（退出码 ${LASTEXITCODE}）：$FilePath"
  }
}

function Stop-ProcessBestEffort {
  param(
    [Parameter(Mandatory = $true)][string]$ProcessName
  )

  try {
    & taskkill /im "$ProcessName" /f *> $null
  } catch {}
  try {
    Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($ProcessName)) -ErrorAction SilentlyContinue |
      Stop-Process -Force -ErrorAction SilentlyContinue
  } catch {}
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
      return
    } catch {
      Start-Sleep -Milliseconds $DelayMs
    }
  }

  if (Test-Path -LiteralPath $Path) {
    throw "错误: 无法删除/覆盖 $Path，文件可能正在运行或被占用。请先退出托盘程序后重试。"
  }
}

$root = $PSScriptRoot
Set-Location -LiteralPath $root

Write-Host '开始构建远程控制托盘程序...'

if (-not $PSBoundParameters.ContainsKey('Version') -or [string]::IsNullOrWhiteSpace($Version)) {
  $Version = Read-Host '请输入版本号（例如 V1.2.3）'
}
if ([string]::IsNullOrWhiteSpace($Version)) {
  throw '错误: 未提供版本号'
}

Write-Host ("使用版本: {0}" -f $Version)

# Directories
Write-Host '创建必要的目录...'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

# Icon
$iconPath = Join-Path $root 'res\top.ico'
Write-Host '检查图标文件...'
if (-not (Test-Path -LiteralPath $iconPath)) {
  throw '错误: res\top.ico 不存在'
}

# Kill old process first (best-effort), so outputs can be overwritten.
Write-Host '结束可能占用的旧进程...'
Stop-ProcessBestEffort -ProcessName 'RC-tray.exe'
Start-Sleep -Seconds 1

# Clean
Write-Host '清理旧产物...'
$cleanupFiles = @(
  'src\tray\tray.o',
  'src\tray\language.o',
  'src\tray\log_messages.o',
  'src\tray\tray_res.o',
  'src\rc_utils.o',
  'bin\RC-tray.exe'
)
foreach ($rel in $cleanupFiles) {
  $p = Join-Path $root $rel
  Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
}

# Ensure exe can be overwritten (link step will fail if locked)
Remove-FileWithRetry -Path (Join-Path $root 'bin\RC-tray.exe')

# Resources
Write-Host '编译资源文件...'
Invoke-Exe -FilePath 'windres' -Arguments @(
  '-c', '65001',
  'src\tray\tray_unified.rc',
  '-o', 'src\tray\tray_res.o'
)

# Compile
Write-Host '编译源码...'
$commonCFlags = @(
  '-Wall',
  '-O2',
  '-finput-charset=UTF-8',
  '-fexec-charset=UTF-8',
  # PowerShell 调用原生程序时，参数里的双引号可能被“吃掉”。
  # 这里改用 gcc 兼容的 \"...\" 形式，保证宏值是字符串字面量。
  ('-DRC_TRAY_VERSION=\"{0}\"' -f $Version)
)
Invoke-Exe -FilePath 'gcc' -Arguments ($commonCFlags + @('-c', 'src\tray\tray.c', '-o', 'src\tray\tray.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($commonCFlags + @('-c', 'src\tray\language.c', '-o', 'src\tray\language.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($commonCFlags + @('-c', 'src\tray\log_messages.c', '-o', 'src\tray\log_messages.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($commonCFlags + @('-c', 'src\rc_utils.c', '-o', 'src\rc_utils.o'))

# Link
Write-Host '链接...'
Invoke-Exe -FilePath 'gcc' -Arguments @(
  'src\tray\tray.o',
  'src\tray\language.o',
  'src\tray\log_messages.o',
  'src\rc_utils.o',
  'src\tray\tray_res.o',
  '-o', 'bin\RC-tray.exe',
  '-mwindows',
  '-lpsapi', '-lshlwapi', '-lshell32', '-lgdi32', '-luser32', '-ladvapi32', '-lcomctl32', '-lwinhttp'
)

# Copy runtime files
Write-Host '复制资源...'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin\res') | Out-Null
Copy-Item -LiteralPath $iconPath -Destination (Join-Path $root 'bin\res\') -Force

Write-Host '构建成功: bin\RC-tray.exe'

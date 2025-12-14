param(
  [Parameter(Mandatory = $false)]
  [string]$Version,

  [Parameter(Mandatory = $false)]
  [switch]$UsePaho,

  # Root directory that contains include\MQTTClient.h and lib\paho-mqtt3c.*
  [Parameter(Mandatory = $false)]
  [string]$PahoRoot,

  # Library name without -l prefix, e.g. paho-mqtt3c or paho-mqtt3cs
  [Parameter(Mandatory = $false)]
  [string]$PahoLib = 'paho-mqtt3c'
)

$ErrorActionPreference = 'Stop'

try {
  [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
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

  try { & taskkill /im "$ProcessName" /f *> $null } catch {}
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
    throw "错误：无法删除/覆盖 $Path，文件可能正在运行或被占用。请先关闭 RC-main 后重试。"
  }
}

$root = $PSScriptRoot
Set-Location -LiteralPath $root

Write-Host '===== 构建 远程控制 主程序（C/Win32） ====='

if (-not $PSBoundParameters.ContainsKey('Version') -or [string]::IsNullOrWhiteSpace($Version)) {
  $Version = Read-Host '请输入版本号（例如 V1.2.3）'
}
if ([string]::IsNullOrWhiteSpace($Version)) {
  throw '错误: 未提供版本号'
}
Write-Host ("使用版本: {0}" -f $Version)

New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

Write-Host '尝试结束旧进程（尽力而为）...'
Stop-ProcessBestEffort -ProcessName 'RC-main.exe'
Start-Sleep -Seconds 1

Remove-Item -LiteralPath (Join-Path $root 'src\main\main.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_log.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_utf.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_actions.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_router.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_mqtt.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\main\rc_main_tray.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'src\rc_json_main.o') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root 'bin\RC-main.exe') -Force -ErrorAction SilentlyContinue
Remove-FileWithRetry -Path (Join-Path $root 'bin\RC-main.exe')

$flags = @(
  '-Wall','-O2',
  '-DUNICODE','-D_UNICODE',
  '-finput-charset=UTF-8',
  '-fexec-charset=UTF-8',
  ('-DRC_MAIN_VERSION=\"{0}\"' -f $Version)
)

# Auto-enable Paho build if PAHO_MQTT_C_ROOT is set.
if (-not $UsePaho -and [string]::IsNullOrWhiteSpace($PahoRoot)) {
  if (-not [string]::IsNullOrWhiteSpace($env:PAHO_MQTT_C_ROOT)) {
    $PahoRoot = $env:PAHO_MQTT_C_ROOT
    $UsePaho = $true
  }
}

$linkExtra = @()
if ($UsePaho) {
  if ([string]::IsNullOrWhiteSpace($PahoRoot)) {
    throw '错误：指定了 -UsePaho，但 -PahoRoot（或环境变量 PAHO_MQTT_C_ROOT）为空'
  }
  $pahoInclude = Join-Path $PahoRoot 'include'
  $pahoLibDir = Join-Path $PahoRoot 'lib'
  if (-not (Test-Path -LiteralPath $pahoInclude)) {
    throw "错误：未找到 Paho include 目录：$pahoInclude"
  }
  if (-not (Test-Path -LiteralPath $pahoLibDir)) {
    throw "错误：未找到 Paho lib 目录：$pahoLibDir"
  }

  Write-Host ("使用 Paho MQTT C：root={0} lib={1}" -f $PahoRoot, $PahoLib)
  $flags += '-DRC_USE_PAHO_MQTT'
  $flags += ("-I{0}" -f $pahoInclude)
  $linkExtra += ("-L{0}" -f $pahoLibDir)
  $linkExtra += ("-l{0}" -f $PahoLib)
}

Write-Host '编译源码...'
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\rc_json.c','-o','src\rc_json_main.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_log.c','-o','src\main\rc_log.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_utf.c','-o','src\main\rc_utf.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_actions.c','-o','src\main\rc_actions.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_router.c','-o','src\main\rc_router.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_mqtt.c','-o','src\main\rc_mqtt.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\rc_main_tray.c','-o','src\main\rc_main_tray.o'))
Invoke-Exe -FilePath 'gcc' -Arguments ($flags + @('-c','src\main\main.c','-o','src\main\main.o'))

Write-Host '链接...'

$linkArgs = @(
  'src\main\main.o',
  'src\main\rc_log.o',
  'src\main\rc_utf.o',
  'src\main\rc_actions.o',
  'src\main\rc_router.o',
  'src\main\rc_mqtt.o',
  'src\main\rc_main_tray.o',
  'src\rc_json_main.o',
  '-o','bin\RC-main.exe',
  '-mwindows',
  '-municode',
  '-lshlwapi','-lshell32','-luser32',
  '-lole32','-luuid',
  '-ldxva2',
  '-lws2_32'
)

if ($linkExtra -and $linkExtra.Count -gt 0) {
  $linkArgs += $linkExtra
}

Invoke-Exe -FilePath 'gcc' -Arguments $linkArgs


Write-Host '构建成功: bin\RC-main.exe'

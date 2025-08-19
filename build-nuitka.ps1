<#
根目录入口：转发执行 installer/build_nuitka.ps1
#>
param([string]$Version = "")
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Child = Join-Path $ScriptDir 'installer' 'build_nuitka.ps1'
if (-not (Test-Path $Child)) { Write-Host "未找到 $Child" -ForegroundColor Red; exit 1 }
if ($Version) { & pwsh -NoProfile -ExecutionPolicy Bypass -File $Child $Version }
else { & pwsh -NoProfile -ExecutionPolicy Bypass -File $Child }
exit $LASTEXITCODE

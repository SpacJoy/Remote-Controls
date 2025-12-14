<#
根目录入口：转发执行 installer/build_nuitka.ps1
#>
param([string]$Version = "")
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Child = Join-Path $ScriptDir 'installer' 'build_nuitka.ps1'
if (-not (Test-Path $Child)) { Write-Host "未找到 $Child" -ForegroundColor Red; exit 1 }
$Pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
if ($Pwsh) {
	if ($Version) { & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $Child $Version }
	else { & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $Child }
} else {
	if ($Version) { & $Child $Version }
	else { & $Child }
}
exit $LASTEXITCODE

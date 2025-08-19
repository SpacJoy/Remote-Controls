<#
Remote Controls 顶层打包入口（PowerShell）
作用：路径无关地转发到 installer/build_installer.ps1
用法：
  - 双击运行（推荐）
  - 或在任意目录运行：pwsh -NoProfile -ExecutionPolicy Bypass -File build.ps1 [版本号]
#>

param(
    [string]$Version = ""
)

# 解析脚本所在目录与 installer 路径
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerScript = Join-Path $ScriptDir 'installer' 'build_installer.ps1'

if (-not (Test-Path $InstallerScript)) {
    Write-Host "错误：未找到 installer/build_installer.ps1" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 直接调用子脚本，保持 -NoProfile/-ExecutionPolicy 由外部控制
if ($Version) {
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $InstallerScript $Version
} else {
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $InstallerScript
}

exit $LASTEXITCODE

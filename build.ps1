<#
Remote Controls 顶层打包入口（PowerShell）
作用：路径无关地转发到 installer/build_installer.ps1
用法：
  - 双击运行（推荐）
    - 或在任意目录运行：pwsh -NoProfile -ExecutionPolicy Bypass -File build.ps1 [版本号] [-NoPause]
#>

param(
        [string]$Version = "",
        [switch]$NoPause
)

# 解析脚本所在目录与 installer 路径（兼容 WinPS 5.1 的 Join-Path 行为）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = Join-Path $ScriptDir 'installer'
$InstallerScript = Join-Path $InstallerDir 'build_installer.ps1'

if (-not (Test-Path $InstallerScript)) {
    Write-Host "错误：未找到 installer/build_installer.ps1" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

<#
优先使用 pwsh（PowerShell 7+），若不可用则回退到当前会话直接调用脚本，
以兼容 Windows PowerShell 5.1 未安装 pwsh 的环境。
保持 -NoProfile/-ExecutionPolicy 的控制在外层（当使用 pwsh 子进程时）。
#>

$Pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
if ($Pwsh) {
    if ($Version) {
        if ($NoPause) {
            & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $InstallerScript $Version -NoPause
        } else {
            & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $InstallerScript $Version
        }
    } else {
        if ($NoPause) {
            & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $InstallerScript -NoPause
        } else {
            & $Pwsh.Path -NoProfile -ExecutionPolicy Bypass -File $InstallerScript
        }
    }
} else {
    # 未找到 pwsh，直接在当前会话中调用子脚本
    if ($Version) {
        if ($NoPause) {
            & $InstallerScript $Version -NoPause
        } else {
            & $InstallerScript $Version
        }
    } else {
        if ($NoPause) {
            & $InstallerScript -NoPause
        } else {
            & $InstallerScript
        }
    }
}

exit $LASTEXITCODE

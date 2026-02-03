# Remote Controls Python 虚拟环境部署脚本
# 用法: .\setup_python_env.ps1

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

# --- 定义通用函数 ---
function Install-Dependencies {
    param([string]$VenvPath)
    $PythonInVenv = Join-Path $VenvPath "Scripts\python.exe"
    
    if (Test-Path $PythonInVenv) {
        Write-Host "`n正在升级 pip..." -ForegroundColor Yellow
        & $PythonInVenv -m pip install --upgrade pip

        if (Test-Path "requirements.txt") {
            Write-Host "`n正在从 requirements.txt 安装依赖..." -ForegroundColor Yellow
            & $PythonInVenv -m pip install -r requirements.txt
            if ($LASTEXITCODE -eq 0) {
                Write-Host "`n依赖安装完成！" -ForegroundColor Green
            } else {
                Write-Error "`n依赖安装过程中出现错误。"
                exit 1
            }
        } else {
            Write-Host "`n未找到 requirements.txt，跳过依赖安装。" -ForegroundColor Gray
        }
    } else {
        Write-Error "无法在虚拟环境中找到 python 可执行文件。"
        exit 1
    }
}

function Get-SystemPythons {
    param([string]$CurrentBaseDir)
    Write-Host "`n正在查找系统中的 Python 可执行文件..." -ForegroundColor Yellow
    $Paths = @()
    # 0. 优先尝试加入当前虚拟环境依赖的路径
    if ($CurrentBaseDir -and (Test-Path (Join-Path $CurrentBaseDir "python.exe"))) {
        $Paths += Join-Path $CurrentBaseDir "python.exe"
    }

    # 1. 从 PATH 环境变量中查找所有 python.exe
    $PathsFromPath = Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source }
    if ($PathsFromPath) { $Paths += $PathsFromPath }

    # 1.1 显式检查 PATH 中的每一个目录（防止 Get-Command 漏掉某些别名或特殊情况）
    $envPathDirs = $env:PATH -split ';'
    foreach ($dir in $envPathDirs) {
        $trimmedDir = $dir.Trim()
        if ($trimmedDir -and (Test-Path $trimmedDir)) {
            $potentialExe = Join-Path $trimmedDir "python.exe"
            if (Test-Path $potentialExe) {
                $Paths += $potentialExe
            }
        }
    }

    # 2. 常见安装路径
    $CommonPatterns = @(
        "C:\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:LOCALAPPDATA\Python\*\python.exe", # 覆盖用户提到的路径
        "$env:ProgramFiles\Python3*\python.exe",
        "$env:ProgramFiles\Python\*\python.exe"
    )
    foreach ($pattern in $CommonPatterns) {
        $found = Resolve-Path $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }
        if ($found) { $Paths += $found }
    }
    return $Paths | Select-Object -Unique
}

function Show-PythonList {
    param($PythonPaths)
    if ($PythonPaths.Count -eq 0) {
        Write-Host "未在系统中找到 Python。请确保已安装 Python。" -ForegroundColor Red
        return
    }
    Write-Host "`n系统中的 Python 解释器列表:" -ForegroundColor White
    for ($i = 0; $i -lt $PythonPaths.Count; $i++) {
        $path = $PythonPaths[$i]
        $ver = "未知版本"
        $linkHint = ""
        
        try {
            $item = Get-Item $path -ErrorAction SilentlyContinue
            if ($item) {
                # 检测是否为符号链接或重解析点 (ReparsePoint)
                if ($item.Attributes -match "ReparsePoint") {
                    $target = $item.Target
                    if ($target) {
                        $linkHint = "[链接 -> $target]"
                    } else {
                        $linkHint = "[应用执行别名/链接]"
                    }
                }
            }
            $ver = & $path --version 2>&1
        } catch {
            $ver = "获取版本失败"
        }
        
        if ($linkHint) {
            Write-Host "[$i] $path ($ver) " -NoNewline
            Write-Host $linkHint -ForegroundColor Gray
        } else {
            Write-Host "[$i] $path ($ver)"
        }
    }
}

Write-Host "===== Remote Controls Python 环境管理 =====" -ForegroundColor Cyan

# --- 1. 获取并显示当前虚拟环境信息 ---
$VenvPath = Join-Path $Root ".venv"
$VenvExists = Test-Path $VenvPath

$NeedsRedeploy = $false
$CurrentVenvBaseDir = $null

if ($VenvExists) {
    while ($true) {
        Write-Host "`n[检测到现有虚拟环境]" -ForegroundColor Yellow
        $PythonInVenv = Join-Path $VenvPath "Scripts\python.exe"
        if (Test-Path $PythonInVenv) {
            $vVersion = & $PythonInVenv --version 2>&1
            Write-Host "位置: $VenvPath"
            Write-Host "版本: $vVersion"
            
            # 获取基础 Python 目录 (从 pyvenv.cfg)
            $CfgPath = Join-Path $VenvPath "pyvenv.cfg"
            if (Test-Path $CfgPath) {
                $CurrentVenvBaseDir = Get-Content $CfgPath | Select-String -Pattern "^home =" | ForEach-Object { $_.ToString().Split("=")[1].Trim() }
                if ($CurrentVenvBaseDir) {
                    Write-Host "依赖的 Python 目录: $CurrentVenvBaseDir" -ForegroundColor Gray
                }
            }
            
            Write-Host "`n已安装的依赖包 (部分):" -ForegroundColor Gray
            & $PythonInVenv -m pip list --format freeze | Select-Object -First 5 | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }
            Write-Host "  ... (更多请运行 pip list)" -ForegroundColor Gray
        } else {
            Write-Host "警告: 找到 .venv 目录但未找到 python.exe，环境可能已损坏。" -ForegroundColor Red
        }

        Write-Host "`n选项:" -ForegroundColor White
        Write-Host "[1] 重新部署 (删除并重建虚拟环境)"
        Write-Host "[2] 仅更新依赖 (在当前环境中运行 pip install)"
        Write-Host "[3] 查看系统中所有 Python 信息"
        Write-Host "[Q] 退出"
        
        $action = Read-Host "`n请选择操作 (默认 Q)"
        if ($action -eq "1") {
            Write-Host "正在删除旧的虚拟环境..." -ForegroundColor Gray
            Remove-Item -Path $VenvPath -Recurse -Force
            $NeedsRedeploy = $true
            break
        } elseif ($action -eq "2") {
            Install-Dependencies -VenvPath $VenvPath
            Write-Host "`n===== 任务完成 =====" -ForegroundColor Cyan
            exit 0
        } elseif ($action -eq "3") {
            $pPaths = Get-SystemPythons -CurrentBaseDir $CurrentVenvBaseDir
            Show-PythonList -PythonPaths $pPaths
            Write-Host "`n按任意键返回菜单..."
            [void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            Clear-Host
            Write-Host "===== Remote Controls Python 环境管理 =====" -ForegroundColor Cyan
            continue
        } else {
            Write-Host "已退出。"
            exit 0
        }
    }
} else {
    Write-Host "`n未检测到虚拟环境 (.venv)。" -ForegroundColor Gray
    $NeedsRedeploy = $true
}

if ($NeedsRedeploy) {
    # --- 2. 查找并选择 Python ---
    $PythonPaths = Get-SystemPythons -CurrentBaseDir $CurrentVenvBaseDir
    
    if ($PythonPaths.Count -eq 0) {
        Write-Host "未在系统中找到 Python。请确保已安装 Python。" -ForegroundColor Red
        $choice = 'M'
    } else {
        Show-PythonList -PythonPaths $PythonPaths
        Write-Host "[M] 手动输入路径"
        Write-Host "[Q] 退出"
        $choice = Read-Host "`n请输入选项 (默认 0)"
        if ($choice -eq "") { $choice = "0" }
    }

    $SelectedPython = $null

    if ($choice -eq 'M' -or $choice -eq 'm') {
        $manualPath = Read-Host "请输入 python.exe 的完整路径"
        if (Test-Path $manualPath) {
            $SelectedPython = $manualPath
        } else {
            Write-Error "路径不存在: $manualPath"
            exit 1
        }
    } elseif ($choice -eq 'Q' -or $choice -eq 'q') {
        Write-Host "已退出。"
        exit 0
    } elseif ($choice -match '^\d+$' -and [int]$choice -lt $PythonPaths.Count) {
        $SelectedPython = $PythonPaths[[int]$choice]
    } else {
        Write-Error "无效的选择。"
        exit 1
    }

    Write-Host "`n已选择: $SelectedPython" -ForegroundColor Green

    # --- 3. 创建虚拟环境 ---
    Write-Host "正在创建虚拟 environment..." -ForegroundColor Yellow
    & $SelectedPython -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "创建虚拟环境失败。"
        exit 1
    }
    Write-Host "虚拟环境创建成功。" -ForegroundColor Green

    # --- 4. 安装依赖 ---
    Install-Dependencies -VenvPath $VenvPath

    Write-Host "`n===== 任务完成 =====" -ForegroundColor Cyan
    Write-Host "激活环境命令:" -ForegroundColor White
    Write-Host "  PowerShell: .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host "  CMD:        .\.venv\Scripts\activate.bat" -ForegroundColor Gray
}

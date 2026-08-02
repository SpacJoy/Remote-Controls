# Remote Controls Python 虚拟环境部署脚本
# 用法: .\setup_python_env.ps1
# 适配场景: 重装系统后 venv 仍存在但基座 Python 路径/版本变化

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

    # 0. 优先尝试加入当前虚拟环境依赖的路径（如果仍有效）
    if ($CurrentBaseDir -and (Test-Path (Join-Path $CurrentBaseDir "python.exe"))) {
        $Paths += Join-Path $CurrentBaseDir "python.exe"
    }

    # 1. 通过 py launcher 枚举已安装版本（最可靠的方式，重装系统后通常可用）
    try {
        $pyExe = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pyExe) {
            $pyList = & py.exe -0p 2>&1
            if ($pyList) {
                foreach ($line in $pyList) {
                    if ($line -match '^[-\s]*V?(\d+\.\d+)\s*(-32)?\s*:\s*(.+)$') {
                        $candidate = $Matches[3].Trim()
                        if ($candidate -and (Test-Path $candidate)) {
                            $Paths += $candidate
                        }
                    }
                }
            }
        }
    } catch {
        # 忽略 py launcher 的错误，继续用其他方式查找
    }

    # 2. 从 PATH 环境变量中查找所有 python.exe
    $PathsFromPath = Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source }
    if ($PathsFromPath) { $Paths += $PathsFromPath }

    # 2.1 显式检查 PATH 中的每一个目录（防止 Get-Command 漏掉某些别名或特殊情况）
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

    # 3. 常见安装路径（覆盖重装系统后的各种安装方式）
    $CommonPatterns = @(
        "C:\Python3*\python.exe",
        "C:\Python*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:LOCALAPPDATA\Python\*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe",
        "$env:ProgramFiles\Python\*\python.exe",
        "${env:ProgramFiles(x86)}\Python3*\python.exe",
        "${env:ProgramFiles(x86)}\Python\*\python.exe",
        "$env:APPDATA\Python\*\python.exe"
    )
    foreach ($pattern in $CommonPatterns) {
        $found = Resolve-Path $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }
        if ($found) { $Paths += $found }
    }

    # 4. Microsoft Store / Windows Apps Python 路径
    $storePatterns = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.exe"
    )
    foreach ($p in $storePatterns) {
        if (Test-Path $p) { $Paths += $p }
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
        $isBroken = $false

        try {
            $item = Get-Item $path -ErrorAction SilentlyContinue
            if ($item) {
                if ($item.Attributes -match "ReparsePoint") {
                    $target = $item.Target
                    if ($target) {
                        $linkHint = "[链接 -> $target]"
                    } else {
                        $linkHint = "[应用执行别名/链接]"
                    }
                }
            }
            $verOutput = & $path --version 2>&1
            if ($LASTEXITCODE -ne 0 -or $verOutput -match "(No Python at|Fatal error|cannot find the file)") {
                $isBroken = $true
                $ver = "不可用 - $verOutput"
            } else {
                $ver = $verOutput
            }
        } catch {
            $isBroken = $true
            $ver = "获取版本失败 - $($_.Exception.Message)"
        }

        $displayVer = if ($isBroken) { "($ver)" } else { "($ver)" }
        if ($isBroken) {
            Write-Host "[$i] $path " -NoNewline
            Write-Host $displayVer -ForegroundColor Red -NoNewline
            if ($linkHint) { Write-Host " $linkHint" -ForegroundColor Gray } else { Write-Host "" }
        } elseif ($linkHint) {
            Write-Host "[$i] $path $displayVer " -NoNewline
            Write-Host $linkHint -ForegroundColor Gray
        } else {
            Write-Host "[$i] $path $displayVer"
        }
    }
}

function Test-VenvHealth {
    param([string]$VenvPath)
    $result = @{
        IsHealthy = $false
        PythonExists = $false
        PythonRunnable = $false
        BaseDirExists = $false
        BaseDir = $null
        Issues = @()
        Version = $null
    }

    $PythonInVenv = Join-Path $VenvPath "Scripts\python.exe"
    $CfgPath = Join-Path $VenvPath "pyvenv.cfg"

    # 1. 检查 python.exe 文件是否存在
    if (Test-Path $PythonInVenv) {
        $result.PythonExists = $true
    } else {
        $result.Issues += "未找到 Scripts\python.exe 文件"
    }

    # 2. 读取并检查 pyvenv.cfg 中的 home 路径
    if (Test-Path $CfgPath) {
        $result.BaseDir = Get-Content $CfgPath | Select-String -Pattern "^home =" | ForEach-Object { $_.ToString().Split("=")[1].Trim() }
        if ($result.BaseDir) {
            if (Test-Path (Join-Path $result.BaseDir "python.exe")) {
                $result.BaseDirExists = $true
            } else {
                $result.Issues += "基座 Python 路径不存在: $($result.BaseDir)（重装系统后常见问题）"
            }
        } else {
            $result.Issues += "pyvenv.cfg 中未找到 home 配置"
        }
    } else {
        $result.Issues += "未找到 pyvenv.cfg 配置文件"
    }

    # 3. 尝试实际执行 python.exe --version（最关键的检测）
    if ($result.PythonExists) {
        try {
            $verOutput = & $PythonInVenv --version 2>&1
            if ($LASTEXITCODE -eq 0 -and -not ($verOutput -match "(No Python at|Fatal error|cannot find the file|找不到)")) {
                $result.PythonRunnable = $true
                $result.Version = $verOutput.ToString().Trim()
            } else {
                $result.Issues += "venv 解释器无法运行: $verOutput（可能是基座 Python 路径/版本变化，或启动器固化了旧路径）"
            }
        } catch {
            $result.Issues += "venv 解释器运行异常: $($_.Exception.Message)"
        }
    }

    # 综合判定健康状态
    $result.IsHealthy = $result.PythonExists -and $result.PythonRunnable -and $result.BaseDirExists
    return $result
}

Write-Host "===== Remote Controls Python 环境管理 =====" -ForegroundColor Cyan

# --- 1. 获取并检测当前虚拟环境健康状态 ---
$VenvPath = Join-Path $Root ".venv"
$VenvExists = Test-Path $VenvPath

$NeedsRedeploy = $false
$CurrentVenvBaseDir = $null
$VenvHealth = $null

if ($VenvExists) {
    $VenvHealth = Test-VenvHealth -VenvPath $VenvPath
    $CurrentVenvBaseDir = $VenvHealth.BaseDir

    while ($true) {
        Write-Host "`n[检测到现有虚拟环境]" -ForegroundColor Yellow
        Write-Host "位置: $VenvPath"

        if ($VenvHealth.IsHealthy) {
            Write-Host "状态: " -NoNewline
            Write-Host "正常" -ForegroundColor Green
            Write-Host "版本: $($VenvHealth.Version)"
            if ($CurrentVenvBaseDir) {
                Write-Host "依赖的 Python 目录: $CurrentVenvBaseDir" -ForegroundColor Gray
            }
            Write-Host "`n已安装的依赖包 (部分):" -ForegroundColor Gray
            $PythonInVenv = Join-Path $VenvPath "Scripts\python.exe"
            & $PythonInVenv -m pip list --format freeze 2>$null | Select-Object -First 5 | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }
            Write-Host "  ... (更多请运行 pip list)" -ForegroundColor Gray

            Write-Host "`n选项:" -ForegroundColor White
            Write-Host "[1] 重新部署 (删除并重建虚拟环境)"
            Write-Host "[2] 仅更新依赖 (在当前环境中运行 pip install) [推荐]"
            Write-Host "[3] 查看系统中所有 Python 信息"
            Write-Host "[Q] 退出"
            $defaultAction = "2"
        } else {
            Write-Host "状态: " -NoNewline
            Write-Host "异常/损坏" -ForegroundColor Red
            if ($VenvHealth.Version) {
                Write-Host "版本: $($VenvHealth.Version)"
            }
            if ($CurrentVenvBaseDir) {
                Write-Host "记录的基座 Python 目录: $CurrentVenvBaseDir" -ForegroundColor Gray
            }
            Write-Host "`n检测到的问题:" -ForegroundColor Red
            foreach ($issue in $VenvHealth.Issues) {
                Write-Host "  ! $issue" -ForegroundColor Red
            }
            Write-Host "`n提示: 这通常发生在重装系统后，原基座 Python 路径/版本发生变化，" -ForegroundColor Yellow
            Write-Host "      或 venv 启动器固化了旧的绝对路径。建议重新部署。" -ForegroundColor Yellow

            Write-Host "`n选项:" -ForegroundColor White
            Write-Host "[1] 重新部署 (删除并重建虚拟环境) [推荐]"
            Write-Host "[2] 尝试仅更新依赖 (不推荐，当前环境可能无法执行)"
            Write-Host "[3] 查看系统中所有 Python 信息"
            Write-Host "[Q] 退出"
            $defaultAction = "1"
        }

        $prompt = "`n请选择操作 (默认 $defaultAction)"
        $action = Read-Host $prompt
        if ($action -eq "") { $action = $defaultAction }

        if ($action -eq "1") {
            Write-Host "正在删除旧的虚拟环境..." -ForegroundColor Gray
            Remove-Item -Path $VenvPath -Recurse -Force
            $NeedsRedeploy = $true
            break
        } elseif ($action -eq "2") {
            if (-not $VenvHealth.PythonRunnable) {
                Write-Host "`n警告: 当前 venv 解释器无法运行，直接更新依赖很可能失败。" -ForegroundColor Yellow
                $confirm = Read-Host "是否仍要继续? (y/N)"
                if ($confirm -notmatch '^[Yy]$') {
                    Write-Host "已取消，建议选择 [1] 重新部署。"
                    continue
                }
            }
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
        Write-Host "`n未在系统中找到 Python。请确保已安装 Python。" -ForegroundColor Red
        Write-Host "可从以下方式获取 Python:" -ForegroundColor Yellow
        Write-Host "  - 官网: https://www.python.org/downloads/"
        Write-Host "  - Microsoft Store: 搜索 'Python 3.10' 或更高版本"
        Write-Host "  - 或使用 py launcher 管理多版本"
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

    # 选择后再做一次可执行性检查
    try {
        $checkVer = & $SelectedPython --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`n警告: 所选 Python 无法正常运行: $checkVer" -ForegroundColor Yellow
            $confirm = Read-Host "是否仍继续? (y/N)"
            if ($confirm -notmatch '^[Yy]$') {
                Write-Host "已取消。"
                exit 0
            }
        } else {
            Write-Host "`n已选择: $SelectedPython ($checkVer)" -ForegroundColor Green
        }
    } catch {
        Write-Host "`n警告: 所选 Python 无法执行: $($_.Exception.Message)" -ForegroundColor Yellow
        $confirm = Read-Host "是否仍继续? (y/N)"
        if ($confirm -notmatch '^[Yy]$') {
            Write-Host "已取消。"
            exit 0
        }
    }

    # --- 3. 创建虚拟环境 ---
    Write-Host "`n正在创建虚拟环境..." -ForegroundColor Yellow
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

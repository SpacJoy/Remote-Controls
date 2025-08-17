#!/bin/bash

# Remote Controls 项目打包脚本 (PowerShell版本)
# 使用方法：在项目根目录运行 .\build_installer.ps1

Write-Host "========================================"
Write-Host "Remote Controls 项目打包脚本"
Write-Host "========================================"
Write-Host ""

# 检查Python环境
Write-Host "[1/6] 检查Python环境..." -ForegroundColor Yellow

# 优先检查虚拟环境
$PythonCmd = "python"
if (Test-Path "venv\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: venv" -ForegroundColor Green
    $PythonCmd = "venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: .venv" -ForegroundColor Green
    $PythonCmd = ".venv\Scripts\python.exe"
} elseif (Test-Path "env\Scripts\python.exe") {
    Write-Host "检测到虚拟环境: env" -ForegroundColor Green
    $PythonCmd = "env\Scripts\python.exe"
} elseif ($env:VIRTUAL_ENV) {
    Write-Host "检测到激活的虚拟环境: $env:VIRTUAL_ENV" -ForegroundColor Green
    $PythonCmd = "python"
} else {
    Write-Host "使用系统Python环境" -ForegroundColor Cyan
}

# 检查Python是否可用
try {
    & $PythonCmd --version | Out-Null
} catch {
    Write-Host "错误：未找到Python，请确保Python已安装并添加到PATH，或创建虚拟环境" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 检查PyInstaller
try {
    & $PythonCmd -c "import PyInstaller" 2>$null
} catch {
    Write-Host "错误：PyInstaller未安装，请运行: $PythonCmd -m pip install pyinstaller" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}
Write-Host "Python环境检查完成" -ForegroundColor Green

# 清理旧的构建文件
Write-Host ""
Write-Host "[2/6] 清理旧的构建文件..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Path "dist" -Recurse -Force }
if (Test-Path "build") { Remove-Item -Path "build" -Recurse -Force }
Write-Host "完成清理" -ForegroundColor Green

# 打包主程序
Write-Host ""
Write-Host "[3/6] 打包主程序 RC-main.exe..." -ForegroundColor Yellow
& $PythonCmd -m PyInstaller RC-main.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：主程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 打包GUI程序
Write-Host ""
Write-Host "[4/6] 打包GUI程序 RC-GUI.exe..." -ForegroundColor Yellow
& $PythonCmd -m PyInstaller RC-GUI.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：GUI程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 打包托盘程序
Write-Host ""
Write-Host "[5/6] 打包托盘程序 RC-tray.exe..." -ForegroundColor Yellow
& $PythonCmd -m PyInstaller RC-tray.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：托盘程序打包失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

# 检查Inno Setup是否安装
Write-Host ""
Write-Host "[6/6] 生成安装包..." -ForegroundColor Yellow
$InnoPath = "C:\Program Files (x86)\Inno Setup 6\iscc.exe"
if (-not (Test-Path $InnoPath)) {
    Write-Host "错误：未找到 Inno Setup 6，请确保已安装到默认路径" -ForegroundColor Red
    Write-Host "或手动运行：& '$InnoPath' 'installer\Remote-Controls.iss'" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

# 生成安装包
& $InnoPath "installer\Remote-Controls.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：安装包生成失败" -ForegroundColor Red
    Read-Host "按Enter键退出"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "打包完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "EXE 文件位置：dist\" -ForegroundColor Cyan
Write-Host "安装包位置：dist\installer\" -ForegroundColor Cyan
Write-Host ""
Read-Host "按Enter键退出"

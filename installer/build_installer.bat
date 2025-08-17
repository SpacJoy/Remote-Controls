@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ========================================
echo Remote Controls 项目打包脚本
echo ========================================
echo.

:: 解析版本参数
set "BUILD_VERSION="
if not "%~1"=="" (
    set "BUILD_VERSION=%~1"
    echo 指定版本: %BUILD_VERSION%
) else (
    echo.
    echo 请输入版本号 (格式: X.Y.Z，如 2.3.0)
    echo 留空使用当前版本信息
    set /p "BUILD_VERSION=版本号: "
    if not "!BUILD_VERSION!"=="" (
        echo 输入版本: !BUILD_VERSION!
    ) else (
        echo 使用当前版本信息
    )
)

:: 检查是否在正确的目录
if not exist "..\main.py" (
    powershell -Command "Write-Host '错误：请在项目根目录的installer文件夹中运行此脚本' -ForegroundColor Red"
    echo 或者运行: cd installer && .\build_installer.bat
    pause
    exit /b 1
)

:: 设置工作目录为项目根目录
cd ..

:: 检查Python环境
echo [1/7] 检查Python环境...

:: 优先检查虚拟环境
set "PYTHON_CMD=python"
if exist "venv\Scripts\python.exe" (
    echo 检测到虚拟环境: venv
    set "PYTHON_CMD=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    echo 检测到虚拟环境: .venv
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else if exist "env\Scripts\python.exe" (
    echo 检测到虚拟环境: env
    set "PYTHON_CMD=env\Scripts\python.exe"
) else if defined VIRTUAL_ENV (
    echo 检测到激活的虚拟环境: %VIRTUAL_ENV%
    set "PYTHON_CMD=python"
) else (
    echo 使用系统Python环境
)

%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    powershell -Command "Write-Host '错误：未找到Python，请确保Python已安装并添加到PATH，或创建虚拟环境' -ForegroundColor Red"
    pause
    exit /b 1
)

:: 检查PyInstaller
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    powershell -Command "Write-Host '错误：PyInstaller未安装，请运行: %PYTHON_CMD% -m pip install pyinstaller' -ForegroundColor Red"
    pause
    exit /b 1
)
echo Python环境检查完成

:: 更新版本信息
echo.
echo [2/8] 更新版本信息...
if not "!BUILD_VERSION!"=="" (
    %PYTHON_CMD% installer\update_version.py !BUILD_VERSION!
    if errorlevel 1 (
        powershell -Command "Write-Host '错误：版本信息更新失败' -ForegroundColor Red"
        pause
        exit /b 1
    )
    echo 版本已更新为: !BUILD_VERSION!
) else (
    echo 保持当前版本信息
)

:: 清理旧的构建文件
echo.
echo [3/7] 清理旧的构建文件...
if exist "installer\dist" rmdir /s /q "installer\dist"
if exist "installer\build" rmdir /s /q "installer\build"
echo 完成清理

:: 打包主程序
echo.
echo [4/8] 打包主程序 RC-main.exe...
%PYTHON_CMD% -m PyInstaller installer\RC-main.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    powershell -Command "Write-Host '错误：主程序打包失败' -ForegroundColor Red"
    pause
    exit /b 1
)

:: 打包GUI程序
echo.
echo [5/8] 打包GUI程序 RC-GUI.exe...
%PYTHON_CMD% -m PyInstaller installer\RC-GUI.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    powershell -Command "Write-Host '错误：GUI程序打包失败' -ForegroundColor Red"
    pause
    exit /b 1
)

:: 打包托盘程序
echo.
echo [6/8] 打包托盘程序 RC-tray.exe...
%PYTHON_CMD% -m PyInstaller installer\RC-tray.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    powershell -Command "Write-Host '错误：托盘程序打包失败' -ForegroundColor Red"
    pause
    exit /b 1
)

:: 检查Inno Setup是否安装
echo.
echo [7/8] 生成安装包...

:: 首先更新 Inno Setup 脚本中的版本号
if not "!BUILD_VERSION!"=="" (
    echo   更新安装脚本版本号：!BUILD_VERSION!
    if exist "installer\Remote-Controls.iss" (
        powershell -Command "(Get-Content 'installer\Remote-Controls.iss' -Raw) -replace '#define MyAppVersion \"[\d\.]+\"', '#define MyAppVersion \"!BUILD_VERSION!\"' | Set-Content 'installer\Remote-Controls.iss' -Encoding UTF8"
        echo   版本号已更新到安装脚本
    ) else (
        echo   警告：未找到安装脚本文件
    )
)

set "INNO_PATH=C:\Program Files (x86)\Inno Setup 6\iscc.exe"
if not exist "%INNO_PATH%" (
    powershell -Command "Write-Host '错误：未找到 Inno Setup 6，请确保已安装到默认路径' -ForegroundColor Red"
    echo 或手动运行："%INNO_PATH%" "installer\Remote-Controls.iss"
    pause
    exit /b 1
)

:: 生成安装包
"%INNO_PATH%" "installer\Remote-Controls.iss"
if errorlevel 1 (
    powershell -Command "Write-Host '错误：安装包生成失败' -ForegroundColor Red"
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo EXE 文件位置：installer\dist\
echo 安装包位置：installer\dist\installer\
if not "!BUILD_VERSION!"=="" (
    echo 构建版本：!BUILD_VERSION!
)
echo.
echo 按任意键退出...
pause >nul

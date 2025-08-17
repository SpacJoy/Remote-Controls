@echo off
chcp 65001 >nul
echo ====================================# 检查Inno Setup是否安装
echo.
echo [6/6] 生成安装包...
set "INNO_PATH=C:\Program Files (x86)\Inno Setup 6\iscc.exe"
echo Remote Controls 项目打包脚本
echo ========================================
echo.

:: 检查是否在正确的目录
if not exist "main.py" (
    echo 错误：请在项目根目录运行此脚本
    pause
    exit /b 1
)

:: 检查Python环境
echo [1/6] 检查Python环境...

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
    echo 错误：未找到Python，请确保Python已安装并添加到PATH，或创建虚拟环境
    pause
    exit /b 1
)

:: 检查PyInstaller
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo 错误：PyInstaller未安装，请运行: %PYTHON_CMD% -m pip install pyinstaller
    pause
    exit /b 1
)
echo Python环境检查完成

:: 清理旧的构建文件
echo.
echo [2/6] 清理旧的构建文件...
if exist "installer\dist" rmdir /s /q "installer\dist"
if exist "installer\build" rmdir /s /q "installer\build"
echo 完成清理

:: 打包主程序
echo.
echo [3/6] 打包主程序 RC-main.exe...
%PYTHON_CMD% -m PyInstaller RC-main.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    echo 错误：主程序打包失败
    pause
    exit /b 1
)

:: 打包GUI程序
echo.
echo [4/6] 打包GUI程序 RC-GUI.exe...
%PYTHON_CMD% -m PyInstaller RC-GUI.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    echo 错误：GUI程序打包失败
    pause
    exit /b 1
)

:: 打包托盘程序
echo.
echo [5/6] 打包托盘程序 RC-tray.exe...
%PYTHON_CMD% -m PyInstaller RC-tray.spec --noconfirm --distpath installer\dist --workpath installer\build
if errorlevel 1 (
    echo 错误：托盘程序打包失败
    pause
    exit /b 1
)

:: 检查Inno Setup是否安装
echo.
echo [5/5] 生成安装包...
set "INNO_PATH=C:\Program Files (x86)\Inno Setup 6\iscc.exe"
if not exist "%INNO_PATH%" (
    echo 错误：未找到 Inno Setup 6，请确保已安装到默认路径
    echo 或手动运行："%INNO_PATH%" "installer\Remote-Controls.iss"
    pause
    exit /b 1
)

:: 生成安装包
"%INNO_PATH%" "installer\Remote-Controls.iss"
if errorlevel 1 (
    echo 错误：安装包生成失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo EXE 文件位置：installer\dist\
echo 安装包位置：installer\dist\installer\
echo.
echo 按任意键退出...
pause >nul

@echo off
setlocal
:: Remote Controls 项目快速打包脚本（双击可用）
:: 始终以脚本所在目录为基准，调用 installer 下的打包脚本

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul 2>&1

echo ========================================
echo Remote Controls 快速打包工具
echo ========================================
echo.

if not exist "%SCRIPT_DIR%installer\build_installer.bat" (
    powershell -Command "Write-Host '错误：未找到 installer\build_installer.bat' -ForegroundColor Red"
    echo 请确保文件存在：%SCRIPT_DIR%installer\build_installer.bat
    pause
    goto :eof
)

pushd "%SCRIPT_DIR%installer" >nul 2>&1
call build_installer.bat %*
set "EXITCODE=%ERRORLEVEL%"
popd >nul 2>&1

if not "%EXITCODE%"=="0" (
    powershell -Command "Write-Host '打包失败或被中止' -ForegroundColor Red"
    pause
)

popd >nul 2>&1
endlocal

@echo off
:: Remote Controls 项目快速打包脚本
:: 调用 installer 文件夹中的打包脚本

echo ========================================
echo Remote Controls 快速打包工具
echo ========================================
echo.

cd installer
if exist "build_installer.bat" (
    call build_installer.bat %*
) else (
    powershell -Command "Write-Host '错误：未找到打包脚本' -ForegroundColor Red"
    echo 请确保 installer\build_installer.bat 存在
    pause
)

cd ..

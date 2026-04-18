@echo off
chcp 65001 >nul 2>&1
title Chrome 调试模式启动器 (Pinterest 爬虫)
echo ==========================================
echo   Chrome 调试模式启动器
echo   双击运行即可，详细控制请使用 start_chrome_debug.ps1
echo ==========================================
echo.
echo 正在以 PowerShell 启动...
echo.

:: 检查是否有参数传入
set "PS_ARGS="
if "%1"=="" goto :run
:parse_args
if "%1"=="" goto :run
set "PS_ARGS=%PS_ARGS% %1"
shift
goto :parse_args

:run
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_chrome_debug.ps1" %PS_ARGS%
if %ERRORLEVEL% neq 0 (
    echo.
    echo 如果 PowerShell 执行出错，请以管理员身份运行 PowerShell 并执行:
    echo   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    echo.
)

echo.
pause
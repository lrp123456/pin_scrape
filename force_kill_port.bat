@echo off
REM 强制关闭占用8000端口的进程

echo ========================================
echo   强制关闭端口占用工具
echo ========================================
echo.

echo 正在查找占用 8000 端口的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    set PID=%%a
    goto :found
)

echo 没有找到占用 8000 端口的进程
pause
exit /b 0

:found
echo 找到进程 PID: %PID%

echo.
echo 正在查看进程信息...
tasklist /FI "PID eq %PID%" /V

echo.
echo 正在强制关闭进程...
taskkill /F /PID %PID%

if errorlevel 1 (
    echo.
    echo ✗ 关闭失败！可能需要管理员权限
    echo.
    echo 请尝试以下方法：
    echo 1. 右键此脚本 → 以管理员身份运行
    echo 2. 或者手动修改配置中的 api_port 端口
    pause
    exit /b 1
)

echo.
echo ✓ 进程已成功关闭！

timeout /t 2 /nobreak >nul

echo.
echo 验证端口是否释放...
netstat -ano | findstr :8000 >nul
if errorlevel 1 (
    echo ✓ 端口 8000 已释放
) else (
    echo ✗ 端口仍被占用，请重试
)

echo.
pause

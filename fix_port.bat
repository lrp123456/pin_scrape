@echo off
REM 快速修复端口占用问题

echo ==========================================
echo   Pinterest Scraper - Port Fix Utility
echo ==========================================
echo.

echo 正在检查 8000 端口...
netstat -ano | findstr :8000 >nul
if errorlevel 1 (
    echo ✓ 端口 8000 未被占用
    echo.
    pause
    exit /b 0
)

echo ✗ 端口 8000 已被占用
echo.
echo 占用进程：
netstat -ano | findstr :8000
echo.

echo 正在关闭占用进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    echo 关闭进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo.
echo ✓ 端口 8000 已释放
echo.
pause

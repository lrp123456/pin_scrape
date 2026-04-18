@echo off
REM 快速启动API服务（调试模式）

echo ========================================
echo   启动API服务（调试模式）
echo ========================================
echo.

echo 启动参数：
echo   端口: 8000
echo   主机: 0.0.0.0
echo   调试: 启用
echo.

echo 启动中...
python api_service_enhanced/service_main.py --port 8000 --host 0.0.0.0

pause

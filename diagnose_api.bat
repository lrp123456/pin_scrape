@echo off
REM API服务诊断工具

echo ========================================
echo   API服务诊断工具
echo ========================================
echo.

echo [1/5] 检查Python环境...
python --version
if errorlevel 1 (
    echo ✗ Python未安装或不在PATH中
    pause
    exit /b 1
)
echo ✓ Python环境正常
echo.

echo [2/5] 检查依赖包...
python -c "import fastapi; import uvicorn; import playwright; print('✓ 核心依赖已安装')" 2>&1
if errorlevel 1 (
    echo ✗ 依赖包缺失，正在安装...
    pip install -r requirements.txt
)
echo.

echo [3/5] 检查导入...
python -c "from api_service_enhanced.service_main import app; print('✓ API服务导入成功')" 2>&1
if errorlevel 1 (
    echo ✗ API服务导入失败
    pause
    exit /b 1
)
echo.

echo [4/5] 检查Playwright...
python -c "import playwright; print('Playwright版本:', playwright.__version__)" 2>&1
if errorlevel 1 (
    echo ✗ Playwright未安装
    echo 正在安装...
    pip install playwright
    playwright install
)
echo.

echo [5/5] 尝试启动API服务...
echo 启动命令: python api_service_enhanced/service_main.py --port 8000
echo.
echo 如果5秒内没有响应，按Ctrl+C停止
echo.

timeout /t 2 /nobreak >nul

start /B python api_service_enhanced/service_main.py --port 8000

echo 等待服务启动...
timeout /t 5 /nobreak >nul

echo.
echo 测试服务连接...
curl -s http://localhost:8000/health

if errorlevel 1 (
    echo.
    echo ✗ 服务未响应
    echo.
    echo 可能的原因：
    echo 1. 端口被占用
    echo 2. 防火墙阻止
    echo 3. 依赖缺失
    echo 4. 配置错误
    echo.
    echo 请查看详细错误信息：
    echo python api_service_enhanced/service_main.py
) else (
    echo.
    echo ✓ 服务启动成功！
    echo.
    echo 访问：http://localhost:8000/docs
)

echo.
pause

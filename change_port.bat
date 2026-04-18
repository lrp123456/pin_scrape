@echo off
REM 快速修改API端口配置

echo ========================================
echo   API端口配置工具
echo ========================================
echo.

set CONFIG_FILE=%APPDATA%\PinterestScraper\config.json

if not exist "%CONFIG_FILE%" (
    echo 配置文件不存在，正在创建...
    if not exist "%APPDATA%\PinterestScraper" mkdir "%APPDATA%\PinterestScraper"
    echo {"api_port": 8001} > "%CONFIG_FILE%"
    echo ✓ 已创建配置文件，端口设置为 8001
    echo.
    pause
    exit /b 0
)

echo 当前配置文件: %CONFIG_FILE%
echo.

echo 请选择新端口:
echo   1. 8001
echo   2. 8002
echo   3. 8080
echo   4. 9000
echo   5. 自定义端口
echo.

set /p CHOICE="请输入选项 (1-5): "

if "%CHOICE%"=="1" set NEW_PORT=8001
if "%CHOICE%"=="2" set NEW_PORT=8002
if "%CHOICE%"=="3" set NEW_PORT=8080
if "%CHOICE%"=="4" set NEW_PORT=9000

if "%CHOICE%"=="5" (
    set /p NEW_PORT="请输入端口号 (1024-65535): "
)

if not defined NEW_PORT (
    echo ✗ 无效选择
    pause
    exit /b 1
)

echo.
echo 正在更新配置...
echo 新端口: %NEW_PORT%

REM 使用Python更新JSON
python -c "import json; f=open(r'%CONFIG_FILE%', 'r+', encoding='utf-8'); d=json.load(f); d['api_port']=%NEW_PORT%; f.seek(0); json.dump(d, f, indent=2); f.truncate(); f.close(); print('✓ 配置已更新')"

if errorlevel 1 (
    echo ✗ 更新失败
    pause
    exit /b 1
)

echo.
echo ✓ 端口已修改为 %NEW_PORT%
echo.
echo 请重新启动托盘应用以应用新配置
echo.

pause

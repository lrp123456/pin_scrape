@echo off
REM 快速测试脚本

echo ========================================
echo   Pinterest Scraper - Import Test
echo ========================================
echo.

echo [1/4] Testing imports...
python -c "from shared.models import Pin; print('  [OK] shared.models')" 2>&1
if errorlevel 1 (
    echo   [FAIL] shared.models import failed
    pause
    exit /b 1
)

python -c "from scraper import PinterestScraper; print('  [OK] scraper')" 2>&1
if errorlevel 1 (
    echo   [FAIL] scraper import failed
    pause
    exit /b 1
)

python -c "from downloader import ImageDownloader; print('  [OK] downloader')" 2>&1
if errorlevel 1 (
    echo   [FAIL] downloader import failed
    pause
    exit /b 1
)

python -c "from output import save_json; print('  [OK] output')" 2>&1
if errorlevel 1 (
    echo   [FAIL] output import failed
    pause
    exit /b 1
)

echo.
echo [2/4] Testing main.py...
python main.py --help >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] main.py test failed
    pause
    exit /b 1
)
echo   [OK] main.py works

echo.
echo [3/4] Checking API service...
if exist "api_service_enhanced\service_main.py" (
    echo   [OK] API service found
) else (
    echo   [FAIL] API service not found
    pause
    exit /b 1
)

echo.
echo [4/4] Checking tray app...
if exist "tray_app\tray_main.py" (
    echo   [OK] Tray app found
) else (
    echo   [FAIL] Tray app not found
    pause
    exit /b 1
)

echo.
echo ========================================
echo   All Tests Passed!
echo ========================================
echo.
echo You can now run:
echo   - python tray_app/tray_main.py
echo   - python api_service_enhanced/service_main.py
echo.

pause

@echo off
chcp 65001 >nul
REM Pinterest Scraper Build Script

echo ==========================================
echo   Pinterest Scraper - Build Script
echo ==========================================
echo.

REM Change to build directory
cd /d "%~dp0"

REM Check Python and PyInstaller
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found
    echo Please run: pip install pyinstaller
    pause
    exit /b 1
)

REM Clean old builds
echo [1/6] Cleaning old build files...
if exist "..\dist\tray_app.exe" del /F /Q "..\dist\tray_app.exe"
if exist "..\dist\api_service.exe" del /F /Q "..\dist\api_service.exe"
if exist "..\dist\scraper_worker.exe" del /F /Q "..\dist\scraper_worker.exe"
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
echo Clean completed
echo.

REM Build tray application
echo [2/6] Building tray application...
pyinstaller tray_app.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: Tray application build failed
    pause
    exit /b 1
)
echo.

REM Build API service
echo [3/6] Building API service...
pyinstaller api_service.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: API service build failed
    pause
    exit /b 1
)
echo.

REM Build scraper worker
echo [4/6] Building scraper worker...
pyinstaller scraper_worker.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: Scraper worker build failed
    pause
    exit /b 1
)
echo.

REM Copy built files to dist
echo [5/6] Copying built files to dist...
if not exist "..\dist" mkdir "..\dist"
copy /Y "dist\tray_app.exe" "..\dist\tray_app.exe"
copy /Y "dist\api_service.exe" "..\dist\api_service.exe"
copy /Y "dist\scraper_worker.exe" "..\dist\scraper_worker.exe"
echo.

REM Create README
echo [6/6] Creating README...
(
echo Pinterest Scraper - Portable Version
echo ====================================
echo.
echo Deployment Instructions:
echo 1. Place tray_app.exe, api_service.exe, scraper_worker.exe in the same directory
echo 2. Double-click tray_app.exe to run
echo 3. Right-click tray icon to start service
echo 4. Visit http://localhost:8000/docs for API documentation
echo.
echo Requirements:
echo - Windows 10/11
echo - Chrome browser
echo - Internet connection
echo.
echo No Python environment required!
) > "..\dist\README.txt"
echo.

echo ==========================================
echo   Build completed successfully!
echo   Files are in: dist\
echo ==========================================
echo.
dir "..\dist"
echo.
pause

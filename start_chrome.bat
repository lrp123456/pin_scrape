@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ==========================================
echo   Pinterest Scraper - Chrome Launcher
echo ==========================================
echo.

REM Find Chrome
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" (
    echo ERROR: Chrome not found.
    pause
    exit /b 1
)

set "DEBUG_PROFILE=C:\temp\chrome-debug-profile"
set "ORIG_DIR=%LOCALAPPDATA%\Google\Chrome\User Data"

REM Kill Chrome
echo [1/3] Closing Chrome...
taskkill /F /IM chrome.exe >nul 2>&1
ping 127.0.0.1 -n 3 >nul

REM Clean lock files
echo [2/3] Cleaning lock files...
del /F /Q "%DEBUG_PROFILE%\SingletonLock" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\SingletonSocket" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\SingletonCookie" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\lockfile" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\DevToolsActivePort" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\Default\SingletonLock" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\Default\SingletonSocket" >nul 2>&1
del /F /Q "%DEBUG_PROFILE%\Default\SingletonCookie" >nul 2>&1

REM Copy profile ONLY if debug profile doesn't exist yet
if not exist "%DEBUG_PROFILE%\Default\Network\Cookies" (
    echo.
    echo [Setup] First time setup - copying profile from original Chrome...
    if not exist "%DEBUG_PROFILE%" mkdir "%DEBUG_PROFILE%"
    if not exist "%DEBUG_PROFILE%\Default" mkdir "%DEBUG_PROFILE%\Default"
    if not exist "%DEBUG_PROFILE%\Default\Network" mkdir "%DEBUG_PROFILE%\Default\Network"

    copy /Y "%ORIG_DIR%\Local State" "%DEBUG_PROFILE%\Local State" >nul 2>&1
    copy /Y "%ORIG_DIR%\First Run" "%DEBUG_PROFILE%\First Run" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Preferences" "%DEBUG_PROFILE%\Default\Preferences" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Secure Preferences" "%DEBUG_PROFILE%\Default\Secure Preferences" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Login Data" "%DEBUG_PROFILE%\Default\Login Data" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Login Data-journal" "%DEBUG_PROFILE%\Default\Login Data-journal" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Network\Cookies" "%DEBUG_PROFILE%\Default\Network\Cookies" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Network\Cookies-journal" "%DEBUG_PROFILE%\Default\Network\Cookies-journal" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Web Data" "%DEBUG_PROFILE%\Default\Web Data" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Web Data-journal" "%DEBUG_PROFILE%\Default\Web Data-journal" >nul 2>&1
    copy /Y "%ORIG_DIR%\Default\Bookmarks" "%DEBUG_PROFILE%\Default\Bookmarks" >nul 2>&1
    echo   Profile copied. You may need to log in to Pinterest once.
) else (
    echo.
    echo [2/3] Debug profile exists - keeping your login state intact.
    echo   Cookies preserved from last session.
)

REM Start Chrome
echo.
echo [3/3] Starting Chrome (debug port 9222)...
start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%DEBUG_PROFILE%" --profile-directory=Default --no-first-run --no-default-browser-check --disable-default-apps --disable-background-networking --disable-translate --disable-sync --start-maximized "https://www.pinterest.com"

echo Waiting for Chrome debug port...
set READY=0
for /L %%i in (1,1,20) do (
    if !READY! == 0 (
        ping 127.0.0.1 -n 2 >nul
        curl -s http://127.0.0.1:9222/json/version >nul 2>&1 && set READY=1
    )
)

echo.
if %READY% == 1 (
    echo ==========================================
    echo   Chrome debug port READY on 9222
    echo ==========================================
    echo.
    echo   CDP: http://127.0.0.1:9222
    echo.
    echo   If Pinterest asks for login, log in NOW.
    echo   Your session will be saved for next time.
    echo.
    echo   To RESET login state, delete this folder:
    echo   %DEBUG_PROFILE%
    echo.
) else (
    echo ==========================================
    echo   WARNING: Debug port NOT responding
    echo ==========================================
    echo.
    echo   Try: powershell -ExecutionPolicy Bypass -File start_chrome_debug.ps1
    echo.
)

pause
@echo off
REM One-click script to start a debugging session and run a scrape
REM Usage: double-click or run from command line

setlocal

REM === 1) Start Chrome with remote debugging ===
echo === Starting Chrome debugger on 0.0.0.0:9222 ===
call start_chrome.bat
if errorlevel 1 (
    echo Failed to start Chrome.
    pause
    exit /b 1
)

REM Give it a moment to be ready
ping 127.0.0.1 -n 3 >nul

REM === 2) Verify the debug endpoint is reachable ===
echo.
echo === Verifying CDP endpoint ===
curl -s http://127.0.0.1:9222/json/version >nul 2>&1
if errorlevel 1 (
    echo Warning: CDP endpoint not reachable. Is Chrome running?
) else (
    echo CDP endpoint is reachable.
    curl -s http://127.0.0.1:9222/json/version
)

REM === 3) Run the Pinterest scraper (example) ===
echo.
echo === Running Pinterest scraper ===
python pinterest_local.py --query "test" --max-pins 10

REM === 4) Stop Chrome when done (optional) ===
echo.
echo === Done. Press any key to stop Chrome and exit ===
pause >nul
call stop_chrome.bat
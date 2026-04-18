@echo off
REM Stop Chrome debugging server gracefully

echo Stopping Chrome...

REM Try graceful stop first
taskkill /F /IM chrome.exe 2>nul
if errorlevel 1 (
    echo Chrome was not running.
) else (
    echo Chrome processes terminated.
)

echo Done.
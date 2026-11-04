@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\MAA-PRTS\MAA-PRTS.exe" (
    set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333
    "dist\MAA-PRTS\MAA-PRTS.exe" --debug
    exit /b
)
python -u "backend\main.py" --debug
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\MAA-PRTS\MAA-PRTS.exe" (
    start "" "dist\MAA-PRTS\MAA-PRTS.exe"
    exit /b
)
echo [提示] 没找到编译版，改用源码启动（需要 pip install pywebview）
python "backend\main.py"
if errorlevel 1 pause

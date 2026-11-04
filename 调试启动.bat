@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1

if not exist "%~dp0启动.bat" (
    echo [错误] 未找到 启动.bat。请在完整的 MAA-PRTS 项目目录中运行本脚本。
    pause
    exit /b 1
)

call "%~dp0启动.bat" --debug
exit /b %ERRORLEVEL%

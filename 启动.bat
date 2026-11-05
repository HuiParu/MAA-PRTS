@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1

cd /d "%~dp0"
if errorlevel 1 goto :CannotEnter

set "DEBUG_MODE="
if /i "%~1"=="--debug" set "DEBUG_MODE=1"

if exist "build\MAA-PRTS\MAA-PRTS.exe" goto :RunExe
if not exist "backend\main.py" goto :MissingSource
if not exist "tools\setup\prepare-python.bat" goto :MissingSource

call "tools\setup\prepare-python.bat"
if errorlevel 1 goto :PrepareFailed

call :InstallRuntime
set "INSTALL_RC=%ERRORLEVEL%"
if not "%INSTALL_RC%"=="0" goto :InstallFailed

echo.
if defined DEBUG_MODE (
    echo [调试] 正在以源码模式启动 MAA-PRTS（DevTools 端口：9333）...
    "%PYTHON%" -u "backend\main.py" --debug
) else (
    echo [启动] 正在以源码模式启动 MAA-PRTS...
    "%PYTHON%" "backend\main.py"
)
set "APP_RC=%ERRORLEVEL%"
if not "%APP_RC%"=="0" goto :AppFailed

if defined DEBUG_MODE (
    echo.
    pause
)
exit /b 0


:RunExe
if defined DEBUG_MODE goto :RunDebugExe
start "" /D "%CD%\build\MAA-PRTS" "%CD%\build\MAA-PRTS\MAA-PRTS.exe"
if errorlevel 1 goto :ExeFailed
exit /b 0


:RunDebugExe
set "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333"
echo [调试] 正在启动编译版 MAA-PRTS（DevTools 端口：9333）...
"%CD%\build\MAA-PRTS\MAA-PRTS.exe" --debug
set "APP_RC=%ERRORLEVEL%"
if not "%APP_RC%"=="0" goto :AppFailed
echo.
pause
exit /b 0


:InstallRuntime
"%PYTHON%" -c "import webview, clr" >nul 2>&1
if not errorlevel 1 exit /b 0

echo [初始化] 正在安装运行依赖 pywebview 和 pythonnet（仅首次需要）...
"%PYTHON%" -m pip install --disable-pip-version-check --prefer-binary --upgrade %PIP_USER_ARG% pywebview pythonnet
if errorlevel 1 exit /b 1

"%PYTHON%" -c "import webview, clr" >nul 2>&1
if errorlevel 1 (
    echo [错误] 运行依赖安装后仍无法导入。
    exit /b 1
)
exit /b 0


:CannotEnter
echo [错误] 无法进入脚本所在目录：%~dp0
pause
exit /b 1


:MissingSource
echo [错误] 未找到 backend\main.py 或 tools\setup\prepare-python.bat。
echo 请在完整的 MAA-PRTS 项目目录中运行本脚本。
pause
exit /b 1


:PrepareFailed
rem 具体原因已由 tools\setup\prepare-python.bat 打印。
pause
exit /b 1


:InstallFailed
echo [错误] 依赖安装失败。请确认网络可访问 pypi.org，或检查代理/证书设置后重试。
pause
exit /b %INSTALL_RC%


:ExeFailed
echo [错误] 无法启动 build\MAA-PRTS\MAA-PRTS.exe。
pause
exit /b 1


:AppFailed
echo.
echo [错误] 程序异常退出，退出码 %APP_RC%。
echo 日志位置：debug\app.log
echo 若错误提到 WebView2 或 Edge Chromium，请安装 Microsoft Edge WebView2 Runtime 后重试。
pause
exit /b %APP_RC%

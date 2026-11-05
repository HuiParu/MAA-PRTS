@echo off
rem 脚本含 UTF-8 中文，必须先切代码页，否则标签定位会错位（即使调用方已切过也无害）。
chcp 65001 >nul 2>&1

rem ============================================================
rem 共享的 Python 环境引导（供 启动.bat / 打包.bat 调用，请勿单独运行）
rem
rem 成功：设置 PYTHON（解释器路径）、PYTHON_IS_VENV、PIP_USER_ARG，退出码 0
rem 失败：打印具体原因，退出码 1
rem
rem 注意：本脚本不能用 setlocal，否则上面的变量无法传回调用方。
rem ============================================================

rem 本脚本位于 tools\setup\ 下，项目根在上两级；后续相对路径都以项目根为准。
cd /d "%~dp0..\.."
if errorlevel 1 (
    echo [错误] 无法进入项目目录：%~dp0..\..
    exit /b 1
)

call :SelectPython
if errorlevel 1 exit /b 1
call :EnsurePip
if errorlevel 1 exit /b 1

rem 直接用系统 Python 时优先装到用户目录，避免无管理员权限时写入失败。
set "PIP_USER_ARG="
if not defined PYTHON_IS_VENV (
    "%PYTHON%" -c "import site; raise SystemExit(0 if site.ENABLE_USER_SITE else 1)" >nul 2>&1
    if not errorlevel 1 set "PIP_USER_ARG=--user"
)
exit /b 0


:SelectPython
set "PYTHON="
set "PYTHON_IS_VENV="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=%CD%\.venv\Scripts\python.exe"
        set "PYTHON_IS_VENV=1"
        exit /b 0
    )
    echo [提示] 项目中的 .venv 不可用，将尝试系统 Python。
)

call :FindSystemPython
if errorlevel 1 exit /b 1
set "SYSTEM_PYTHON=%PYTHON%"

echo [初始化] 正在创建项目专用环境 .venv（仅首次需要）...
"%PYTHON%" -m venv ".venv"
if errorlevel 1 (
    echo [提示] 创建 .venv 失败，将直接使用系统 Python 安装依赖。
    set "PYTHON=%SYSTEM_PYTHON%"
    exit /b 0
)

set "PYTHON=%CD%\.venv\Scripts\python.exe"
set "PYTHON_IS_VENV=1"
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [提示] 新建的 .venv 不可用，将直接使用系统 Python 安装依赖。
    set "PYTHON=%SYSTEM_PYTHON%"
    set "PYTHON_IS_VENV="
)
exit /b 0


:FindSystemPython
set "PYTHON="
call :TryPython py -3
if not errorlevel 1 exit /b 0
call :TryPython python
if not errorlevel 1 exit /b 0
call :TryPython python3
if not errorlevel 1 exit /b 0

rem PATH 未配置时，继续检查官方安装器和 Python Install Manager 的常见位置。
for /d %%D in (
    "%LocalAppData%\Programs\Python\Python*"
    "%LocalAppData%\Python\pythoncore-*"
    "%ProgramFiles%\Python*"
    "%ProgramFiles(x86)%\Python*"
) do (
    if exist "%%~fD\python.exe" (
        call :TryPythonPath "%%~fD\python.exe"
        if not errorlevel 1 exit /b 0
    )
)

echo [错误] 未找到 Python 3.10 或更高版本。
echo Download: https://www.python.org/downloads/windows/
echo 安装时请勾选 Add python.exe to PATH。
exit /b 1


rem One call for both: print the interpreter path if version >= 3.10, else exit 1 quietly.
:TryPython
set "PYTHON="
for /f "delims=" %%I in ('%* -c "import sys; sys.exit(1) if sys.version_info < (3, 10) else print(sys.executable)" 2^>nul') do set "PYTHON=%%I"
if defined PYTHON exit /b 0
exit /b 1


:TryPythonPath
if not exist "%~1" exit /b 1
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "PYTHON=%~1"
exit /b 0


:EnsurePip
"%PYTHON%" -m pip --version >nul 2>&1
if not errorlevel 1 exit /b 0

echo [初始化] Python 未附带 pip，正在尝试启用...
"%PYTHON%" -m ensurepip --upgrade
if errorlevel 1 (
    echo [错误] 无法启用 pip。请重新安装官方 Python，并在安装器中勾选 pip。
    exit /b 1
)
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [错误] pip 仍不可用。
    exit /b 1
)
exit /b 0

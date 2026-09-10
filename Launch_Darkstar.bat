@echo off
rem SPDX-License-Identifier: Apache-2.0
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "DARKSTAR_ROOT=%CD%"
set "DARKSTAR_ELECTRON=%DARKSTAR_ROOT%\backend\vendor\electron\win32-x64\electron.exe"
set "DARKSTAR_APP=%DARKSTAR_ROOT%\backend\shell"
set "DARKSTAR_BOOTSTRAP_PYTHON=%DARKSTAR_ROOT%\backend\scripts\bootstrap-python.ps1"
set "DARKSTAR_BOOTSTRAP_ELECTRON=%DARKSTAR_ROOT%\backend\scripts\bootstrap-electron.ps1"
set "DARKSTAR_BOOTSTRAP_NATIVE=%DARKSTAR_ROOT%\backend\scripts\bootstrap-llamacpp.ps1"

call :ensure_python || goto :bootstrap_failed
call :ensure_electron || goto :bootstrap_failed
call :ensure_native || goto :bootstrap_failed

if not exist "%DARKSTAR_ELECTRON%" (
    echo.
    echo [Darkstar] ERROR: Electron runtime is missing after bootstrap:
    echo "%DARKSTAR_ELECTRON%"
    goto :launch_failed
)
if not exist "%DARKSTAR_APP%\package.json" (
    echo.
    echo [Darkstar] ERROR: Application shell is missing:
    echo "%DARKSTAR_APP%"
    goto :launch_failed
)

if /I "%DARKSTAR_SHOW_CONSOLE%"=="1" (
    "%DARKSTAR_ELECTRON%" "%DARKSTAR_APP%" %*
    if errorlevel 1 exit /b 1
    exit /b 0
)

start "" /D "%DARKSTAR_ROOT%" "%DARKSTAR_ELECTRON%" "%DARKSTAR_APP%" %*
if errorlevel 1 goto :launch_failed
exit /b 0

:ensure_python
if exist "%DARKSTAR_ROOT%\.darkstar-runtime\python-install.json" exit /b 0
if defined DARKSTAR_PYTHON if exist "%DARKSTAR_PYTHON%" exit /b 0
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" exit /b 0
if defined ProgramFiles if exist "%ProgramFiles%\Python311\python.exe" exit /b 0
call :run_bootstrap "%DARKSTAR_BOOTSTRAP_PYTHON%" "Python"
exit /b %ERRORLEVEL%

:ensure_electron
if exist "%DARKSTAR_ELECTRON%" exit /b 0
call :run_bootstrap "%DARKSTAR_BOOTSTRAP_ELECTRON%" "Electron"
exit /b %ERRORLEVEL%

:ensure_native
if not exist "%DARKSTAR_ROOT%\backend\bin\backends\cpu\llama-server.exe" goto :bootstrap_native
if not exist "%DARKSTAR_ROOT%\backend\bin\backends\vulkan\llama-server.exe" goto :bootstrap_native
if not exist "%DARKSTAR_ROOT%\backend\bin\backends\cuda\llama-server.exe" goto :bootstrap_native
if not exist "%DARKSTAR_ROOT%\backend\bin\diffusion\cpu\sd-cli.exe" goto :bootstrap_native
if not exist "%DARKSTAR_ROOT%\backend\bin\diffusion\vulkan\sd-cli.exe" goto :bootstrap_native
exit /b 0

:bootstrap_native
call :run_bootstrap "%DARKSTAR_BOOTSTRAP_NATIVE%" "native AI runtime"
exit /b %ERRORLEVEL%

:run_bootstrap
set "DARKSTAR_BOOTSTRAP_SCRIPT=%~1"
set "DARKSTAR_BOOTSTRAP_NAME=%~2"
if not exist "%DARKSTAR_BOOTSTRAP_SCRIPT%" (
    echo.
    echo [Darkstar] ERROR: %DARKSTAR_BOOTSTRAP_NAME% bootstrap helper is missing:
    echo "%DARKSTAR_BOOTSTRAP_SCRIPT%"
    exit /b 1
)
where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo.
    echo [Darkstar] ERROR: powershell.exe is required to provision the missing %DARKSTAR_BOOTSTRAP_NAME% component.
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_BOOTSTRAP_SCRIPT%"
exit /b %ERRORLEVEL%

:bootstrap_failed
echo.
echo [Darkstar] ERROR: Required runtime provisioning failed. Darkstar was not started.
pause >nul
exit /b 1

:launch_failed
echo.
echo [Darkstar] ERROR: Darkstar could not be started.
pause >nul
exit /b 1

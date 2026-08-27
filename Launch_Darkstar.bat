@echo off
rem SPDX-License-Identifier: Apache-2.0
setlocal EnableExtensions DisableDelayedExpansion

set "DARKSTAR_ROOT=%~dp0"
if "%DARKSTAR_ROOT:~-1%"=="\" set "DARKSTAR_ROOT=%DARKSTAR_ROOT:~0,-1%"
set "DARKSTAR_HIDDEN_HELPER=%DARKSTAR_ROOT%\backend\scripts\launch-darkstar-hidden.vbs"
set "DARKSTAR_SETUP_HELPER=%DARKSTAR_ROOT%\backend\scripts\launch-darkstar-setup.vbs"
set "DARKSTAR_WSCRIPT=%SystemRoot%\System32\wscript.exe"
set "DARKSTAR_PYTHON_BOOTSTRAP=%DARKSTAR_ROOT%\backend\scripts\bootstrap-python.ps1"
set "DARKSTAR_PYTHON_INSTALLER=%DARKSTAR_ROOT%\backend\vendor\python\python-3.11.9-amd64.exe"
set "DARKSTAR_ELECTRON_DIR=%DARKSTAR_ROOT%\backend\vendor\electron\win32-x64"
set "DARKSTAR_ELECTRON=%DARKSTAR_ROOT%\backend\vendor\electron\win32-x64\electron.exe"
set "DARKSTAR_BOOTSTRAP=%DARKSTAR_ROOT%\backend\scripts\bootstrap-electron.ps1"
set "DARKSTAR_LLAMA_DIR=%DARKSTAR_ROOT%\backend\bin"
set "DARKSTAR_LLAMA_BACKENDS=%DARKSTAR_ROOT%\backend\bin\backends"
set "DARKSTAR_LLAMA_CPU=%DARKSTAR_ROOT%\backend\bin\backends\cpu\llama-server.exe"
set "DARKSTAR_LLAMA_VULKAN=%DARKSTAR_ROOT%\backend\bin\backends\vulkan\llama-server.exe"
set "DARKSTAR_LLAMA_CUDA=%DARKSTAR_ROOT%\backend\bin\backends\cuda\llama-server.exe"
set "DARKSTAR_LLAMA_BOOTSTRAP=%DARKSTAR_ROOT%\backend\scripts\bootstrap-llamacpp.ps1"
set "DARKSTAR_LAUNCHER=%DARKSTAR_ROOT%\backend\Darkstar_Core.js"

rem Probe runtime state before choosing visible setup or hidden normal launch.
set "DARKSTAR_NEED_PYTHON=0"
call :python_runtime_ready
if errorlevel 1 set "DARKSTAR_NEED_PYTHON=1"

set "DARKSTAR_NEED_ELECTRON=0"
call :electron_runtime_ready
if errorlevel 1 set "DARKSTAR_NEED_ELECTRON=1"

set "DARKSTAR_NEED_LLAMA=0"
call :llama_runtime_ready
if errorlevel 1 set "DARKSTAR_NEED_LLAMA=1"

set "DARKSTAR_BOOTSTRAP_REQUIRED=0"
if "%DARKSTAR_NEED_PYTHON%"=="1" set "DARKSTAR_BOOTSTRAP_REQUIRED=1"
if "%DARKSTAR_NEED_ELECTRON%"=="1" set "DARKSTAR_BOOTSTRAP_REQUIRED=1"
if "%DARKSTAR_NEED_LLAMA%"=="1" set "DARKSTAR_BOOTSTRAP_REQUIRED=1"

rem A hidden launch can discover that setup is required. In that case, reopen
rem this BAT visibly so users can see download/provisioning progress. The hidden
rem probe exits immediately; it never leaves a blank console waiting behind setup.
if /I "%DARKSTAR_HIDDEN_LAUNCH%"=="1" if "%DARKSTAR_BOOTSTRAP_REQUIRED%"=="1" if /I not "%DARKSTAR_SHOW_CONSOLE%"=="1" (
    if not exist "%DARKSTAR_SETUP_HELPER%" exit /b 1
    set "DARKSTAR_HIDDEN_LAUNCH="
    start "" /b "%DARKSTAR_WSCRIPT%" //Nologo "%DARKSTAR_SETUP_HELPER%" %*
    if errorlevel 1 exit /b 1
    exit /b 0
)

rem With runtimes already ready, a direct BAT launch hands off immediately to
rem the hidden helper. Hidden helper invocations already arrive hidden and therefore
rem skip this handoff.
if /I not "%DARKSTAR_HIDDEN_LAUNCH%"=="1" if "%DARKSTAR_BOOTSTRAP_REQUIRED%"=="0" if /I not "%DARKSTAR_SHOW_CONSOLE%"=="1" (
    call :launch_hidden_async %*
    if errorlevel 1 goto :startup_failed
    exit /b 0
)

if "%DARKSTAR_NEED_PYTHON%"=="1" goto :bootstrap_python
goto :python_ready

:bootstrap_python
if not exist "%DARKSTAR_PYTHON_BOOTSTRAP%" (
    echo.
    echo [Darkstar Harness] ERROR: Python bootstrap helper is missing:
    echo "%DARKSTAR_PYTHON_BOOTSTRAP%"
    goto :startup_failed
)
echo.
echo ============================================================
echo  Darkstar Python 3.11 prerequisite
echo ============================================================
echo [Darkstar Harness] Python 3.11 x64 is not installed.
echo [Darkstar Harness] The official Python 3.11.9 installer will open now.
echo [Darkstar Harness] Complete the installer normally; Darkstar will continue after it closes.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_PYTHON_BOOTSTRAP%"
if errorlevel 1 goto :startup_failed

:python_ready
call :python_runtime_ready
if errorlevel 1 (
    echo.
    echo [Darkstar Harness] ERROR: Python setup completed without a usable 64-bit Python 3.11 interpreter.
    goto :startup_failed
)

if "%DARKSTAR_NEED_ELECTRON%"=="1" goto :bootstrap_electron
goto :electron_ready

:bootstrap_electron
if not exist "%DARKSTAR_BOOTSTRAP%" (
    echo.
    echo [Darkstar Harness] ERROR: Electron bootstrap helper is missing:
    echo "%DARKSTAR_BOOTSTRAP%"
    goto :startup_failed
)
echo.
echo ============================================================
echo  Darkstar first-time runtime setup
echo ============================================================
echo [Darkstar Harness] Electron 43.2.0 is not installed yet.
echo [Darkstar Harness] Download and verification progress will be shown below.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_BOOTSTRAP%"
if errorlevel 1 goto :startup_failed

:electron_ready
call :electron_runtime_ready
if errorlevel 1 (
    echo.
    echo [Darkstar Harness] ERROR: Electron bootstrap completed without a usable runtime:
    echo "%DARKSTAR_ELECTRON%"
    goto :startup_failed
)

if "%DARKSTAR_NEED_LLAMA%"=="1" goto :bootstrap_llama
goto :llama_ready

:bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BOOTSTRAP%" (
    echo.
    echo [Darkstar Harness] ERROR: llama.cpp bootstrap helper is missing:
    echo "%DARKSTAR_LLAMA_BOOTSTRAP%"
    goto :startup_failed
)
echo.
echo [Darkstar Harness] llama.cpp backends are not installed yet.
echo [Darkstar Harness] Downloading/verifying pinned CPU + Vulkan + CUDA 12.4 runtimes...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_LLAMA_BOOTSTRAP%"
if errorlevel 1 goto :startup_failed

:llama_ready
call :llama_runtime_ready
if errorlevel 1 (
    echo.
    echo [Darkstar Harness] ERROR: llama.cpp bootstrap completed without all CPU, Vulkan and CUDA servers.
    goto :startup_failed
)

rem A visible setup console has completed its only job. Hand the actual app to
rem the hidden launcher and return immediately so this terminal closes now.
if /I not "%DARKSTAR_HIDDEN_LAUNCH%"=="1" if /I not "%DARKSTAR_SHOW_CONSOLE%"=="1" (
    echo.
    echo [Darkstar Harness] Runtime setup complete. Starting Darkstar...
    call :launch_hidden_async %*
    if errorlevel 1 goto :startup_failed
    exit /b 0
)

if not exist "%DARKSTAR_LAUNCHER%" (
    echo.
    echo [Darkstar Harness] ERROR: Application launcher is missing:
    echo "%DARKSTAR_LAUNCHER%"
    goto :startup_failed
)

pushd "%DARKSTAR_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [Darkstar Harness] ERROR: Could not enter the application directory:
    echo "%DARKSTAR_ROOT%"
    goto :startup_failed
)

set "ELECTRON_RUN_AS_NODE=1"
echo [Darkstar Harness] Diagnostics enabled. Runtime trace will be recorded for this session.
"%DARKSTAR_ELECTRON%" "%DARKSTAR_LAUNCHER%" --darkstar-debug %*
set "DARKSTAR_EXIT_CODE=%ERRORLEVEL%"
set "ELECTRON_RUN_AS_NODE="
popd

if not "%DARKSTAR_EXIT_CODE%"=="0" goto :launch_failed
exit /b 0

:launch_failed
echo.
echo [Darkstar Harness] Application exited with error code %DARKSTAR_EXIT_CODE%.
goto :hold_error

:startup_failed
set "DARKSTAR_EXIT_CODE=1"

:hold_error
if /I "%DARKSTAR_HIDDEN_LAUNCH%"=="1" exit /b %DARKSTAR_EXIT_CODE%
echo.
echo [Darkstar Harness] The terminal will remain open so you can read the error.
echo Press any key to close this window.
pause >nul
exit /b %DARKSTAR_EXIT_CODE%

:launch_hidden_async
if not exist "%DARKSTAR_HIDDEN_HELPER%" (
    echo.
    echo [Darkstar Harness] ERROR: Hidden launch helper is missing:
    echo "%DARKSTAR_HIDDEN_HELPER%"
    exit /b 1
)
if not exist "%DARKSTAR_WSCRIPT%" (
    echo.
    echo [Darkstar Harness] ERROR: Windows Script Host could not be located:
    echo "%DARKSTAR_WSCRIPT%"
    exit /b 1
)
start "" /b "%DARKSTAR_WSCRIPT%" //Nologo "%DARKSTAR_HIDDEN_HELPER%" %*
if errorlevel 1 exit /b 1
exit /b 0

:python_runtime_ready
if not exist "%DARKSTAR_PYTHON_BOOTSTRAP%" exit /b 1
set "DARKSTAR_DETECTED_PYTHON="
for /f "usebackq delims=" %%P in (`powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_PYTHON_BOOTSTRAP%" -ProbeOnly 2^>nul`) do if not defined DARKSTAR_DETECTED_PYTHON set "DARKSTAR_DETECTED_PYTHON=%%P"
if not defined DARKSTAR_DETECTED_PYTHON exit /b 1
set "DARKSTAR_PYTHON=%DARKSTAR_DETECTED_PYTHON%"
exit /b 0

:electron_runtime_ready
if not exist "%DARKSTAR_ELECTRON%" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\version" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\icudtl.dat" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\resources.pak" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\snapshot_blob.bin" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\v8_context_snapshot.bin" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\locales\en-US.pak" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\LICENSE" exit /b 1
if not exist "%DARKSTAR_ELECTRON_DIR%\LICENSES.chromium.html" exit /b 1
set "DARKSTAR_ELECTRON_VERSION="
set /p DARKSTAR_ELECTRON_VERSION=<"%DARKSTAR_ELECTRON_DIR%\version"
if not "%DARKSTAR_ELECTRON_VERSION%"=="43.2.0" exit /b 1
exit /b 0

:llama_runtime_ready
if not exist "%DARKSTAR_LLAMA_CPU%" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama-server-impl.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama-common.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml-base.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_VULKAN%" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\llama-server-impl.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\llama-common.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-base.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-vulkan.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_CUDA%" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\llama-server-impl.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\llama-common.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-base.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-cuda.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cudart64_12.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cublas64_12.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cublasLt64_12.dll" exit /b 1
if not exist "%DARKSTAR_LLAMA_DIR%\licenses\llama.cpp-LICENSE" exit /b 1
if not exist "%DARKSTAR_LLAMA_DIR%\licenses\NVIDIA-CUDA-12.4-EULA.pdf" exit /b 1
dir /b "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 exit /b 1
dir /b "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 exit /b 1
dir /b "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

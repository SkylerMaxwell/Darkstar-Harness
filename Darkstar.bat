@echo off
rem SPDX-License-Identifier: GPL-3.0-only
setlocal EnableExtensions DisableDelayedExpansion

set "DARKSTAR_ROOT=%~dp0"
if "%DARKSTAR_ROOT:~-1%"=="\" set "DARKSTAR_ROOT=%DARKSTAR_ROOT:~0,-1%"
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

if not exist "%DARKSTAR_ELECTRON%" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\version" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\icudtl.dat" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\resources.pak" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\snapshot_blob.bin" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\v8_context_snapshot.bin" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\locales\en-US.pak" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\LICENSE" goto :bootstrap_electron
if not exist "%DARKSTAR_ELECTRON_DIR%\LICENSES.chromium.html" goto :bootstrap_electron
set /p DARKSTAR_ELECTRON_VERSION=<"%DARKSTAR_ELECTRON_DIR%\version"
if not "%DARKSTAR_ELECTRON_VERSION%"=="43.2.0" goto :bootstrap_electron
goto :electron_ready

:bootstrap_electron
if not exist "%DARKSTAR_BOOTSTRAP%" (
    echo.
    echo [Darkstar Harness] ERROR: Electron bootstrap helper is missing:
    echo "%DARKSTAR_BOOTSTRAP%"
    goto :startup_failed
)
echo.
echo [Darkstar Harness] Electron 43.2.0 is not installed yet. Bootstrapping the pinned official runtime...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_BOOTSTRAP%"
if errorlevel 1 goto :startup_failed

:electron_ready
if not exist "%DARKSTAR_ELECTRON%" (
    echo.
    echo [Darkstar Harness] ERROR: Electron bootstrap completed without a usable runtime:
    echo "%DARKSTAR_ELECTRON%"
    goto :startup_failed
)

if not exist "%DARKSTAR_LLAMA_CPU%" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama-server-impl.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\llama-common.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml-base.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_VULKAN%" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\llama-server-impl.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\llama-common.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-base.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-vulkan.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_CUDA%" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\llama-server-impl.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\llama-common.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-base.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-cuda.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cudart64_12.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cublas64_12.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BACKENDS%\cuda\cublasLt64_12.dll" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_DIR%\licenses\llama.cpp-LICENSE" goto :bootstrap_llama
if not exist "%DARKSTAR_LLAMA_DIR%\licenses\NVIDIA-CUDA-12.4-EULA.pdf" goto :bootstrap_llama
dir /b "%DARKSTAR_LLAMA_BACKENDS%\cpu\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 goto :bootstrap_llama
dir /b "%DARKSTAR_LLAMA_BACKENDS%\vulkan\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 goto :bootstrap_llama
dir /b "%DARKSTAR_LLAMA_BACKENDS%\cuda\ggml-cpu*.dll" >nul 2>&1
if errorlevel 1 goto :bootstrap_llama
goto :llama_ready

:bootstrap_llama
if not exist "%DARKSTAR_LLAMA_BOOTSTRAP%" (
    echo.
    echo [Darkstar Harness] ERROR: llama.cpp bootstrap helper is missing:
    echo "%DARKSTAR_LLAMA_BOOTSTRAP%"
    goto :startup_failed
)
echo.
echo [Darkstar Harness] llama.cpp backends are not installed yet. Bootstrapping pinned CPU + Vulkan + CUDA 12.4 runtimes...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DARKSTAR_LLAMA_BOOTSTRAP%"
if errorlevel 1 goto :startup_failed

:llama_ready
if not exist "%DARKSTAR_LLAMA_CPU%" goto :llama_bootstrap_failed
if not exist "%DARKSTAR_LLAMA_VULKAN%" goto :llama_bootstrap_failed
if not exist "%DARKSTAR_LLAMA_CUDA%" goto :llama_bootstrap_failed
goto :llama_bootstrap_verified

:llama_bootstrap_failed
echo.
echo [Darkstar Harness] ERROR: llama.cpp bootstrap completed without all CPU, Vulkan and CUDA servers.
goto :startup_failed

:llama_bootstrap_verified

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
if defined DARKSTAR_HIDDEN_LAUNCH exit /b %DARKSTAR_EXIT_CODE%
echo.
echo [Darkstar Harness] The terminal will remain open so you can read the error.
echo Press any key to close this window.
pause >nul
exit /b %DARKSTAR_EXIT_CODE%

@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
where powershell.exe >nul 2>nul || (
  echo [Darkstar Portable Build] powershell.exe was not found.
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0backend\scripts\build-portable-single-exe.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [Darkstar Portable Build] FAILED with exit code %EXITCODE%.
  pause
  exit /b %EXITCODE%
)
echo.
echo [Darkstar Portable Build] Finished successfully.
pause
exit /b 0

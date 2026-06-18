@echo off
setlocal
set "ROOT_DIR=%~dp0"
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%start-dev.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Check the logs in the project root.
  pause
  exit /b 1
)
echo.
echo Services are launching in the background. You can close this window.
pause

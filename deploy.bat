@echo off
REM One-click Windows setup and local launch. Python 3.11+ is required.
REM Usage: deploy.bat [port]   (default: 8080)
setlocal
cd /d "%~dp0"

if /I "%~1"=="/?" goto usage
if /I "%~1"=="-h" goto usage
if /I "%~1"=="--help" goto usage

set "PORT=8080"
if not "%~1"=="" set "PORT=%~1"
if not "%~2"=="" goto usage

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" -Port "%PORT%"
if errorlevel 1 (
  echo.
  echo Setup or launch did not complete. Review the message above.
  pause
  exit /b 1
)
exit /b 0

:usage
echo Usage: deploy.bat [port]
echo Sets up dependencies, launches the portal locally, and opens a browser.
echo Python 3.11 or newer must be installed on this computer.
exit /b 0

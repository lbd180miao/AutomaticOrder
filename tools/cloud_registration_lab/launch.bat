@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "LAB_PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%LAB_PYTHON%" (
  echo Project Python environment not found: %LAB_PYTHON%
  echo Install requirements and run: python app.py
  pause
  exit /b 1
)
echo Starting point cloud lab. Please wait for the application window.
echo Diagnostic log: %~dp0startup.log
"%LAB_PYTHON%" -u -X faulthandler app.py %* > "%~dp0startup.log" 2>&1
set "LAB_EXIT=%ERRORLEVEL%"
if not "%LAB_EXIT%"=="0" (
  echo Application exited with code %LAB_EXIT%.
  type "%~dp0startup.log"
  pause
)

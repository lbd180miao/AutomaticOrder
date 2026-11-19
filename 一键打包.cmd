@echo off
setlocal
cd /d "%~dp0"
echo Building complete AGV and External deployments. Please keep this window open.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-distributed.ps1"
if errorlevel 1 (
  echo BUILD FAILED. See the error above. Do not deploy incomplete output.
  pause
  exit /b 1
)
echo BUILD SUCCESS. Output is in the delivery folder.
explorer.exe "%~dp0delivery"
pause

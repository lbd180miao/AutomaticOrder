@echo off
setlocal
cd /d "%~dp0"
"%~dp0..\..\.venv\Scripts\python.exe" -m pip install --no-deps --target "%~dp0.ppf_runtime" opencv-contrib-python-headless==4.13.0.92
if errorlevel 1 (
  echo PPF installation failed.
) else (
  echo PPF installation complete. Restart launch.bat.
)
pause

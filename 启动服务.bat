@echo off
cd /d "%~dp0"
echo Starting AutomaticOrder with Waitress on http://127.0.0.1:8082
".venv\Scripts\python.exe" run.py --host 127.0.0.1 --port 8082
pause

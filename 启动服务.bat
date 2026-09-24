@echo off
cd /d "%~dp0"
echo 正在激活虚拟环境...
call .venv\Scripts\activate.bat
echo 启动 Django（相机服务将自动随 Django 启动）...
python manage.py runserver 8082
pause

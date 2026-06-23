@echo off
chcp 65001 >nul
echo ========================================
echo  DM 3D深度相机演示启动脚本
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python
    pause
    exit /b 1
)

echo [1/4] 检查集成状态...
python check_dm_camera_setup.py
if errorlevel 1 (
    echo.
    echo [错误] 集成检查未通过，请先修复问题
    pause
    exit /b 1
)

echo.
echo [2/4] 准备数据库...
python manage.py migrate --noinput

echo.
echo [3/4] 收集静态文件...
python manage.py collectstatic --noinput --clear 2>nul

echo.
echo [4/4] 启动Django开发服务器...
echo.
echo ========================================
echo  服务器启动成功！
echo ========================================
echo.
echo  演示页面: http://127.0.0.1:8000/dm-camera/
echo  Admin后台: http://127.0.0.1:8000/admin/
echo  API基础URL: http://127.0.0.1:8000/dm-camera/api/
echo.
echo  按 Ctrl+C 停止服务器
echo ========================================
echo.

python manage.py runserver

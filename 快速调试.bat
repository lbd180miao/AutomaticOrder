@echo off
chcp 65001 >nul
echo ========================================
echo 3D料架定位工作台 - 采集点云功能调试
echo ========================================
echo.
echo ⚠️  重要提示：如果您是从浏览器过来的，请先：
echo    1. 按 Ctrl + F5 强制刷新浏览器页面
echo    2. 或按 Ctrl + Shift + Delete 清除浏览器缓存
echo    这很可能就能解决问题！
echo.
echo ========================================
echo 选择操作：
echo 1. 运行完整诊断（推荐）
echo 2. 运行API测试脚本
echo 3. 检查URL路由配置
echo 4. 启动Django服务器并打开测试页面
echo 5. 打开问题诊断文档
echo 6. 退出
echo.
set /p choice=请输入选项 (1-6): 

if "%choice%"=="1" goto diagnose
if "%choice%"=="2" goto test_api
if "%choice%"=="3" goto test_url
if "%choice%"=="4" goto run_server
if "%choice%"=="5" goto open_doc
if "%choice%"=="6" goto end

:diagnose
echo.
echo ========================================
echo 正在运行完整诊断...
echo ========================================
python diagnose_capture_issue.py
pause
goto end

:test_api
echo.
echo ========================================
echo 正在运行API测试...
echo ========================================
python test_capture_api.py
pause
goto end

:test_url
echo.
echo ========================================
echo 正在检查URL配置...
echo ========================================
python test_url_routing.py
pause
goto end

:run_server
echo.
echo ========================================
echo 启动Django开发服务器...
echo ========================================
echo.
echo 服务器启动后，请在浏览器中访问以下任一测试页面：
echo.
echo 1. 最小化测试（最简单）:
echo    http://127.0.0.1:8000/vision/minimal-test/
echo.
echo 2. 简单测试:
echo    http://127.0.0.1:8000/vision/simple-capture-test/
echo.
echo 3. 完整调试页面:
echo    http://127.0.0.1:8000/vision/test-capture-debug/
echo.
echo 4. 实际工作台页面:
echo    http://127.0.0.1:8000/vision/rack-locator/
echo.
echo ⚠️  记得按 Ctrl+F5 强制刷新浏览器！
echo.
echo 按 Ctrl+C 停止服务器
echo.
python manage.py runserver
goto end

:open_doc
start 问题诊断与解决方案.md
goto end

:end
echo.
echo 完成。
pause

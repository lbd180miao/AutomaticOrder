@echo off
chcp 65001 >nul
echo ============================================================
echo 「采集点云」按钮修复验证脚本
echo ============================================================
echo.
echo 正在检查修复情况...
echo.
python test_capture_button_issue.py
echo.
echo ============================================================
echo 下一步操作：
echo ============================================================
echo.
echo 1. 在浏览器中访问工作台页面
echo    http://localhost:8000/vision/rack-locator/
echo.
echo 2. 按 Ctrl+Shift+I 打开开发者工具
echo.
echo 3. 按 Ctrl+F5 强制刷新页面（清除缓存）
echo.
echo 4. 切换到 Console 标签
echo.
echo 5. 点击「📡 采集点云」按钮
echo.
echo 6. 在 Console 中查看日志输出：
echo    应该看到: [采集点云] 使用API端点: /vision/api/rack-location/workbench/capture/
echo.
echo 7. 切换到 Network 标签，查看请求：
echo    - URL应该是: workbench/capture/
echo    - 状态码应该是: 200
echo    - 响应应该包含: pointcloud_token, preview_image_url
echo.
echo ============================================================
echo.
pause

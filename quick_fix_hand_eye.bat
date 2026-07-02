@echo off
REM 快速修复手眼标定配置问题
REM 运行此脚本将自动更新所有配方的 hand_eye_config

echo ========================================
echo  手眼标定配置快速修复工具
echo ========================================
echo.

echo [1/3] 检查当前配置状态...
python check_hand_eye_config.py
if %errorlevel% neq 0 (
    echo.
    echo 发现配置问题，准备修复...
    echo.
) else (
    echo.
    echo 配置正常，无需修复。
    pause
    exit /b 0
)

echo [2/3] 更新配方配置...
python update_recipes_hand_eye_config.py
if %errorlevel% neq 0 (
    echo.
    echo ❌ 更新失败！请检查错误信息。
    pause
    exit /b 1
)

echo.
echo [3/3] 验证修复结果...
python update_recipes_hand_eye_config.py --verify-only

echo.
echo ========================================
echo  修复完成！
echo ========================================
echo.
echo 下一步操作：
echo  1. 刷新浏览器页面（Ctrl + F5）
echo  2. 重新尝试定位计算
echo  3. 应该能看到实际的偏差值
echo.
pause

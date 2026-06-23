@echo off
chcp 65001 >nul
echo ========================================
echo  DM相机SDK更新脚本
echo ========================================
echo.

set SOURCE_SDK=d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3
set TARGET_SDK=apps\dm_camera\sdk

echo [1/4] 备份当前SDK...
if exist "%TARGET_SDK%.backup" (
    rmdir /s /q "%TARGET_SDK%.backup"
)
xcopy "%TARGET_SDK%" "%TARGET_SDK%.backup\" /E /I /Y >nul
echo ✓ 备份完成

echo.
echo [2/4] 复制Python API文件...
copy "%SOURCE_SDK%\Python\API\zh\LW_DM_Api.py" "%TARGET_SDK%\" /Y >nul
copy "%SOURCE_SDK%\Python\API\zh\LW_DM_Type.py" "%TARGET_SDK%\" /Y >nul
echo ✓ Python API已更新

echo.
echo [3/4] 复制DLL文件...
copy "%SOURCE_SDK%\C\lib\windows\x64\dm_c_sdk.dll" "%TARGET_SDK%\lib\" /Y >nul
echo ✓ DLL已更新

echo.
echo [4/4] 验证更新...
python -c "from apps.dm_camera.sdk_wrapper import DMCamera; print('✓ SDK导入成功')"
if errorlevel 1 (
    echo.
    echo [错误] SDK验证失败！正在恢复备份...
    rmdir /s /q "%TARGET_SDK%"
    move "%TARGET_SDK%.backup" "%TARGET_SDK%"
    echo ✓ 已恢复到更新前的版本
    pause
    exit /b 1
)

echo.
echo ========================================
echo  SDK更新完成！
echo ========================================
echo.
echo 建议运行完整测试:
echo   python test_dm_camera.py
echo.
pause

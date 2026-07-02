#!/bin/bash
# 快速修复手眼标定配置问题
# 运行此脚本将自动更新所有配方的 hand_eye_config

echo "========================================"
echo " 手眼标定配置快速修复工具"
echo "========================================"
echo ""

echo "[1/3] 检查当前配置状态..."
python3 check_hand_eye_config.py
if [ $? -ne 0 ]; then
    echo ""
    echo "发现配置问题，准备修复..."
    echo ""
else
    echo ""
    echo "✅ 配置正常，无需修复。"
    exit 0
fi

echo "[2/3] 更新配方配置..."
python3 update_recipes_hand_eye_config.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 更新失败！请检查错误信息。"
    exit 1
fi

echo ""
echo "[3/3] 验证修复结果..."
python3 update_recipes_hand_eye_config.py --verify-only

echo ""
echo "========================================"
echo " 修复完成！"
echo "========================================"
echo ""
echo "下一步操作："
echo "  1. 刷新浏览器页面（Ctrl + F5）"
echo "  2. 重新尝试定位计算"
echo "  3. 应该能看到实际的偏差值"
echo ""

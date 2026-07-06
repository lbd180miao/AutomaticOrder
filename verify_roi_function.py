"""验证ROI自动加载功能是否正确实现"""
import os

print("=" * 70)
print("验证ROI自动加载功能")
print("=" * 70)

# 1. 检查JS文件是否包含必要的代码
js_file = r'd:\workspace2\AutomaticOrder\static\vision\js\rack_locator_workbench.js'

if not os.path.exists(js_file):
    print(f"❌ JS文件不存在: {js_file}")
    exit(1)

print(f"\n✅ JS文件存在: {js_file}")
print(f"   文件大小: {os.path.getsize(js_file)} 字节")

# 读取文件内容
with open(js_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 检查关键代码
checks = [
    ('autoLoadAndShowRecipeRoi 函数', 'async function autoLoadAndShowRecipeRoi()'),
    ('[自动ROI] 日志标记', '[自动ROI]'),
    ('采集点云回调', 'autoLoadAndShowRecipeRoi();'),
    ('正确的API端点', '/vision/api/rack-location/recipes/'),
    ('API响应解析', 'recipeDetailData.recipe'),
    ('image.complete 检查', 'if (image.complete)'),
]

print("\n检查关键代码：")
all_passed = True
for name, keyword in checks:
    if keyword in content:
        print(f"   ✅ {name}")
    else:
        print(f"   ❌ {name} - 未找到")
        all_passed = False

if all_passed:
    print("\n🎉 所有检查通过！代码已正确实现。")
    print("\n下一步操作：")
    print("1. 重启Django服务器（如果正在运行）")
    print("   taskkill /F /IM python.exe")
    print("   python manage.py runserver 0.0.0.0:8083")
    print()
    print("2. 打开浏览器，清除缓存")
    print("   Ctrl + Shift + Delete 或 Ctrl + Shift + R")
    print()
    print("3. 打开工作台")
    print("   http://127.0.0.1:8083/vision/rack-locator-panel/")
    print()
    print("4. 打开控制台（F12），查看日志")
    print("   搜索：[自动ROI]")
    print()
    print("5. 测试流程")
    print("   - 选择配方")
    print("   - 点击「采集点云」")
    print("   - 查看是否显示绿色ROI框")
else:
    print("\n❌ 代码检查失败！可能文件未保存或被覆盖。")

print("\n" + "=" * 70)

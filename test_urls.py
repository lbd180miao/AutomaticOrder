"""
测试配方模块的 URL 解析
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.urls import reverse

# 需要测试的 URL 列表
urls_to_test = [
    'vision:recipe_management',
    'vision:roi_3d_workbench',
    'vision:hand_eye_page',
    'vision:rack_locator_panel',
    'vision:rack_location_recipes',
    'vision:foam_inspector_interactive',
    'vision:task_list',
]

print("=" * 60)
print("测试配方模块 URL 解析")
print("=" * 60)

success_count = 0
error_count = 0

for url_name in urls_to_test:
    try:
        url = reverse(url_name)
        print(f"✅ {url_name:40} → {url}")
        success_count += 1
    except Exception as e:
        print(f"❌ {url_name:40} → 错误: {e}")
        error_count += 1

print("=" * 60)
print(f"测试完成: {success_count} 个成功, {error_count} 个失败")
print("=" * 60)

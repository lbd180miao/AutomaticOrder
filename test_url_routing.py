"""
检查URL路由配置
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.urls import reverse

print("=" * 60)
print("检查3D料架定位相关API URL配置")
print("=" * 60)

api_names = [
    'vision:api_vision_3d_capture',
    'vision:api_rack_location_workbench_capture',
    'vision:api_vision_3d_auto_align',
    'vision:api_rack_location_workbench_calculate',
    'vision:api_rack_location_workbench_save',
]

for name in api_names:
    try:
        url = reverse(name)
        print(f"✓ {name:50s} -> {url}")
    except Exception as e:
        print(f"✗ {name:50s} -> ERROR: {e}")

print("\n" + "=" * 60)
print("建议配置:")
print("=" * 60)
print("前端应使用以下URL之一:")
print("1. CFG.captureUrl = '/vision/api/vision/3d/capture/'")
print("2. CFG.legacyCaptureUrl = '/vision/api/rack-location/workbench/capture/'")

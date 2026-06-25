"""测试默认阈值是否已更新"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.algorithms.foam_inspector import _detect_foam_side
import cv2
import numpy as np

# 创建测试图像
image = np.zeros((100, 200, 3), dtype=np.uint8)
image[:, :] = (20, 20, 20)  # 黑色背景
image[20:80, 20:80] = (200, 200, 200)  # 白色泡棉区域

roi = (0, 0, 100, 100)  # ROI: 100x100
# 白色区域: 60x60 = 3600像素
# ROI面积: 100x100 = 10000像素
# 覆盖率: 36%

# 测试默认阈值
cfg = {}  # 不指定阈值，使用默认值
result = _detect_foam_side(image, roi, cfg)

print(f"实际覆盖率: {result['coverage_ratio']:.2%}")
print(f"是否检测到: {result['is_present']}")
print(f"默认阈值: {result.get('coverage_threshold', '未返回')}")

# 显式测试35%阈值
cfg_35 = {'coverage_threshold': 0.35}
result_35 = _detect_foam_side(image, roi, cfg_35)
print(f"\n使用35%阈值:")
print(f"是否检测到: {result_35['is_present']}")

# 显式测试70%阈值
cfg_70 = {'coverage_threshold': 0.70}
result_70 = _detect_foam_side(image, roi, cfg_70)
print(f"\n使用70%阈值:")
print(f"是否检测到: {result_70['is_present']}")

if result['is_present'] and not result_70['is_present']:
    print("\n✅ 默认阈值已更新为35%，修改成功！")
else:
    print("\n⚠️ 默认阈值可能还是70%，请检查代码")

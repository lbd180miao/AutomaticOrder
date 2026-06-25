"""调试测试失败问题"""
import os
import sys
import numpy as np
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.algorithms.foam_inspector import FoamInspector

# 重现测试场景
image = np.zeros((120, 220, 3), dtype=np.uint8)
image[:, :] = (35, 90, 80)
# 左侧泡棉
image[55:85, 5:55] = 245  # 30x50 = 1500像素
# 右侧泡棉  
image[55:85, 165:215] = 245  # 30x50 = 1500像素

result = FoamInspector().inspect(
    image=image,
    inspection_config={
        'foam_rois': {
            '0': {
                'left': (0.0, 0.45, 0.28, 0.78),
                'right': (0.72, 0.45, 1.0, 0.78),
            },
        },
        'coverage_threshold': 0.3,
        'max_offset_px': 18,
    },
    simulated_pass=False,
)

print("="*60)
print("检测结果:")
print("="*60)
print(f"is_passed: {result['is_passed']}")
print(f"is_present: {result['is_present']}")
print(f"defect_type: {result['defect_type']}")
print(f"coverage_ratio: {result['coverage_ratio']}")
print(f"score: {result['score']}")

if 'sides' in result.get('result_data', {}):
    print("\n侧面详情:")
    for side, data in result['result_data']['sides'].items():
        print(f"\n{side}:")
        print(f"  roi: {data['roi']}")
        print(f"  box: {data['box']}")
        print(f"  is_present: {data['is_present']}")
        print(f"  coverage_ratio: {data['coverage_ratio']}")
        print(f"  coverage_threshold: {data.get('coverage_threshold', 'N/A')}")
        print(f"  reason: {data.get('reason', 'N/A')}")

# 计算理论覆盖率
left_roi_pixels = 62 * 40  # (0.28 * 220) * (0.78-0.45) * 120
left_foam_pixels = 30 * 50
print(f"\n左侧理论计算:")
print(f"  ROI面积: {left_roi_pixels}")
print(f"  泡棉面积: {left_foam_pixels}")
print(f"  理论覆盖率: {left_foam_pixels/left_roi_pixels:.2%}")

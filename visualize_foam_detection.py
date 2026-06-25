"""可视化泡棉检测区域，帮助调整ROI"""
import os
import sys
import cv2
import numpy as np
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.algorithms.foam_inspector import FoamInspector
from pathlib import Path

# 查找最新图片
media_root = Path('media')
temp_uploads = media_root / 'temp_uploads'

if not temp_uploads.exists():
    print("temp_uploads 文件夹不存在")
    sys.exit(1)

images = list(temp_uploads.glob('*.jpg')) + list(temp_uploads.glob('*.png'))
if not images:
    print("没有找到图片")
    sys.exit(1)

latest_image = max(images, key=lambda p: p.stat().st_mtime)
print(f"分析图片: {latest_image}")

image = cv2.imread(str(latest_image))
if image is None:
    print("无法读取图片")
    sys.exit(1)

height, width = image.shape[:2]
print(f"图片尺寸: {width}x{height}")

# 使用不同的覆盖率阈值进行检测
thresholds = [0.30, 0.35, 0.40, 0.50, 0.60, 0.70]

print("\n不同覆盖率阈值的检测结果:")
print("="*70)
print(f"{'阈值':<8} {'是否通过':<10} {'覆盖率':<10} {'评分':<10}")
print("="*70)

for threshold in thresholds:
    inspector = FoamInspector(simulate=False)
    config = {
        'coverage_threshold': threshold,
        'white_min_v': 170,
        'white_max_s': 80,
        'white_min_l': 175,
    }
    
    result = inspector.inspect(
        position_index=0,
        inspection_config=config,
        image=image,
        camera_image_path=str(latest_image),
    )
    
    passed = "✅ 合格" if result['is_passed'] else "❌ 不合格"
    coverage = f"{result['coverage_ratio']:.2%}"
    score = f"{result['score']:.3f}"
    
    print(f"{threshold*100:5.0f}%   {passed:<10} {coverage:<10} {score:<10}")

print("="*70)
print("\n推荐配置:")
print("-" * 70)

# 找到实际覆盖率
actual_coverage = result['coverage_ratio']

if actual_coverage < 0.50:
    recommended = 0.35
    reason = "实际覆盖率较低，建议降低阈值或调整ROI框大小"
elif actual_coverage < 0.60:
    recommended = 0.50
    reason = "覆盖率中等，建议适度降低阈值"
else:
    recommended = 0.70
    reason = "覆盖率良好，保持当前阈值"

print(f"实际覆盖率: {actual_coverage:.2%}")
print(f"推荐阈值: {recommended*100:.0f}%")
print(f"原因: {reason}")
print("\n配置示例:")
print(f"""
{{
    'coverage_threshold': {recommended},
    'white_min_v': 170,
    'white_max_s': 80,
    'white_min_l': 175,
}}
""")

# 查看结果图
result_image_path = Path(result['result_image'])
if result_image_path.exists():
    print(f"\n结果图已保存: {result_image_path}")
    print("请查看结果图中的红色ROI框和泡棉检测区域")
else:
    print("\n未找到结果图")

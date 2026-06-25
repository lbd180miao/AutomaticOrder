"""分析真实泡棉图片的检测问题"""
import os
import sys
import cv2
import numpy as np
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.algorithms.foam_inspector import FoamInspector

# 从媒体文件夹中查找最新的上传图片
import glob
from pathlib import Path

media_root = Path('media')
temp_uploads = media_root / 'temp_uploads'

if temp_uploads.exists():
    images = list(temp_uploads.glob('*.jpg')) + list(temp_uploads.glob('*.png'))
    if images:
        latest_image = max(images, key=lambda p: p.stat().st_mtime)
        print(f"找到最新图片: {latest_image}")
        
        # 读取图片
        image = cv2.imread(str(latest_image))
        if image is None:
            print(f"无法读取图片: {latest_image}")
            sys.exit(1)
        
        height, width = image.shape[:2]
        print(f"图片尺寸: {width}x{height}")
        
        # 分析图片亮度分布
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        print(f"\n亮度统计:")
        print(f"  最小值: {gray.min()}")
        print(f"  最大值: {gray.max()}")
        print(f"  平均值: {gray.mean():.1f}")
        print(f"  中位数: {np.median(gray):.1f}")
        
        # 统计不同亮度范围的像素数
        very_dark = (gray < 50).sum()
        dark = ((gray >= 50) & (gray < 100)).sum()
        medium = ((gray >= 100) & (gray < 170)).sum()
        bright = ((gray >= 170) & (gray < 220)).sum()
        very_bright = (gray >= 220).sum()
        total = gray.size
        
        print(f"\n亮度分布:")
        print(f"  极暗 (<50):      {very_dark:8d} ({very_dark/total*100:5.1f}%)")
        print(f"  暗 (50-100):    {dark:8d} ({dark/total*100:5.1f}%)")
        print(f"  中等 (100-170): {medium:8d} ({medium/total*100:5.1f}%)")
        print(f"  亮 (170-220):   {bright:8d} ({bright/total*100:5.1f}%)")
        print(f"  极亮 (≥220):    {very_bright:8d} ({very_bright/total*100:5.1f}%)")
        
        # 使用不同的白色阈值进行检测
        print(f"\n使用不同白色阈值的检测结果:")
        print("="*60)
        
        for white_min_v in [120, 140, 160, 170, 180]:
            inspector = FoamInspector(simulate=False)
            config = {
                'coverage_threshold': 0.70,
                'white_min_v': white_min_v,
                'white_max_s': 80,
                'white_min_l': white_min_v,
            }
            
            result = inspector.inspect(
                position_index=0,
                inspection_config=config,
                image=image,
                camera_image_path=str(latest_image),
            )
            
            print(f"\n白色阈值 V={white_min_v}:")
            print(f"  is_passed: {result['is_passed']}")
            print(f"  coverage_ratio: {result['coverage_ratio']:.2%}")
            print(f"  score: {result['score']:.3f}")
            
            if 'sides' in result.get('result_data', {}):
                sides = result['result_data']['sides']
                for side, data in sides.items():
                    print(f"  {side}: present={data['is_present']}, coverage={data['coverage_ratio']:.2%}")
        
        print("\n" + "="*60)
        print("建议:")
        print("1. 如果使用较低的白色阈值能检测到泡棉，说明光照不足或泡棉不够白")
        print("2. 可以在配方中调整 white_min_v 和 white_min_l 参数")
        print("3. 或者调整覆盖率阈值 coverage_threshold")
        
    else:
        print("temp_uploads 文件夹中没有图片")
else:
    print("temp_uploads 文件夹不存在")

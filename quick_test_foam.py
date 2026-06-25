"""快速测试泡棉检测优化效果

这个脚本可以快速对比优化前后的检测效果。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()

import cv2
from apps.vision.algorithms.foam_inspector import FoamInspector


def compare_detection(image_path):
    """对比优化前后的检测效果"""
    
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ 无法读取图像: {image_path}")
        return
    
    print(f"{'='*70}")
    print(f"  泡棉检测对比测试 - 优化前 vs 优化后")
    print(f"{'='*70}")
    print(f"测试图像: {image_path}")
    print(f"图像尺寸: {image.shape[1]} x {image.shape[0]}")
    
    # 配置1: 旧版本严格参数
    old_config = {
        'coverage_threshold': 0.35,  # 35% - 太严格
        'white_min_v': 170,
        'white_max_s': 80,
        'white_min_l': 175,
        'side_min_area_ratio': 0.15,
        'ignore_border_ratio': 0.04,
        'enable_quality_analysis': False,
    }
    
    # 配置2: 新版本优化参数
    new_config = {
        'coverage_threshold': 0.08,  # 8% - 更合理
        'white_min_v': 150,
        'white_max_s': 100,
        'white_min_l': 160,
        'side_min_area_ratio': 0.05,
        'ignore_border_ratio': 0.02,
        'enable_quality_analysis': True,  # 启用自适应
        'enable_auto_adjustment': True,
    }
    
    inspector = FoamInspector(simulate=False)
    
    # 测试旧配置
    print(f"\n{'─'*70}")
    print("🔴 旧版本检测 (严格参数)")
    print(f"{'─'*70}")
    result_old = inspector.inspect(
        position_index=0,
        inspection_config=old_config,
        image=image.copy(),
    )
    
    print(f"覆盖率: {result_old['coverage_ratio']:.2%}")
    print(f"置信度: {result_old['score']:.3f}")
    print(f"判定结果: {'✅ PASS (合格)' if result_old['is_passed'] else '❌ NG (不合格)'}")
    print(f"缺陷类型: {result_old['defect_type']}")
    
    # 测试新配置
    print(f"\n{'─'*70}")
    print("🟢 新版本检测 (优化参数+自适应)")
    print(f"{'─'*70}")
    result_new = inspector.inspect(
        position_index=1,
        inspection_config=new_config,
        image=image.copy(),
    )
    
    print(f"覆盖率: {result_new['coverage_ratio']:.2%}")
    print(f"置信度: {result_new['score']:.3f}")
    print(f"判定结果: {'✅ PASS (合格)' if result_new['is_passed'] else '❌ NG (不合格)'}")
    print(f"缺陷类型: {result_new['defect_type']}")
    
    # 如果有图像质量分析
    if 'quality_analysis' in result_new and result_new['quality_analysis']:
        qa = result_new['quality_analysis']
        print(f"\n图像质量分析:")
        print(f"  - 亮度: {qa.get('mean_brightness', 'N/A'):.1f}")
        print(f"  - 对比度: {qa.get('contrast', 'N/A'):.1f}")
        print(f"  - 清晰度: {qa.get('sharpness_score', 'N/A'):.1f}")
        
        if qa.get('config_adjusted'):
            print(f"\n  ✨ 配置已自动调整:")
            for key, value in qa.get('adjustments', {}).items():
                print(f"     {key} = {value}")
    
    # 对比结果
    print(f"\n{'='*70}")
    print("📊 对比总结")
    print(f"{'='*70}")
    
    coverage_diff = result_new['coverage_ratio'] - result_old['coverage_ratio']
    score_diff = result_new['score'] - result_old['score']
    
    print(f"覆盖率变化: {result_old['coverage_ratio']:.2%} → {result_new['coverage_ratio']:.2%} "
          f"({'+'if coverage_diff > 0 else ''}{coverage_diff:.2%})")
    print(f"置信度变化: {result_old['score']:.3f} → {result_new['score']:.3f} "
          f"({'+'if score_diff > 0 else ''}{score_diff:.3f})")
    
    # 判定结果变化
    if result_old['is_passed'] != result_new['is_passed']:
        if result_new['is_passed']:
            print(f"\n✅ 改进效果: 原本误判为NG，现在正确识别为PASS")
        else:
            print(f"\n⚠️  警告: 原本判定为PASS，现在判定为NG")
    else:
        if result_new['is_passed']:
            print(f"\n✅ 两个版本都判定为PASS")
        else:
            print(f"\n❌ 两个版本都判定为NG")
    
    print(f"\n结果图像:")
    print(f"  旧版本: {result_old['result_image']}")
    print(f"  新版本: {result_new['result_image']}")
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='快速对比泡棉检测优化效果')
    parser.add_argument('image_path', help='图像文件路径')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_path):
        print(f"❌ 文件不存在: {args.image_path}")
        sys.exit(1)
    
    compare_detection(args.image_path)

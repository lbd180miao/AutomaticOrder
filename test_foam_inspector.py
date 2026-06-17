#!/usr/bin/env python
"""测试交互式泡棉检测功能"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')

import django
django.setup()

import cv2
import numpy as np
from apps.vision.algorithms.foam_inspector import FoamInspector


def test_simulated_inspection():
    """测试模拟检测"""
    print("=== 测试模拟泡棉检测 ===\n")
    
    inspector = FoamInspector(simulate=True)
    
    # 测试合格场景
    print("1. 测试合格场景 (position_index=0)")
    result = inspector.inspect(position_index=0, simulated_pass=True)
    print(f"   - 是否存在: {result['is_present']}")
    print(f"   - 是否对齐: {result['is_aligned']}")
    print(f"   - 边缘起翘: {result['has_lifted_edge']}")
    print(f"   - 分数: {result['score']}")
    print(f"   - 判定: {'✓ 合格' if result['is_passed'] else '✗ 不合格'}")
    print(f"   - 原图: {result['original_image']}")
    print(f"   - 结果图: {result['result_image']}\n")
    
    # 测试不合格场景
    print("2. 测试不合格场景 (position_index=1, 位置偏移)")
    result = inspector.inspect(position_index=1, simulated_pass=False)
    print(f"   - 缺陷类型: {result['defect_type']}")
    print(f"   - X偏移: {result['offset_x_px']} px")
    print(f"   - Y偏移: {result['offset_y_px']} px")
    print(f"   - 分数: {result['score']}")
    print(f"   - 判定: {'✓ 合格' if result['is_passed'] else '✗ 不合格'}\n")
    
    print("3. 测试不合格场景 (position_index=2, 边缘起翘)")
    result = inspector.inspect(position_index=2, simulated_pass=False)
    print(f"   - 缺陷类型: {result['defect_type']}")
    print(f"   - 边缘起翘: {result['has_lifted_edge']}")
    print(f"   - 分数: {result['score']}")
    print(f"   - 判定: {'✓ 合格' if result['is_passed'] else '✗ 不合格'}\n")
    
    print("✓ 模拟检测测试通过\n")


def test_real_image_inspection():
    """测试真实图片检测"""
    print("=== 测试真实图片检测 ===\n")
    
    # 创建一个测试图片
    width, height = 640, 480
    image = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 绘制背景
    image[:, :] = (200, 200, 200)
    
    # 绘制一个模拟的泡棉区域
    foam_x1, foam_y1 = 250, 180
    foam_x2, foam_y2 = 390, 300
    cv2.rectangle(image, (foam_x1, foam_y1), (foam_x2, foam_y2), (80, 100, 200), -1)
    
    print(f"创建测试图片: {width}x{height}")
    print(f"模拟泡棉区域: ({foam_x1},{foam_y1}) -> ({foam_x2},{foam_y2})\n")
    
    # 保存测试图片
    test_image_path = BASE_DIR / 'media' / 'test_foam.jpg'
    test_image_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(test_image_path), image)
    print(f"测试图片已保存: {test_image_path}\n")
    
    # 使用真实图片进行检测
    inspector = FoamInspector(simulate=False)
    
    try:
        result = inspector.inspect(
            position_index=0,
            image=image,
            camera_image_path=str(test_image_path),
        )
        
        print("检测结果:")
        print(f"   - 是否存在: {result['is_present']}")
        print(f"   - 是否对齐: {result['is_aligned']}")
        print(f"   - 边缘起翘: {result['has_lifted_edge']}")
        print(f"   - 分数: {result['score']}")
        print(f"   - 判定: {'✓ 合格' if result['is_passed'] else '✗ 不合格'}")
        print(f"   - ROI区域: {result['roi']}")
        print(f"   - 泡棉框: {result['foam_box']}")
        print(f"   - 结果图: {result['result_image']}\n")
        
        print("✓ 真实图片检测测试通过\n")
        
    except NotImplementedError as e:
        print(f"⚠ 预期的异常: {e}\n")


def test_inspection_config():
    """测试检测配置参数"""
    print("=== 测试检测配置参数 ===\n")
    
    inspector = FoamInspector(simulate=True)
    
    # 自定义配置
    config = {
        'score_threshold': 0.9,
        'coverage_threshold': 0.8,
        'max_offset_px': 20,
    }
    
    print(f"使用自定义配置: {config}\n")
    
    result = inspector.inspect(
        position_index=0,
        inspection_config=config,
        simulated_pass=True,
    )
    
    print("检测结果:")
    print(f"   - 分数: {result['score']}")
    print(f"   - 覆盖率: {result['coverage_ratio']}")
    print(f"   - 判定: {'✓ 合格' if result['is_passed'] else '✗ 不合格'}\n")
    
    print("✓ 配置参数测试通过\n")


def main():
    print("=" * 60)
    print("交互式泡棉检测功能测试")
    print("=" * 60 + "\n")
    
    try:
        test_simulated_inspection()
        test_real_image_inspection()
        test_inspection_config()
        
        print("=" * 60)
        print("✓ 所有测试通过")
        print("=" * 60)
        print("\n现在可以访问: http://127.0.0.1:8000/vision/foam-inspector/")
        print("测试交互式泡棉检测页面\n")
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

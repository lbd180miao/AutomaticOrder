#!/usr/bin/env python
"""测试泡棉检测算法的调试脚本"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

import cv2
import numpy as np
from apps.vision.algorithms.foam_inspector import FoamInspector

def create_test_image():
    """创建一个测试图像：黑色背景 + 白色泡棉"""
    # 创建500x600的黑色图像
    image = np.zeros((500, 600, 3), dtype=np.uint8)
    
    # 添加一个白色的矩形区域模拟泡棉（250x180）
    # 位置：中心偏右上，模拟泡棉
    foam_x1, foam_y1 = 280, 150
    foam_x2, foam_y2 = 530, 330
    image[foam_y1:foam_y2, foam_x1:foam_x2] = 240  # 接近白色的泡棉
    
    # 添加一些噪点和纹理
    noise = np.random.randint(0, 30, (foam_y2-foam_y1, foam_x2-foam_x1, 3), dtype=np.uint8)
    image[foam_y1:foam_y2, foam_x1:foam_x2] = np.clip(
        image[foam_y1:foam_y2, foam_x1:foam_x2].astype(int) - noise.astype(int), 0, 255
    ).astype(np.uint8)
    
    return image

def main():
    print("=== 泡棉检测算法测试 ===\n")
    
    # 创建测试图像
    test_image = create_test_image()
    print(f"✓ 创建测试图像: {test_image.shape}")
    
    # 保存测试图像用于查看
    cv2.imwrite('media/test_foam_input.png', test_image)
    print("✓ 测试图像已保存到: media/test_foam_input.png")
    
    # 初始化检测器
    inspector = FoamInspector(simulate=False)
    
    # 执行检测
    print("\n执行泡棉检测...")
    result = inspector.inspect(
        position_index=0,
        image=test_image,
        simulated_pass=True,  # 这个参数在使用真实图像时应该被忽略
    )
    
    # 打印结果
    print("\n=== 检测结果 ===")
    print(f"是否存在: {result['is_present']}")
    print(f"是否对齐: {result['is_aligned']}")  
    print(f"边缘起翘: {result['has_lifted_edge']}")
    print(f"缺陷类型: {result['defect_type']}")
    print(f"评分: {result['score']}")
    print(f"是否合格: {result['is_passed']}")
    print(f"\n偏移 X: {result['offset_x_px']} px")
    print(f"偏移 Y: {result['offset_y_px']} px")
    print(f"覆盖率: {result['coverage_ratio']:.1%}")
    print(f"\nROI: {result['roi']}")
    print(f"泡棉边界: {result['foam_box']}")
    print(f"\n原始图像: {result['original_image']}")
    print(f"结果图像: {result['result_image']}")
    
    # 验证图像文件
    import os
    if os.path.exists('media/' + result['original_image']):
        print(f"\n✓ 原始图像文件存在")
    else:
        print(f"\n✗ 原始图像文件不存在！")
        
    if os.path.exists('media/' + result['result_image']):
        print(f"✓ 结果图像文件存在")
    else:
        print(f"✗ 结果图像文件不存在！")
    
    print("\n测试完成！")

if __name__ == '__main__':
    main()

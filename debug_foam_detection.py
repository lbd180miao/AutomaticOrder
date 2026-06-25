"""泡棉检测调试工具

用于分析和优化泡棉检测算法的参数。
可以逐步查看检测过程中的各个中间结果。
"""
import cv2
import numpy as np
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()

from apps.vision.algorithms.foam_inspector import FoamInspector


def debug_foam_detection(image_path, position_index=0):
    """调试泡棉检测，展示中间步骤"""
    
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ 无法读取图像: {image_path}")
        return
    
    print(f"✅ 成功读取图像: {image.shape}")
    height, width = image.shape[:2]
    
    # 不同的配置方案测试
    configs = [
        {
            'name': '默认配置（优化后+自适应）',
            'config': {
                'coverage_threshold': 0.08,
                'white_min_v': 150,
                'white_max_s': 100,
                'white_min_l': 160,
                'side_min_area_ratio': 0.05,
                'ignore_border_ratio': 0.02,
                'enable_quality_analysis': True,  # 启用自适应
                'enable_auto_adjustment': True,
            }
        },
        {
            'name': '高灵敏度配置',
            'config': {
                'coverage_threshold': 0.05,
                'white_min_v': 140,
                'white_max_s': 110,
                'white_min_l': 150,
                'side_min_area_ratio': 0.03,
                'ignore_border_ratio': 0.01,
                'enable_quality_analysis': False,
            }
        },
        {
            'name': '多策略增强检测',
            'config': {
                'coverage_threshold': 0.06,
                'white_min_v': 145,
                'white_max_s': 105,
                'white_min_l': 155,
                'side_min_area_ratio': 0.04,
                'ignore_border_ratio': 0.015,
                'use_clahe': True,  # 启用对比度增强
                'denoise': True,  # 启用降噪
                'enable_quality_analysis': True,
            }
        },
        {
            'name': '原始配置（严格）',
            'config': {
                'coverage_threshold': 0.35,
                'white_min_v': 170,
                'white_max_s': 80,
                'white_min_l': 175,
                'side_min_area_ratio': 0.15,
                'ignore_border_ratio': 0.04,
                'enable_quality_analysis': False,
            }
        },
    ]
    
    # 测试每个配置
    for idx, test_case in enumerate(configs):
        print(f"\n{'='*60}")
        print(f"测试配置 {idx+1}: {test_case['name']}")
        print(f"{'='*60}")
        
        config = test_case['config']
        
        # 运行检测
        inspector = FoamInspector(simulate=False)
        result = inspector.inspect(
            position_index=position_index,
            inspection_config=config,
            image=image.copy(),
        )
        
        # 打印结果
        print(f"\n检测结果:")
        print(f"  - 泡棉存在: {result['is_present']}")
        print(f"  - 对齐状态: {result['is_aligned']}")
        print(f"  - 边缘起翘: {result['has_lifted_edge']}")
        print(f"  - 缺陷类型: {result['defect_type']}")
        print(f"  - 覆盖率: {result['coverage_ratio']:.2%}")
        print(f"  - 置信度: {result['score']:.3f}")
        print(f"  - 最终判定: {'✅ 合格 (PASS)' if result['is_passed'] else '❌ 不合格 (NG)'}")
        
        # 打印图像质量分析（如果有）
        if 'quality_analysis' in result and result['quality_analysis']:
            qa = result['quality_analysis']
            print(f"\n图像质量分析:")
            print(f"  - 平均亮度: {qa.get('mean_brightness', 'N/A')}")
            print(f"  - 对比度: {qa.get('contrast', 'N/A')}")
            print(f"  - 清晰度得分: {qa.get('sharpness_score', 'N/A')}")
            print(f"  - 噪声水平: {qa.get('noise_level', 'N/A')}")
            print(f"  - 白色像素比例: {qa.get('white_ratio', 0):.2%}")
            
            if 'suggestions' in qa:
                sug = qa['suggestions']
                print(f"\n  智能建议:")
                print(f"    - 光照情况: {sug.get('lighting', 'N/A')}")
                print(f"    - 对比度: {sug.get('contrast', 'N/A')}")
                print(f"    - 清晰度: {sug.get('sharpness', 'N/A')}")
                print(f"    - 噪声: {sug.get('noise', 'N/A')}")
                
                if qa.get('config_adjusted'):
                    print(f"\n  已自动调整配置:")
                    for key, value in qa.get('adjustments', {}).items():
                        print(f"    - {key}: {value}")
        
        print(f"\n配置参数:")
        for key, value in config.items():
            print(f"  - {key}: {value}")
        
        print(f"\n结果图像已保存:")
        print(f"  - 原图: {result['original_image']}")
        print(f"  - 结果图: {result['result_image']}")


def visualize_detection_steps(image_path, position_index=0):
    """可视化检测的各个步骤"""
    
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ 无法读取图像: {image_path}")
        return
    
    height, width = image.shape[:2]
    
    # 转换色彩空间
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    
    # 白色检测 - HSV
    white_hsv = cv2.inRange(hsv, (0, 0, 150), (180, 100, 255))
    
    # 白色检测 - LAB
    white_lab = cv2.inRange(lab[:, :, 0], 160, 255)
    
    # 组合
    mask_combined = cv2.bitwise_or(white_hsv, white_lab)
    
    # 形态学处理
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask_closed = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel_close, iterations=3)
    mask_final = cv2.morphologyEx(mask_closed, cv2.MORPH_OPEN, kernel_open, iterations=2)
    
    # 保存中间结果
    output_dir = Path("media/vision/debug")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cv2.imwrite(str(output_dir / "01_original.jpg"), image)
    cv2.imwrite(str(output_dir / "02_gray.jpg"), gray)
    cv2.imwrite(str(output_dir / "03_white_hsv.jpg"), white_hsv)
    cv2.imwrite(str(output_dir / "04_white_lab.jpg"), white_lab)
    cv2.imwrite(str(output_dir / "05_combined.jpg"), mask_combined)
    cv2.imwrite(str(output_dir / "06_closed.jpg"), mask_closed)
    cv2.imwrite(str(output_dir / "07_final.jpg"), mask_final)
    
    # 统计覆盖率
    total_pixels = width * height
    white_pixels_hsv = cv2.countNonZero(white_hsv)
    white_pixels_lab = cv2.countNonZero(white_lab)
    white_pixels_combined = cv2.countNonZero(mask_combined)
    white_pixels_final = cv2.countNonZero(mask_final)
    
    print(f"\n{'='*60}")
    print("检测步骤可视化分析")
    print(f"{'='*60}")
    print(f"图像尺寸: {width} x {height} = {total_pixels:,} 像素")
    print(f"\n各步骤白色像素统计:")
    print(f"  - HSV 白色检测: {white_pixels_hsv:,} 像素 ({white_pixels_hsv/total_pixels:.2%})")
    print(f"  - LAB 白色检测: {white_pixels_lab:,} 像素 ({white_pixels_lab/total_pixels:.2%})")
    print(f"  - 组合结果: {white_pixels_combined:,} 像素 ({white_pixels_combined/total_pixels:.2%})")
    print(f"  - 形态学处理后: {white_pixels_final:,} 像素 ({white_pixels_final/total_pixels:.2%})")
    
    print(f"\n中间结果已保存到: {output_dir}")
    print("文件列表:")
    for i, name in enumerate([
        "01_original.jpg - 原始图像",
        "02_gray.jpg - 灰度图",
        "03_white_hsv.jpg - HSV白色检测",
        "04_white_lab.jpg - LAB白色检测",
        "05_combined.jpg - 组合结果",
        "06_closed.jpg - 闭运算后",
        "07_final.jpg - 最终mask",
    ], 1):
        print(f"  {name}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='泡棉检测调试工具')
    parser.add_argument('image_path', help='图像文件路径')
    parser.add_argument('--position', type=int, default=0, help='位置索引（默认0）')
    parser.add_argument('--steps', action='store_true', help='显示检测步骤可视化')
    
    args = parser.parse_args()
    
    if args.steps:
        visualize_detection_steps(args.image_path, args.position)
    else:
        debug_foam_detection(args.image_path, args.position)

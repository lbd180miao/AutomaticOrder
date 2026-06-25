"""泡棉检测配置生成器

根据实际使用场景，生成最适合的检测配置。
"""
import json


def generate_config_for_scenario(scenario):
    """根据场景生成配置
    
    Args:
        scenario: 场景类型
            - 'standard': 标准场景（黑色保险杠+白色泡棉，正常光照）
            - 'low_light': 低光照场景
            - 'large_roi': 大ROI场景（泡棉占比小）
            - 'high_precision': 高精度场景（严格要求）
            - 'complex_background': 复杂背景场景
    
    Returns:
        dict: 配置字典
    """
    configs = {
        'standard': {
            'name': '标准场景配置',
            'description': '适用于正常光照下的黑色保险杠+白色泡棉检测',
            'config': {
                'coverage_threshold': 0.08,
                'white_min_v': 150,
                'white_max_s': 100,
                'white_min_l': 160,
                'side_min_area_ratio': 0.05,
                'side_max_area_ratio': 0.98,
                'ignore_border_ratio': 0.02,
                'side_min_compactness': 0.20,
                'global_min_area_ratio': 0.03,
                'global_max_area_ratio': 0.95,
                'global_min_aspect': 0.1,
                'global_max_aspect': 15.0,
                'global_min_compactness': 0.20,
                'enable_quality_analysis': True,
                'enable_auto_adjustment': True,
                'gray_high_threshold': 170,
                'adaptive_block_size': 21,
                'adaptive_c': -5,
            }
        },
        
        'low_light': {
            'name': '低光照场景配置',
            'description': '适用于光照不足的环境',
            'config': {
                'coverage_threshold': 0.06,
                'white_min_v': 130,  # 降低白色检测阈值
                'white_max_s': 120,
                'white_min_l': 145,
                'side_min_area_ratio': 0.04,
                'side_max_area_ratio': 0.98,
                'ignore_border_ratio': 0.015,
                'side_min_compactness': 0.18,
                'global_min_area_ratio': 0.025,
                'enable_quality_analysis': True,
                'enable_auto_adjustment': True,
                'use_clahe': True,  # 启用对比度增强
                'enable_low_light_gray_detection': True,
                'low_light_min_gray': 90,
                'low_light_delta_gray': 10,
                'low_light_max_s': 60,
                'gray_high_threshold': 150,
            }
        },
        
        'large_roi': {
            'name': '大ROI场景配置',
            'description': '适用于ROI区域很大，泡棉占比小的场景',
            'config': {
                'coverage_threshold': 0.03,  # 大幅降低覆盖率要求
                'white_min_v': 145,
                'white_max_s': 105,
                'white_min_l': 155,
                'side_min_area_ratio': 0.02,  # 降低最小面积要求
                'side_max_area_ratio': 0.98,
                'ignore_border_ratio': 0.01,  # 减小边界忽略
                'side_min_compactness': 0.18,
                'global_min_area_ratio': 0.01,
                'global_max_area_ratio': 0.98,
                'enable_quality_analysis': True,
                'enable_auto_adjustment': True,
            }
        },
        
        'high_precision': {
            'name': '高精度场景配置',
            'description': '适用于需要严格检测的场景，降低误检率',
            'config': {
                'coverage_threshold': 0.15,  # 提高覆盖率要求
                'white_min_v': 165,
                'white_max_s': 85,
                'white_min_l': 170,
                'side_min_area_ratio': 0.10,
                'side_max_area_ratio': 0.95,
                'ignore_border_ratio': 0.03,
                'side_min_compactness': 0.25,
                'global_min_area_ratio': 0.08,
                'global_max_aspect': 12.0,
                'global_min_compactness': 0.25,
                'enable_quality_analysis': True,
                'enable_auto_adjustment': False,  # 关闭自动调整
                'gray_high_threshold': 180,
            }
        },
        
        'complex_background': {
            'name': '复杂背景场景配置',
            'description': '适用于有其他白色物体或复杂背景的场景',
            'config': {
                'coverage_threshold': 0.10,
                'white_min_v': 160,
                'white_max_s': 90,
                'white_min_l': 165,
                'side_min_area_ratio': 0.08,
                'side_max_area_ratio': 0.95,
                'ignore_border_ratio': 0.025,
                'side_min_compactness': 0.25,
                'global_min_area_ratio': 0.05,
                'global_min_compactness': 0.25,
                'enable_quality_analysis': True,
                'enable_auto_adjustment': True,
                'denoise': True,  # 启用降噪
                'require_dark_support': True,  # 要求检测到黑色底座
                'dark_max_v': 65,
                'min_dark_ratio': 0.002,
            }
        },
    }
    
    return configs.get(scenario)


def print_config(config_info):
    """打印配置信息"""
    print(f"\n{'='*70}")
    print(f"  {config_info['name']}")
    print(f"{'='*70}")
    print(f"\n说明: {config_info['description']}\n")
    print("配置参数:")
    print(json.dumps(config_info['config'], indent=2, ensure_ascii=False))
    print(f"\n{'='*70}\n")


def save_config_to_file(config_info, output_path):
    """保存配置到文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config_info['config'], f, indent=2, ensure_ascii=False)
    print(f"✅ 配置已保存到: {output_path}")


def interactive_config_generator():
    """交互式配置生成器"""
    print("\n" + "="*70)
    print("  泡棉检测配置生成器")
    print("="*70)
    print("\n请选择您的使用场景:\n")
    print("1. 标准场景 - 正常光照，黑色保险杠+白色泡棉")
    print("2. 低光照场景 - 光线不足的环境")
    print("3. 大ROI场景 - ROI很大，泡棉占比小")
    print("4. 高精度场景 - 严格要求，降低误检")
    print("5. 复杂背景场景 - 有其他白色物体或复杂背景")
    print("\n输入场景编号 (1-5): ", end='')
    
    choice = input().strip()
    
    scenario_map = {
        '1': 'standard',
        '2': 'low_light',
        '3': 'large_roi',
        '4': 'high_precision',
        '5': 'complex_background',
    }
    
    if choice not in scenario_map:
        print("❌ 无效的选择")
        return
    
    scenario = scenario_map[choice]
    config_info = generate_config_for_scenario(scenario)
    
    print_config(config_info)
    
    print("是否保存配置到文件? (y/n): ", end='')
    save_choice = input().strip().lower()
    
    if save_choice == 'y':
        print("输入保存路径 (默认: foam_config.json): ", end='')
        output_path = input().strip() or 'foam_config.json'
        save_config_to_file(config_info, output_path)
        print("\n使用方法:")
        print(f"  import json")
        print(f"  with open('{output_path}', 'r') as f:")
        print(f"      config = json.load(f)")
        print(f"  inspector.inspect(inspection_config=config, ...)")


def generate_roi_config_template():
    """生成ROI配置模板"""
    template = {
        "foam_rois": {
            "position_0": {
                "left": [0.1, 0.2, 0.45, 0.8],
                "right": [0.55, 0.2, 0.9, 0.8]
            },
            "position_1": {
                "left": [0.1, 0.2, 0.45, 0.8],
                "right": [0.55, 0.2, 0.9, 0.8]
            }
        },
        "coverage_threshold": 0.08,
        "white_min_v": 150,
        "white_max_s": 100,
        "white_min_l": 160,
        "side_min_area_ratio": 0.05,
        "enable_quality_analysis": True
    }
    
    print("\n" + "="*70)
    print("  ROI配置模板（左右分离检测）")
    print("="*70)
    print("\n说明:")
    print("  - 坐标使用比例值 [x1_ratio, y1_ratio, x2_ratio, y2_ratio]")
    print("  - 比例值范围: 0.0 ~ 1.0")
    print("  - left: 左侧泡棉ROI")
    print("  - right: 右侧泡棉ROI")
    print("  - position_X: 不同位置可以配置不同的ROI\n")
    print(json.dumps(template, indent=2, ensure_ascii=False))
    print("\n" + "="*70 + "\n")
    
    return template


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'roi':
            # 生成ROI模板
            template = generate_roi_config_template()
            if len(sys.argv) > 2:
                output_path = sys.argv[2]
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(template, f, indent=2, ensure_ascii=False)
                print(f"✅ ROI配置模板已保存到: {output_path}")
        else:
            # 生成指定场景的配置
            scenario = sys.argv[1]
            config_info = generate_config_for_scenario(scenario)
            if config_info:
                print_config(config_info)
                if len(sys.argv) > 2:
                    output_path = sys.argv[2]
                    save_config_to_file(config_info, output_path)
            else:
                print(f"❌ 未知场景: {scenario}")
                print("可用场景: standard, low_light, large_roi, high_precision, complex_background")
    else:
        # 交互式模式
        interactive_config_generator()

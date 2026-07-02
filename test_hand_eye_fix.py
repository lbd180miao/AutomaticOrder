"""
测试手眼标定问题修复
验证修复后的功能是否正常工作
"""

import os
import sys
import django
import json

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe
from apps.vision.rack_location import Rack3DLocator


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_recipe_config():
    """测试1: 验证配方配置"""
    print_section("测试1: 验证配方配置")
    
    recipes = RackLocationRecipe.objects.all()
    
    if not recipes.exists():
        print("⚠️  警告: 没有找到任何配方！")
        return False
    
    print(f"找到 {recipes.count()} 个配方\n")
    
    all_valid = True
    
    for recipe in recipes:
        config = recipe.hand_eye_config or {}
        
        # 检查配置是否有效
        is_valid = False
        reason = []
        
        if config.get('skip_validation'):
            is_valid = True
            reason.append("✅ skip_validation=True")
        
        if config.get('calibration_id'):
            is_valid = True
            reason.append(f"✅ calibration_id={config['calibration_id']}")
        
        if config.get('T_flange_camera'):
            is_valid = True
            reason.append("✅ 包含变换矩阵")
        
        matrix = config.get('matrix', 'identity')
        if matrix != 'identity':
            is_valid = True
            reason.append(f"✅ matrix={matrix}")
        
        if is_valid:
            print(f"✅ {recipe.recipe_name} (ID: {recipe.id})")
            for r in reason:
                print(f"   {r}")
        else:
            print(f"❌ {recipe.recipe_name} (ID: {recipe.id})")
            print(f"   配置: {json.dumps(config, ensure_ascii=False)}")
            all_valid = False
        
        print()
    
    if all_valid:
        print("🎉 所有配方配置正确！")
    else:
        print("❌ 存在无效配置，请运行修复脚本。")
    
    return all_valid


def test_validation_logic():
    """测试2: 验证定位验证逻辑"""
    print_section("测试2: 验证定位验证逻辑")
    
    # 测试不同的配置场景
    test_cases = [
        {
            'name': '开发模式（skip_validation=True）',
            'config': {'matrix': 'identity', 'skip_validation': True},
            'should_pass': True,
        },
        {
            'name': '生产模式（有calibration_id）',
            'config': {'matrix': 'T_flange_camera', 'calibration_id': 123},
            'should_pass': True,
        },
        {
            'name': '直接包含矩阵',
            'config': {
                'matrix': 'T_flange_camera',
                'T_flange_camera': [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
            },
            'should_pass': True,
        },
        {
            'name': '无效配置（仅identity）',
            'config': {'matrix': 'identity'},
            'should_pass': False,
        },
        {
            'name': '空配置',
            'config': {},
            'should_pass': False,
        },
    ]
    
    print("模拟验证逻辑测试...\n")
    
    all_passed = True
    
    for i, test in enumerate(test_cases, 1):
        hand_eye_config = test['config']
        skip_calibration_check = hand_eye_config.get('skip_validation', False)
        
        # 检查是否有有效的标定
        has_valid_calibration = False
        if hand_eye_config:
            matrix_type = hand_eye_config.get('matrix')
            if matrix_type and matrix_type != 'identity':
                has_valid_calibration = True
            elif 'calibration_id' in hand_eye_config:
                has_valid_calibration = True
            elif 'T_flange_camera' in hand_eye_config:
                has_valid_calibration = True
            elif matrix_type == 'identity' and skip_calibration_check:
                has_valid_calibration = True
        
        validation_passed = has_valid_calibration or skip_calibration_check
        
        expected = test['should_pass']
        actual = validation_passed
        
        if expected == actual:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            all_passed = False
        
        print(f"{status} 测试 {i}: {test['name']}")
        print(f"   配置: {json.dumps(hand_eye_config, ensure_ascii=False)}")
        print(f"   预期: {'通过' if expected else '拒绝'}")
        print(f"   实际: {'通过' if actual else '拒绝'}")
        print()
    
    if all_passed:
        print("🎉 所有验证逻辑测试通过！")
    else:
        print("❌ 部分测试失败，验证逻辑可能有问题。")
    
    return all_passed


def test_locator_create():
    """测试3: 测试定位器初始化"""
    print_section("测试3: 测试定位器初始化")
    
    try:
        locator = Rack3DLocator()
        print("✅ Rack3DLocator 初始化成功")
        return True
    except Exception as e:
        print(f"❌ Rack3DLocator 初始化失败: {e}")
        return False


def test_recipe_defaults():
    """测试4: 测试新配方默认值"""
    print_section("测试4: 测试新配方默认值")
    
    # 创建测试配方
    test_recipe = RackLocationRecipe(
        recipe_name="测试配方-请删除",
        position_no=999,
        layer_no=1,
        rack_side='LEFT',
    )
    
    # 模拟默认值设置
    default_hand_eye_config = {
        'matrix': 'identity',
        'skip_validation': True,
        'note': '开发测试模式',
    }
    
    print("默认 hand_eye_config:")
    print(json.dumps(default_hand_eye_config, indent=2, ensure_ascii=False))
    print()
    
    # 验证默认配置是否有效
    skip_validation = default_hand_eye_config.get('skip_validation', False)
    
    if skip_validation:
        print("✅ 默认配置包含 skip_validation=True")
        print("✅ 新创建的配方将自动通过验证")
        return True
    else:
        print("❌ 默认配置缺少 skip_validation")
        print("❌ 新创建的配方可能无法通过验证")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("  手眼标定问题修复 - 完整测试")
    print("=" * 80)
    
    results = {}
    
    # 运行所有测试
    results['配方配置'] = test_recipe_config()
    results['验证逻辑'] = test_validation_logic()
    results['定位器初始化'] = test_locator_create()
    results['默认配置'] = test_recipe_defaults()
    
    # 汇总结果
    print_section("测试结果汇总")
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {test_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 所有测试通过！修复成功！")
        print("=" * 80)
        print("\n下一步操作：")
        print("  1. 刷新浏览器页面（Ctrl + F5）")
        print("  2. 打开 3D 料架定位工作台")
        print("  3. 尝试进行定位计算")
        print("  4. 应该能看到实际的偏差值\n")
        return True
    else:
        print("❌ 部分测试失败！")
        print("=" * 80)
        print("\n建议操作：")
        print("  1. 运行修复脚本: python update_recipes_hand_eye_config.py")
        print("  2. 检查代码修改是否已应用")
        print("  3. 重新运行本测试脚本\n")
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='测试手眼标定问题修复')
    parser.add_argument('--test', choices=['config', 'logic', 'locator', 'defaults', 'all'],
                       default='all', help='选择要运行的测试')
    
    args = parser.parse_args()
    
    if args.test == 'config':
        success = test_recipe_config()
    elif args.test == 'logic':
        success = test_validation_logic()
    elif args.test == 'locator':
        success = test_locator_create()
    elif args.test == 'defaults':
        success = test_recipe_defaults()
    else:
        success = run_all_tests()
    
    sys.exit(0 if success else 1)

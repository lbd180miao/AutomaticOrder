"""
快速检查配方的手眼标定配置状态
"""

import os
import sys
import django
from tabulate import tabulate

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe


def check_configs():
    """检查所有配方的手眼标定配置"""
    
    print("\n" + "=" * 80)
    print("配方手眼标定配置检查")
    print("=" * 80 + "\n")
    
    recipes = RackLocationRecipe.objects.all().order_by('position_no', 'layer_no')
    
    if not recipes:
        print("❌ 没有找到任何配方！")
        return
    
    table_data = []
    valid_count = 0
    invalid_count = 0
    
    for recipe in recipes:
        config = recipe.hand_eye_config or {}
        
        # 分析配置状态
        matrix_type = config.get('matrix', '-')
        skip_val = config.get('skip_validation', False)
        has_calib_id = 'calibration_id' in config
        has_matrix_data = 'T_flange_camera' in config
        
        # 判断是否有效
        is_valid = False
        status_reason = []
        
        if skip_val:
            is_valid = True
            status_reason.append("开发模式")
        
        if has_calib_id:
            is_valid = True
            status_reason.append(f"标定ID: {config['calibration_id']}")
        
        if has_matrix_data:
            is_valid = True
            status_reason.append("含变换矩阵")
        
        if matrix_type != 'identity' and not is_valid:
            is_valid = True
            status_reason.append(f"矩阵: {matrix_type}")
        
        # 统计
        if is_valid:
            status = "✅ 有效"
            valid_count += 1
        else:
            status = "❌ 无效"
            invalid_count += 1
            status_reason.append("缺少配置")
        
        # 添加到表格
        table_data.append([
            recipe.id,
            recipe.recipe_name[:30],
            f"POS{recipe.position_no}",
            f"L{recipe.layer_no}",
            matrix_type,
            "✓" if skip_val else "✗",
            "✓" if has_calib_id else "✗",
            status,
            ", ".join(status_reason) if status_reason else "-"
        ])
    
    # 打印表格
    headers = [
        "ID", "配方名称", "POS", "层号", "Matrix", "Skip", "标定ID", "状态", "说明"
    ]
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # 统计信息
    print("\n" + "=" * 80)
    print("统计信息")
    print("=" * 80)
    print(f"✅ 有效配置: {valid_count} 个 ({valid_count/len(recipes)*100:.1f}%)")
    print(f"❌ 无效配置: {invalid_count} 个 ({invalid_count/len(recipes)*100:.1f}%)")
    print(f"📊 总计: {len(recipes)} 个配方")
    print("=" * 80)
    
    # 提供建议
    if invalid_count > 0:
        print("\n⚠️  发现无效配置！建议操作：")
        print("   1. 运行更新脚本: python update_recipes_hand_eye_config.py")
        print("   2. 或手动编辑配方，添加 skip_validation: true")
        print("   3. 或完成手眼标定，配置 calibration_id\n")
    else:
        print("\n🎉 所有配方配置正确！可以正常使用定位功能。\n")
    
    return invalid_count == 0


def show_detailed_config(recipe_id):
    """显示指定配方的详细配置"""
    try:
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
    except RackLocationRecipe.DoesNotExist:
        print(f"❌ 配方 ID {recipe_id} 不存在！")
        return
    
    import json
    
    print("\n" + "=" * 80)
    print(f"配方详细配置 - {recipe.recipe_name} (ID: {recipe.id})")
    print("=" * 80)
    
    print(f"\n基本信息：")
    print(f"  配方名称: {recipe.recipe_name}")
    print(f"  POS: {recipe.position_no}, 层号: {recipe.layer_no}")
    print(f"  料架侧: {recipe.rack_side}")
    print(f"  状态: {'✅ 已启用' if recipe.enabled else '❌ 已禁用'}")
    
    print(f"\n标准坐标：")
    print(f"  X: {recipe.standard_x} mm")
    print(f"  Y: {recipe.standard_y} mm")
    print(f"  Z: {recipe.standard_z} mm")
    print(f"  Rz: {recipe.standard_rz}°")
    
    print(f"\n手眼标定配置：")
    config = recipe.hand_eye_config or {}
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    print(f"\nROI 配置：")
    roi_config = recipe.roi_config or {}
    print(json.dumps(roi_config, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 80)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='检查配方手眼标定配置')
    parser.add_argument('--detail', type=int, metavar='RECIPE_ID', 
                       help='显示指定配方的详细配置')
    
    args = parser.parse_args()
    
    if args.detail:
        show_detailed_config(args.detail)
    else:
        try:
            is_ok = check_configs()
            sys.exit(0 if is_ok else 1)
        except ImportError:
            print("\n⚠️  注意: tabulate 模块未安装")
            print("   安装命令: pip install tabulate")
            print("   或使用简化版本显示\n")
            
            # 简化版本
            recipes = RackLocationRecipe.objects.all()
            for recipe in recipes:
                config = recipe.hand_eye_config or {}
                skip_val = config.get('skip_validation', False)
                print(f"{'✅' if skip_val else '❌'} {recipe.recipe_name} - skip_validation: {skip_val}")

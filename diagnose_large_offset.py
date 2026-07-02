"""
诊断和修复大偏差问题
"""
import os
import sys
import django
import numpy as np
import json

# 设置Django环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe, RackLocationResult
from apps.vision.rack_location import RackLocationService
from decimal import Decimal


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_recipe_configuration():
    """检查配方配置"""
    print_section("检查配方配置")
    
    recipes = RackLocationRecipe.objects.filter(enabled=True).order_by('position_no', 'layer_no')
    
    if not recipes.exists():
        print("✗ 没有找到启用的配方")
        return
    
    print(f"找到 {recipes.count()} 个启用的配方:\n")
    
    for recipe in recipes:
        print(f"配方 ID={recipe.id}: {recipe.recipe_name}")
        print(f"  位置/层: POS{recipe.position_no} / L{recipe.layer_no}")
        print(f"  标准值:")
        print(f"    X = {recipe.standard_x} mm")
        print(f"    Y = {recipe.standard_y} mm")
        print(f"    Z = {recipe.standard_z} mm")
        print(f"    Rz = {getattr(recipe, 'standard_rz', 0)} deg")
        
        # 检查标准值是否合理
        issues = []
        if abs(float(recipe.standard_x)) > 2000:
            issues.append(f"  ⚠️  X标准值过大: {recipe.standard_x}")
        if abs(float(recipe.standard_y)) > 2000:
            issues.append(f"  ⚠️  Y标准值过大: {recipe.standard_y}")
        if abs(float(recipe.standard_z)) > 2000:
            issues.append(f"  ⚠️  Z标准值过大: {recipe.standard_z}")
        
        if issues:
            print(f"\n  问题:")
            for issue in issues:
                print(issue)
        else:
            print(f"  ✓ 标准值配置正常")
        
        print()


def check_recent_results():
    """检查最近的定位结果"""
    print_section("检查最近的定位结果")
    
    results = RackLocationResult.objects.order_by('-created_at')[:5]
    
    if not results.exists():
        print("✗ 没有找到定位结果")
        return
    
    print(f"最近 {results.count()} 条定位结果:\n")
    
    for result in results:
        print(f"结果 ID={result.id} (创建于 {result.created_at.strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"  配方: {result.recipe.recipe_name if result.recipe else 'N/A'}")
        print(f"  实际测量值:")
        print(f"    X = {result.actual_x} mm")
        print(f"    Y = {result.actual_y} mm")
        print(f"    Z = {result.actual_z} mm")
        print(f"  偏差值:")
        print(f"    ΔX = {result.offset_x} mm")
        print(f"    ΔY = {result.offset_y} mm")
        print(f"    ΔZ = {result.offset_z} mm")
        print(f"    ΔRz = {result.offset_rz} deg")
        print(f"  成功: {result.is_success}")
        print(f"  置信度: {result.confidence}")
        
        # 分析偏差
        if abs(float(result.offset_x)) > 100 or abs(float(result.offset_y)) > 100 or abs(float(result.offset_z)) > 100:
            print(f"  ❌ 偏差值异常大！")
            
            # 检查可能的原因
            if result.recipe:
                print(f"\n  诊断分析:")
                print(f"    配方标准X: {result.recipe.standard_x}")
                print(f"    实际测量X: {result.actual_x}")
                print(f"    计算的偏差X: {result.offset_x}")
                print(f"    验算: {float(result.actual_x) - float(result.recipe.standard_x):.2f}")
                
                # 检查是否是符号问题
                if abs(float(result.actual_x) - float(result.recipe.standard_x) - float(result.offset_x)) < 0.1:
                    print(f"    ✓ 偏差计算正确")
                elif abs(float(result.actual_x) - float(result.recipe.standard_x) + float(result.offset_x)) < 0.1:
                    print(f"    ⚠️  偏差符号可能反了")
                else:
                    print(f"    ❌ 偏差计算错误")
                
                # 检查实际值是否合理
                if abs(float(result.actual_x)) < 10:
                    print(f"    ⚠️  实际测量X值接近0，可能是测量失败")
                if abs(float(result.actual_y)) < 10:
                    print(f"    ⚠️  实际测量Y值接近0，可能是测量失败")
                if abs(float(result.actual_z)) < 10:
                    print(f"    ⚠️  实际测量Z值接近0，可能是测量失败")
        else:
            print(f"  ✓ 偏差值正常")
        
        print()


def suggest_fixes():
    """建议修复方案"""
    print_section("修复建议")
    
    print("""
常见问题和解决方案:

1. **标准值配置错误**
   问题: 标准值（standard_x/y/z）配置为实际工件坐标，而不是相对偏差
   解决: 
   - 标准值应该是相对机器人基坐标的期望位置
   - 例如: standard_x=1100, standard_y=600, standard_z=800
   - 如果配置错误，请到配方管理页面修正

2. **点云坐标系问题**
   问题: 点云数据的坐标系与标准值坐标系不一致
   解决:
   - 检查手眼标定是否正确
   - 确认点云已正确转换到机器人基坐标系
   - 检查坐标转换矩阵

3. **实际测量值为0或接近0**
   问题: 点云裁剪失败，提取不到有效特征
   解决:
   - 检查ROI配置是否正确
   - 确认点云数据质量
   - 调整ROI范围，确保包含目标特征

4. **偏差计算公式错误**
   问题: offset = actual - standard 的符号可能反了
   解决:
   - 检查rack_positioning_algorithm.py中的计算公式
   - 确认: offset_x = actual_x - standard_x

5. **单位不一致**
   问题: 点云单位是m，但标准值单位是mm
   解决:
   - 统一使用mm作为单位
   - 检查点云数据的单位
    """)


def fix_offset_calculation():
    """修复偏差计算（如果是公式错误）"""
    print_section("检查偏差计算公式")
    
    print("检查算法文件中的偏差计算...")
    
    algo_file = "apps/vision/rack_positioning_algorithm.py"
    
    if not os.path.exists(algo_file):
        print(f"✗ 找不到文件: {algo_file}")
        return
    
    with open(algo_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查偏差计算的关键行
    if 'result.offset_x = result.actual_x - standard_x' in content:
        print("✓ X轴偏差计算公式正确: offset_x = actual_x - standard_x")
    else:
        print("⚠️  未找到预期的X轴偏差计算公式")
    
    if 'result.offset_y = result.actual_y - standard_y' in content:
        print("✓ Y轴偏差计算公式正确: offset_y = actual_y - standard_y")
    else:
        print("⚠️  未找到预期的Y轴偏差计算公式")
    
    if 'result.offset_z = result.actual_z - standard_z' in content:
        print("✓ Z轴偏差计算公式正确: offset_z = actual_z - standard_z")
    else:
        print("⚠️  未找到预期的Z轴偏差计算公式")


def create_test_recipe():
    """创建测试配方"""
    print_section("创建测试配方")
    
    print("创建一个测试配方，使用合理的标准值...")
    
    # 创建测试配方
    test_recipe, created = RackLocationRecipe.objects.get_or_create(
        recipe_name="测试配方-标准值验证",
        position_no=1,
        layer_no=99,  # 使用特殊的层号避免冲突
        defaults={
            'rack_type': 'STANDARD',
            'rack_side': 'LEFT',
            'layer_count': 1,
            'capture_pose_name': 'TEST_POSE',
            'standard_x': Decimal('1100.000'),  # 合理的标准值
            'standard_y': Decimal('600.000'),
            'standard_z': Decimal('800.000'),
            'standard_rz': Decimal('0.000'),
            'enabled': False,  # 默认不启用
        }
    )
    
    if created:
        print(f"✓ 创建测试配方: ID={test_recipe.id}")
    else:
        print(f"✓ 测试配方已存在: ID={test_recipe.id}")
    
    print(f"\n测试配方标准值:")
    print(f"  X = {test_recipe.standard_x} mm")
    print(f"  Y = {test_recipe.standard_y} mm")
    print(f"  Z = {test_recipe.standard_z} mm")
    print(f"\n如果实际测量值为 X=1095, Y=605, Z=798，则:")
    print(f"  期望偏差: ΔX = -5mm, ΔY = +5mm, ΔZ = -2mm")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  3D 料架定位大偏差问题诊断工具")
    print("=" * 70)
    
    try:
        # 1. 检查配方配置
        check_recipe_configuration()
        
        # 2. 检查最近的结果
        check_recent_results()
        
        # 3. 检查偏差计算公式
        fix_offset_calculation()
        
        # 4. 创建测试配方
        create_test_recipe()
        
        # 5. 提供修复建议
        suggest_fixes()
        
        print("\n" + "=" * 70)
        print("  诊断完成")
        print("=" * 70)
        print("\n下一步操作:")
        print("1. 检查配方的标准值是否配置正确")
        print("2. 如果标准值错误，到配方管理页面修正")
        print("3. 确认点云数据的坐标系和单位")
        print("4. 重新采集点云并测试")
        print()
        
    except Exception as e:
        print(f"\n✗ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

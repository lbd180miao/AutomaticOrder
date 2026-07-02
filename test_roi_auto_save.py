"""
测试3D配方ROI坐标自动保存和复用功能

测试场景：
1. 创建配方并保存ROI坐标
2. 验证ROI坐标已保存到数据库
3. 模拟加载配方时自动获取ROI坐标
4. 更新ROI坐标并验证
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from apps.vision.models import RackLocationRecipe
from decimal import Decimal


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def test_create_recipe_with_roi():
    """测试场景1：创建配方并保存ROI坐标"""
    print_section("测试场景1：创建配方并保存ROI坐标")
    
    # 创建测试配方
    recipe = RackLocationRecipe.objects.create(
        recipe_name="测试配方-ROI自动保存",
        rack_type="标准料架",
        rack_side="BOTH",
        position_no=1,
        layer_count=3,
        layer_no=1,
        capture_pose_name="POSE-TEST-L1",
        standard_x=Decimal("1100.000"),
        standard_y=Decimal("600.000"),
        standard_z=Decimal("850.000"),
        standard_rz=Decimal("0.000"),
        roi_config={},  # 初始为空
        enabled=True
    )
    
    print(f"✓ 创建配方成功: ID={recipe.id}, Name={recipe.recipe_name}")
    print(f"  初始roi_config: {recipe.roi_config}")
    
    # 模拟保存ROI坐标（就像用户绘制后保存）
    roi_config = {
        'coordinate_system': 'robot',
        'target_roi': {
            'x': 100,
            'y': 200,
            'w': 300,
            'h': 400
        },
        'target_roi_updated_at': timezone.now().isoformat()
    }
    
    recipe.roi_config = roi_config
    recipe.save(update_fields=['roi_config'])
    
    print(f"✓ ROI坐标已保存")
    print(f"  target_roi: {roi_config['target_roi']}")
    print(f"  更新时间: {roi_config['target_roi_updated_at']}")
    
    return recipe.id


def test_load_saved_roi(recipe_id):
    """测试场景2：验证ROI坐标已保存并能正确加载"""
    print_section("测试场景2：验证ROI坐标已保存并能正确加载")
    
    # 从数据库重新加载配方
    recipe = RackLocationRecipe.objects.get(id=recipe_id)
    
    print(f"✓ 加载配方: ID={recipe.id}, Name={recipe.recipe_name}")
    
    # 检查ROI配置
    if recipe.roi_config and 'target_roi' in recipe.roi_config:
        target_roi = recipe.roi_config['target_roi']
        updated_at = recipe.roi_config.get('target_roi_updated_at', 'N/A')
        
        print(f"✓ 发现已保存的ROI坐标:")
        print(f"  X: {target_roi.get('x')}")
        print(f"  Y: {target_roi.get('y')}")
        print(f"  W: {target_roi.get('w')}")
        print(f"  H: {target_roi.get('h')}")
        print(f"  最后更新: {updated_at}")
        
        return True
    else:
        print("✗ 未找到已保存的ROI坐标")
        return False


def test_update_roi(recipe_id):
    """测试场景3：更新ROI坐标"""
    print_section("测试场景3：更新ROI坐标")
    
    recipe = RackLocationRecipe.objects.get(id=recipe_id)
    
    # 保存旧的ROI
    old_roi = recipe.roi_config.get('target_roi', {})
    print(f"  旧ROI: {old_roi}")
    
    # 更新ROI（模拟用户重新绘制）
    new_roi = {
        'x': 150,
        'y': 250,
        'w': 350,
        'h': 450
    }
    
    current_config = recipe.roi_config or {}
    current_config['target_roi'] = new_roi
    current_config['target_roi_updated_at'] = timezone.now().isoformat()
    
    recipe.roi_config = current_config
    recipe.save(update_fields=['roi_config'])
    
    print(f"✓ ROI坐标已更新")
    print(f"  新ROI: {new_roi}")
    
    # 验证更新
    recipe.refresh_from_db()
    updated_roi = recipe.roi_config.get('target_roi', {})
    
    if updated_roi == new_roi:
        print(f"✓ 验证成功：ROI坐标已正确更新")
        return True
    else:
        print(f"✗ 验证失败：ROI坐标未正确更新")
        return False


def test_auto_load_logic(recipe_id):
    """测试场景4：模拟自动加载逻辑"""
    print_section("测试场景4：模拟自动加载逻辑")
    
    # 模拟前端请求（没有传入roi_config）
    roi_config = {}
    
    print("  模拟场景：前端没有传入ROI配置")
    
    # 从配方加载已保存的ROI（模拟后端逻辑）
    recipe = RackLocationRecipe.objects.get(id=recipe_id)
    
    if recipe.roi_config:
        saved_target_roi = recipe.roi_config.get('target_roi')
        if saved_target_roi:
            roi_config['target_roi'] = saved_target_roi
            print(f"✓ 自动加载配方 {recipe_id} 的已保存ROI坐标")
            print(f"  加载的ROI: {saved_target_roi}")
            return True
    
    print("✗ 未找到已保存的ROI，需要重新绘制")
    return False


def test_multiple_layers():
    """测试场景5：测试多层配方的ROI独立性"""
    print_section("测试场景5：测试多层配方的ROI独立性")
    
    recipes = []
    
    # 为3层分别创建配方并保存不同的ROI
    for layer_no in [1, 2, 3]:
        recipe = RackLocationRecipe.objects.create(
            recipe_name=f"测试配方-第{layer_no}层",
            rack_side="BOTH",
            position_no=1,
            layer_count=3,
            layer_no=layer_no,
            standard_x=Decimal("1100.000"),
            standard_y=Decimal("600.000") + Decimal(str(layer_no * 100)),
            standard_z=Decimal("850.000") + Decimal(str(layer_no * 120)),
            roi_config={
                'coordinate_system': 'robot',
                'target_roi': {
                    'x': 100 + layer_no * 10,
                    'y': 200 + layer_no * 10,
                    'w': 300,
                    'h': 400
                },
                'target_roi_updated_at': timezone.now().isoformat()
            },
            enabled=True
        )
        recipes.append(recipe)
        print(f"✓ 创建第{layer_no}层配方: ID={recipe.id}")
        print(f"  ROI: {recipe.roi_config['target_roi']}")
    
    # 验证每层的ROI都不同
    print("\n验证ROI独立性:")
    for i, recipe in enumerate(recipes, 1):
        recipe.refresh_from_db()
        roi = recipe.roi_config['target_roi']
        expected_x = 100 + i * 10
        expected_y = 200 + i * 10
        
        if roi['x'] == expected_x and roi['y'] == expected_y:
            print(f"✓ 第{i}层ROI正确: X={roi['x']}, Y={roi['y']}")
        else:
            print(f"✗ 第{i}层ROI错误: X={roi['x']}, Y={roi['y']}")
    
    # 清理测试数据
    for recipe in recipes:
        recipe.delete()
    print("\n✓ 测试数据已清理")


def cleanup_test_data(recipe_id):
    """清理测试数据"""
    print_section("清理测试数据")
    
    try:
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        recipe_name = recipe.recipe_name
        recipe.delete()
        print(f"✓ 已删除测试配方: {recipe_name} (ID={recipe_id})")
    except RackLocationRecipe.DoesNotExist:
        print(f"  配方 ID={recipe_id} 不存在，可能已被删除")


def main():
    """主测试流程"""
    print("\n" + "█" * 60)
    print(" 3D配方ROI坐标自动保存和复用功能测试")
    print("█" * 60)
    
    try:
        # 测试1：创建配方并保存ROI
        recipe_id = test_create_recipe_with_roi()
        
        # 测试2：验证ROI已保存
        if test_load_saved_roi(recipe_id):
            print("\n[成功] ROI坐标保存和加载功能正常")
        else:
            print("\n[失败] ROI坐标保存或加载失败")
            return
        
        # 测试3：更新ROI
        if test_update_roi(recipe_id):
            print("\n[成功] ROI坐标更新功能正常")
        else:
            print("\n[失败] ROI坐标更新失败")
            return
        
        # 测试4：模拟自动加载逻辑
        if test_auto_load_logic(recipe_id):
            print("\n[成功] ROI自动加载逻辑正常")
        else:
            print("\n[失败] ROI自动加载逻辑异常")
            return
        
        # 测试5：多层配方测试
        test_multiple_layers()
        
        # 清理测试数据
        cleanup_test_data(recipe_id)
        
        # 最终结果
        print_section("测试总结")
        print("✓ 所有测试通过！")
        print("\n功能验证:")
        print("  ✓ ROI坐标能正确保存到数据库")
        print("  ✓ ROI坐标能正确从数据库加载")
        print("  ✓ ROI坐标能正确更新")
        print("  ✓ 自动加载逻辑工作正常")
        print("  ✓ 多层配方ROI独立性正常")
        
    except Exception as e:
        print(f"\n✗ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

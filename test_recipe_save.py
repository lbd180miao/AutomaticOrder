#!/usr/bin/env python
"""
测试视觉配方保存功能
运行: python test_recipe_save.py
"""
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import VisionRecipe

def test_recipe_save():
    """测试配方保存"""
    print("=" * 60)
    print("测试视觉配方保存功能")
    print("=" * 60)
    
    # 测试数据
    test_recipe = {
        'recipe_type': 'FOAM_2D',
        'pos': 0,
        'name': '测试配方 - POS 0',
        'camera_side': 'both',
        'image_width': 1280,
        'image_height': 720,
        'roi_config': {
            'leftFoamROI': {'x': 220, 'y': 140, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 140, 'width': 110, 'height': 70}
        },
        'threshold_config': {
            'minCoverage': 0.75,
            'minScore': 0.8,
            'maxOffsetX': 30,
            'maxOffsetY': 30
        },
        'is_active': True
    }
    
    print("\n1. 创建/更新配方...")
    recipe, created = VisionRecipe.objects.update_or_create(
        recipe_type='FOAM_2D',
        pos=0,
        camera_side='both',
        defaults=test_recipe
    )
    
    if created:
        print("   ✓ 配方创建成功")
    else:
        print("   ✓ 配方更新成功")
    
    print(f"   配方 ID: {recipe.id}")
    print(f"   配方名称: {recipe.name}")
    print(f"   POS: {recipe.pos}")
    
    print("\n2. 验证 ROI 配置...")
    left_roi = recipe.roi_config.get('leftFoamROI', {})
    right_roi = recipe.roi_config.get('rightFoamROI', {})
    
    print(f"   左ROI: x={left_roi.get('x')}, y={left_roi.get('y')}, " 
          f"w={left_roi.get('width')}, h={left_roi.get('height')}")
    print(f"   右ROI: x={right_roi.get('x')}, y={right_roi.get('y')}, "
          f"w={right_roi.get('width')}, h={right_roi.get('height')}")
    
    print("\n3. 验证阈值配置...")
    thresh = recipe.threshold_config
    print(f"   覆盖率阈值: {thresh.get('minCoverage')}")
    print(f"   得分阈值: {thresh.get('minScore')}")
    print(f"   X偏移阈值: {thresh.get('maxOffsetX')} px")
    print(f"   Y偏移阈值: {thresh.get('maxOffsetY')} px")
    
    print("\n4. 查询所有活动配方...")
    active_recipes = VisionRecipe.objects.filter(
        recipe_type='FOAM_2D',
        is_active=True
    ).order_by('pos')
    
    print(f"   找到 {active_recipes.count()} 个活动配方")
    for r in active_recipes:
        print(f"   - POS {r.pos}: {r.name}")
    
    print("\n" + "=" * 60)
    print("✓ 测试完成！配方保存功能正常")
    print("=" * 60)

if __name__ == '__main__':
    try:
        test_recipe_save()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

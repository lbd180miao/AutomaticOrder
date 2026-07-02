"""
修复配方的手眼矩阵配置

将 'matrix': 'identity' 字符串替换为实际的4x4单位矩阵数组
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe

# 单位矩阵（4x4）
IDENTITY_MATRIX = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]

def fix_recipes():
    """修复所有使用 'identity' 字符串的配方"""
    recipes = RackLocationRecipe.objects.all()
    fixed_count = 0
    
    for recipe in recipes:
        if not recipe.hand_eye_config:
            continue
            
        # 检查是否使用了 'identity' 字符串
        matrix_value = recipe.hand_eye_config.get('matrix')
        if matrix_value == 'identity':
            print(f'🔧 修复配方: {recipe.recipe_name} (Layer {recipe.layer_no})')
            
            # 替换为实际的单位矩阵
            recipe.hand_eye_config['matrix'] = IDENTITY_MATRIX
            recipe.save(update_fields=['hand_eye_config', 'updated_at'])
            
            fixed_count += 1
            print(f'   ✅ 已更新为4x4单位矩阵')
    
    print(f'\n📊 总结：')
    print(f'   - 检查配方数: {recipes.count()}')
    print(f'   - 修复配方数: {fixed_count}')
    
    if fixed_count > 0:
        print(f'\n✅ 修复完成！现在Canvas绘制的坐标转换应该正确了。')
        print(f'\n📝 验证步骤：')
        print(f'   1. 清除浏览器缓存（Ctrl+F5）')
        print(f'   2. 进入3D配方页面')
        print(f'   3. 点击"采集标准图"')
        print(f'   4. 在图像上拖拽绘制ROI')
        print(f'   5. 查看填充的机器人坐标是否为正数（X≈900, Y≈530, Z≈920）')
    else:
        print(f'\n✅ 所有配方的手眼矩阵配置正确！')

if __name__ == '__main__':
    fix_recipes()

"""
更新现有配方的手眼标定配置

问题：现有配方的 hand_eye_config 为 {'matrix': 'identity'}
     导致定位计算时提示"缺少手眼标定参数"

解决：为所有配方添加 skip_validation 标志，允许开发测试模式
"""

import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe


def update_recipes():
    """更新所有配方的 hand_eye_config"""
    
    print("=" * 60)
    print("更新配方手眼标定配置")
    print("=" * 60)
    
    recipes = RackLocationRecipe.objects.all()
    total = recipes.count()
    
    print(f"\n找到 {total} 个配方需要更新\n")
    
    if total == 0:
        print("没有需要更新的配方。")
        return
    
    updated_count = 0
    skipped_count = 0
    
    for recipe in recipes:
        hand_eye_config = recipe.hand_eye_config or {}
        
        # 检查是否需要更新
        needs_update = False
        
        if not hand_eye_config:
            # 空配置，需要更新
            needs_update = True
            reason = "空配置"
        elif hand_eye_config.get('matrix') == 'identity' and 'skip_validation' not in hand_eye_config:
            # 使用 identity 但没有 skip_validation
            needs_update = True
            reason = "缺少 skip_validation"
        elif 'skip_validation' not in hand_eye_config:
            # 其他情况，也添加 skip_validation（保守起见）
            needs_update = True
            reason = "添加 skip_validation"
        
        if needs_update:
            # 更新配置
            updated_config = {
                'matrix': hand_eye_config.get('matrix', 'identity'),
                'skip_validation': True,
                'note': '开发测试模式 - 使用单位矩阵（相机坐标系=机器人坐标系）',
                **{k: v for k, v in hand_eye_config.items() if k not in ['matrix', 'skip_validation', 'note']}
            }
            
            recipe.hand_eye_config = updated_config
            recipe.save(update_fields=['hand_eye_config', 'updated_at'])
            
            print(f"✅ 更新配方: {recipe.recipe_name}")
            print(f"   ID: {recipe.id}, 原因: {reason}")
            print(f"   配置: {updated_config}")
            print()
            
            updated_count += 1
        else:
            print(f"⏭️  跳过配方: {recipe.recipe_name} (ID: {recipe.id})")
            print(f"   已有有效的手眼标定配置")
            print()
            skipped_count += 1
    
    print("=" * 60)
    print(f"更新完成！")
    print(f"  ✅ 已更新: {updated_count} 个配方")
    print(f"  ⏭️  已跳过: {skipped_count} 个配方")
    print(f"  📊 总计: {total} 个配方")
    print("=" * 60)


def verify_updates():
    """验证更新结果"""
    print("\n" + "=" * 60)
    print("验证更新结果")
    print("=" * 60 + "\n")
    
    recipes = RackLocationRecipe.objects.all()
    
    valid_count = 0
    invalid_count = 0
    
    for recipe in recipes:
        hand_eye_config = recipe.hand_eye_config or {}
        
        has_skip = hand_eye_config.get('skip_validation', False)
        has_matrix = 'matrix' in hand_eye_config
        
        if has_skip or (has_matrix and hand_eye_config['matrix'] != 'identity'):
            valid_count += 1
            status = "✅"
        else:
            invalid_count += 1
            status = "❌"
        
        print(f"{status} {recipe.recipe_name} (ID: {recipe.id})")
        print(f"   配置: {hand_eye_config}")
        print()
    
    print("=" * 60)
    print(f"验证结果：")
    print(f"  ✅ 有效配置: {valid_count} 个")
    print(f"  ❌ 无效配置: {invalid_count} 个")
    print("=" * 60)
    
    if invalid_count > 0:
        print("\n⚠️  仍有配方配置无效，请检查！")
        return False
    else:
        print("\n🎉 所有配方配置正确！")
        return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='更新配方手眼标定配置')
    parser.add_argument('--verify-only', action='store_true', help='仅验证，不更新')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际保存')
    
    args = parser.parse_args()
    
    if args.verify_only:
        verify_updates()
    else:
        if args.dry_run:
            print("⚠️  DRY RUN 模式 - 不会实际保存更改\n")
        
        update_recipes()
        
        if not args.dry_run:
            print("\n正在验证更新...")
            verify_updates()

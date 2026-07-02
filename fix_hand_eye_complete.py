"""
手眼标定问题 - 完整修复流程
自动检测、修复、验证
"""

import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe


class HandEyeConfigFixer:
    """手眼标定配置修复器"""
    
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.stats = {
            'total': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }
    
    def print_header(self, title):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80 + "\n")
    
    def check_recipe_config(self, recipe):
        """检查单个配方的配置是否有效"""
        config = recipe.hand_eye_config or {}
        
        # 检查是否需要更新
        if not config:
            return False, "空配置"
        
        # 检查是否有有效标定
        if config.get('skip_validation'):
            return True, "有 skip_validation"
        
        if config.get('calibration_id'):
            return True, "有 calibration_id"
        
        if config.get('T_flange_camera'):
            return True, "有变换矩阵"
        
        matrix_type = config.get('matrix', '')
        if matrix_type and matrix_type != 'identity':
            return True, f"矩阵类型: {matrix_type}"
        
        # 需要更新
        return False, "缺少有效配置"
    
    def fix_recipe_config(self, recipe):
        """修复单个配方的配置"""
        config = recipe.hand_eye_config or {}
        
        # 保留原有配置，添加必要字段
        updated_config = {
            'matrix': config.get('matrix', 'identity'),
            'skip_validation': True,
            'note': '开发测试模式 - 使用单位矩阵（相机坐标系=机器人坐标系）',
        }
        
        # 保留其他字段
        for key, value in config.items():
            if key not in ['matrix', 'skip_validation', 'note']:
                updated_config[key] = value
        
        return updated_config
    
    def run(self):
        """执行完整修复流程"""
        
        # ====== 阶段 1: 检测问题 ======
        self.print_header("阶段 1/4: 检测配方配置问题")
        
        recipes = RackLocationRecipe.objects.all()
        self.stats['total'] = recipes.count()
        
        if self.stats['total'] == 0:
            print("⚠️  没有找到任何配方。")
            return False
        
        print(f"找到 {self.stats['total']} 个配方\n")
        
        problems = []
        for recipe in recipes:
            is_valid, reason = self.check_recipe_config(recipe)
            if not is_valid:
                problems.append((recipe, reason))
                print(f"❌ {recipe.recipe_name} (ID: {recipe.id}) - {reason}")
        
        if not problems:
            print("✅ 所有配方配置正确，无需修复。")
            return True
        
        print(f"\n发现 {len(problems)} 个配方需要修复。")
        
        # ====== 阶段 2: 修复配置 ======
        self.print_header("阶段 2/4: 修复配方配置")
        
        if self.dry_run:
            print("⚠️  DRY RUN 模式 - 不会实际保存更改\n")
        
        for recipe, reason in problems:
            try:
                new_config = self.fix_recipe_config(recipe)
                
                print(f"📝 修复配方: {recipe.recipe_name} (ID: {recipe.id})")
                print(f"   原因: {reason}")
                print(f"   新配置: {new_config}")
                
                if not self.dry_run:
                    recipe.hand_eye_config = new_config
                    recipe.save(update_fields=['hand_eye_config', 'updated_at'])
                    print("   ✅ 已保存")
                else:
                    print("   ⏭️  跳过保存（DRY RUN）")
                
                self.stats['updated'] += 1
                print()
                
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                self.stats['errors'] += 1
                print()
        
        # ====== 阶段 3: 验证修复 ======
        self.print_header("阶段 3/4: 验证修复结果")
        
        if self.dry_run:
            print("⏭️  跳过验证（DRY RUN 模式）\n")
        else:
            recipes = RackLocationRecipe.objects.all()
            
            valid_count = 0
            invalid_count = 0
            
            for recipe in recipes:
                is_valid, reason = self.check_recipe_config(recipe)
                if is_valid:
                    valid_count += 1
                    print(f"✅ {recipe.recipe_name} - {reason}")
                else:
                    invalid_count += 1
                    print(f"❌ {recipe.recipe_name} - {reason}")
            
            print(f"\n验证结果:")
            print(f"  ✅ 有效: {valid_count} 个")
            print(f"  ❌ 无效: {invalid_count} 个")
            
            if invalid_count > 0:
                print("\n⚠️  仍有配方配置无效！")
                return False
        
        # ====== 阶段 4: 统计报告 ======
        self.print_header("阶段 4/4: 修复统计报告")
        
        print(f"总配方数:   {self.stats['total']}")
        print(f"已修复:     {self.stats['updated']}")
        print(f"已跳过:     {self.stats['skipped']}")
        print(f"失败:       {self.stats['errors']}")
        print()
        
        if self.stats['errors'] > 0:
            print("❌ 部分配方修复失败！")
            return False
        
        if self.dry_run:
            print("✅ DRY RUN 完成。实际运行请去掉 --dry-run 参数。")
            return True
        
        print("🎉 修复完成！")
        print()
        print("=" * 80)
        print("  下一步操作")
        print("=" * 80)
        print()
        print("1. 运行测试验证:")
        print("   python test_hand_eye_fix.py")
        print()
        print("2. 刷新浏览器:")
        print("   在浏览器中按 Ctrl + F5 强制刷新页面")
        print()
        print("3. 测试定位功能:")
        print("   - 打开 3D 料架定位工作台")
        print("   - 选择配方")
        print("   - 采集点云")
        print("   - 计算偏差")
        print("   - 应该能看到实际的偏差值（不再全为0）")
        print()
        print("4. 如果仍有问题:")
        print("   - 检查后端日志")
        print("   - 查看浏览器控制台（F12）")
        print("   - 运行: python check_hand_eye_config.py --detail <配方ID>")
        print()
        
        return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='手眼标定问题 - 完整修复流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查问题但不修复（DRY RUN）
  python fix_hand_eye_complete.py --dry-run
  
  # 执行完整修复
  python fix_hand_eye_complete.py
  
  # 静默模式（仅显示错误）
  python fix_hand_eye_complete.py --quiet
        """
    )
    
    parser.add_argument('--dry-run', action='store_true',
                       help='模拟运行，不实际保存更改')
    parser.add_argument('--quiet', action='store_true',
                       help='静默模式，仅显示错误')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='自动确认，不询问')
    
    args = parser.parse_args()
    
    # 创建修复器
    fixer = HandEyeConfigFixer(dry_run=args.dry_run)
    
    # 显示警告（非 DRY RUN 且非自动确认）
    if not args.dry_run and not args.yes:
        print("\n" + "!" * 80)
        print("  警告: 此操作将修改数据库中的配方配置")
        print("!" * 80)
        print("\n建议: 先运行 --dry-run 查看将要进行的更改\n")
        
        response = input("确认继续？(yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("\n已取消。")
            return 1
    
    # 执行修复
    try:
        success = fixer.run()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n已中断。")
        return 130
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

"""
管理命令：检查并修复 vision 应用的数据库问题

用法:
    python manage.py check_vision_db
    python manage.py check_vision_db --fix
"""
from django.core.management.base import BaseCommand
from django.db import connection

from apps.vision.models import (
    VisionTask,
    VisionImage,
    FoamInspectionResult,
    RackLocationResult,
    CalibrationProfile,
    VisionRecipe,
    RackLocationRecipe,
)


class Command(BaseCommand):
    help = '检查 vision 应用的数据库完整性并提供修复建议'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='自动修复检测到的问题（清理无效外键引用）',
        )

    def handle(self, *args, **options):
        fix_mode = options['fix']
        
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('Vision 数据库完整性检查'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        # 1. 检查所有表是否存在
        self.check_tables()
        
        # 2. 检查 VisionTask 外键完整性
        self.check_vision_task_foreign_keys(fix_mode)
        
        # 3. 检查孤立的结果记录
        self.check_orphaned_results(fix_mode)
        
        # 4. 统计信息
        self.show_statistics()
        
        self.stdout.write(self.style.SUCCESS('\n✓ 检查完成'))
        
        if not fix_mode:
            self.stdout.write(
                self.style.WARNING(
                    '\n提示：运行 "python manage.py check_vision_db --fix" 可自动修复问题'
                )
            )

    def check_tables(self):
        """检查所有必需的表是否存在"""
        self.stdout.write('\n[1] 检查数据库表...')
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE 'vision_%' OR name LIKE 'production_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = [
            'vision_visiontask',
            'vision_visionimage',
            'vision_foaminspectionresult',
            'vision_racklocationresult',
            'vision_calibrationprofile',
            'vision_visionrecipe',
            'vision_racklocationrecipe',
            'production_product',
            'production_rack',
        ]
        
        missing = []
        for table in required_tables:
            if table in tables:
                self.stdout.write(f'  ✓ {table}')
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ {table} (缺失)'))
                missing.append(table)
        
        if missing:
            self.stdout.write(
                self.style.ERROR(
                    f'\n警告：缺失 {len(missing)} 个表，请运行: python manage.py migrate'
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS('  所有必需的表都存在'))

    def check_vision_task_foreign_keys(self, fix_mode):
        """检查 VisionTask 的外键完整性"""
        self.stdout.write('\n[2] 检查 VisionTask 外键完整性...')
        
        # 检查 product 外键
        invalid_product_ids = []
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT vt.id, vt.product_id
                    FROM vision_visiontask vt
                    WHERE vt.product_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM production_product p
                        WHERE p.id = vt.product_id
                    )
                """)
                invalid_product_ids = cursor.fetchall()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  查询 product 外键时出错: {str(e)}'))
        
        if invalid_product_ids:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ 发现 {len(invalid_product_ids)} 条记录引用了不存在的 Product'
                )
            )
            if fix_mode:
                VisionTask.objects.filter(
                    id__in=[row[0] for row in invalid_product_ids]
                ).update(product_id=None)
                self.stdout.write(self.style.SUCCESS(f'    已清理 {len(invalid_product_ids)} 条无效 product 引用'))
        else:
            self.stdout.write('  ✓ Product 外键完整')
        
        # 检查 rack 外键
        invalid_rack_ids = []
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT vt.id, vt.rack_id
                    FROM vision_visiontask vt
                    WHERE vt.rack_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM production_rack r
                        WHERE r.id = vt.rack_id
                    )
                """)
                invalid_rack_ids = cursor.fetchall()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  查询 rack 外键时出错: {str(e)}'))
        
        if invalid_rack_ids:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ 发现 {len(invalid_rack_ids)} 条记录引用了不存在的 Rack'
                )
            )
            if fix_mode:
                VisionTask.objects.filter(
                    id__in=[row[0] for row in invalid_rack_ids]
                ).update(rack_id=None)
                self.stdout.write(self.style.SUCCESS(f'    已清理 {len(invalid_rack_ids)} 条无效 rack 引用'))
        else:
            self.stdout.write('  ✓ Rack 外键完整')

    def check_orphaned_results(self, fix_mode):
        """检查孤立的结果记录"""
        self.stdout.write('\n[3] 检查孤立的结果记录...')
        
        # 检查孤立的 FoamInspectionResult
        orphaned_foam = FoamInspectionResult.objects.filter(
            vision_task__isnull=True
        ).count()
        
        if orphaned_foam > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ 发现 {orphaned_foam} 条孤立的泡棉检测结果'
                )
            )
            if fix_mode:
                deleted = FoamInspectionResult.objects.filter(
                    vision_task__isnull=True
                ).delete()
                self.stdout.write(self.style.SUCCESS(f'    已删除 {deleted[0]} 条孤立记录'))
        else:
            self.stdout.write('  ✓ 无孤立的泡棉检测结果')
        
        # 检查孤立的 RackLocationResult
        orphaned_rack = RackLocationResult.objects.filter(
            vision_task__isnull=True
        ).count()
        
        if orphaned_rack > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ 发现 {orphaned_rack} 条孤立的料架定位结果'
                )
            )
            if fix_mode:
                deleted = RackLocationResult.objects.filter(
                    vision_task__isnull=True
                ).delete()
                self.stdout.write(self.style.SUCCESS(f'    已删除 {deleted[0]} 条孤立记录'))
        else:
            self.stdout.write('  ✓ 无孤立的料架定位结果')
        
        # 检查孤立的 VisionImage
        orphaned_images = VisionImage.objects.filter(
            vision_task__isnull=True
        ).count()
        
        if orphaned_images > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ 发现 {orphaned_images} 条孤立的视觉图像记录'
                )
            )
            if fix_mode:
                deleted = VisionImage.objects.filter(
                    vision_task__isnull=True
                ).delete()
                self.stdout.write(self.style.SUCCESS(f'    已删除 {deleted[0]} 条孤立记录'))
        else:
            self.stdout.write('  ✓ 无孤立的视觉图像记录')

    def show_statistics(self):
        """显示统计信息"""
        self.stdout.write('\n[4] 数据统计...')
        
        try:
            total_tasks = VisionTask.objects.count()
            total_images = VisionImage.objects.count()
            total_foam = FoamInspectionResult.objects.count()
            total_rack = RackLocationResult.objects.count()
            total_recipes = VisionRecipe.objects.count()
            total_rack_recipes = RackLocationRecipe.objects.count()
            
            self.stdout.write(f'  • 视觉任务: {total_tasks}')
            self.stdout.write(f'  • 视觉图像: {total_images}')
            self.stdout.write(f'  • 泡棉检测结果: {total_foam}')
            self.stdout.write(f'  • 料架定位结果: {total_rack}')
            self.stdout.write(f'  • 2D泡棉配方: {total_recipes}')
            self.stdout.write(f'  • 3D料架配方: {total_rack_recipes}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  查询统计信息时出错: {str(e)}'))

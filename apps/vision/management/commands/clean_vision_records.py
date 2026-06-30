"""
清理视觉模块的历史记录，只保留最近的一条记录。

使用方法:
    python manage.py clean_vision_records
    
选项:
    --dry-run: 只显示将要删除的记录数量，不实际删除
    --keep=N: 保留最近的 N 条记录（默认为 1）
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.vision.models import (
    VisionTask,
    RackLocationResult,
    FoamInspectionResult,
    VisionImage,
)


class Command(BaseCommand):
    help = '清理视觉模块中的历史记录，只保留最近的 N 条记录'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示将要删除的记录数量，不实际删除',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=1,
            help='保留最近的 N 条记录（默认为 1）',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        keep_count = options['keep']

        if keep_count < 0:
            self.stdout.write(self.style.ERROR('--keep 参数必须大于等于 0'))
            return

        self.stdout.write(self.style.WARNING(f'开始清理视觉记录，保留最近 {keep_count} 条...'))
        if dry_run:
            self.stdout.write(self.style.NOTICE('>>> 这是演练模式，不会实际删除数据 <<<'))

        # 统计信息
        stats = {
            'VisionTask': 0,
            'RackLocationResult': 0,
            'FoamInspectionResult': 0,
            'VisionImage': 0,
        }

        try:
            with transaction.atomic():
                # 1. 清理 VisionTask 及其关联的结果和图像
                total_tasks = VisionTask.objects.count()
                if total_tasks > keep_count:
                    # 获取要保留的最新记录的 ID
                    keep_task_ids = list(
                        VisionTask.objects.order_by('-created_at')
                        .values_list('id', flat=True)[:keep_count]
                    )
                    
                    # 查询要删除的任务
                    tasks_to_delete = VisionTask.objects.exclude(id__in=keep_task_ids)
                    delete_task_count = tasks_to_delete.count()
                    
                    if not dry_run:
                        # 删除会级联删除相关的 RackLocationResult, FoamInspectionResult, VisionImage
                        deleted = tasks_to_delete.delete()
                        stats['VisionTask'] = delete_task_count
                        # deleted[1] 是字典，包含了级联删除的详细信息
                        stats['RackLocationResult'] = deleted[1].get('vision.RackLocationResult', 0)
                        stats['FoamInspectionResult'] = deleted[1].get('vision.FoamInspectionResult', 0)
                        stats['VisionImage'] = deleted[1].get('vision.VisionImage', 0)
                    else:
                        stats['VisionTask'] = delete_task_count
                        # 在演练模式下，统计将被删除的关联记录
                        stats['RackLocationResult'] = RackLocationResult.objects.filter(
                            vision_task__in=tasks_to_delete
                        ).count()
                        stats['FoamInspectionResult'] = FoamInspectionResult.objects.filter(
                            vision_task__in=tasks_to_delete
                        ).count()
                        stats['VisionImage'] = VisionImage.objects.filter(
                            vision_task__in=tasks_to_delete
                        ).count()

                if dry_run:
                    # 演练模式下，回滚事务
                    raise Exception('Dry run mode - rolling back')

            # 输出统计信息
            self.stdout.write(self.style.SUCCESS('\n清理完成！统计信息：'))
            self.stdout.write(f'  - VisionTask: 删除 {stats["VisionTask"]} 条，保留 {min(total_tasks, keep_count)} 条')
            self.stdout.write(f'  - RackLocationResult: 删除 {stats["RackLocationResult"]} 条')
            self.stdout.write(f'  - FoamInspectionResult: 删除 {stats["FoamInspectionResult"]} 条')
            self.stdout.write(f'  - VisionImage: 删除 {stats["VisionImage"]} 条')
            
            total_deleted = sum(stats.values())
            self.stdout.write(self.style.SUCCESS(f'\n总共删除 {total_deleted} 条记录'))

        except Exception as e:
            if 'Dry run mode' in str(e):
                # 输出演练模式的统计信息
                self.stdout.write(self.style.NOTICE('\n演练模式统计信息：'))
                self.stdout.write(f'  - VisionTask: 将删除 {stats["VisionTask"]} 条，保留 {min(total_tasks, keep_count)} 条')
                self.stdout.write(f'  - RackLocationResult: 将删除 {stats["RackLocationResult"]} 条')
                self.stdout.write(f'  - FoamInspectionResult: 将删除 {stats["FoamInspectionResult"]} 条')
                self.stdout.write(f'  - VisionImage: 将删除 {stats["VisionImage"]} 条')
                
                total_will_delete = sum(stats.values())
                self.stdout.write(self.style.NOTICE(f'\n预计将删除 {total_will_delete} 条记录'))
                self.stdout.write(self.style.WARNING('\n使用 python manage.py clean_vision_records 来实际执行删除'))
            else:
                self.stdout.write(self.style.ERROR(f'\n清理失败: {str(e)}'))
                raise

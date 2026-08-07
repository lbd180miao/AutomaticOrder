"""
清理视觉任务记录的管理命令

只保留最近的N条泡棉检测记录和N条料架定位记录
"""
from django.core.management.base import BaseCommand
from apps.vision.models import VisionTask
from apps.core.constants import VisionTaskType


class Command(BaseCommand):
    help = '清理旧的视觉任务记录，只保留最近的指定数量记录'

    def add_arguments(self, parser):
        parser.add_argument(
            '--foam-keep',
            type=int,
            default=2,
            help='保留的泡棉检测记录数量（默认：2）'
        )
        parser.add_argument(
            '--rack-keep',
            type=int,
            default=2,
            help='保留的料架定位记录数量（默认：2）'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅显示将要删除的记录，不实际删除'
        )

    def handle(self, *args, **options):
        foam_keep = options['foam_keep']
        rack_keep = options['rack_keep']
        dry_run = options['dry_run']

        self.stdout.write(self.style.WARNING(
            f'\n开始清理视觉任务记录...'
        ))
        self.stdout.write(f'保留泡棉检测记录数: {foam_keep}')
        self.stdout.write(f'保留料架定位记录数: {rack_keep}')
        if dry_run:
            self.stdout.write(self.style.NOTICE('【演习模式】不会实际删除记录\n'))

        # 处理泡棉检测记录
        foam_tasks = VisionTask.objects.filter(
            task_type=VisionTaskType.FOAM_INSPECTION
        ).order_by('-created_at')

        foam_total = foam_tasks.count()
        foam_to_delete_ids = list(foam_tasks.values_list('id', flat=True)[foam_keep:])
        foam_delete_count = len(foam_to_delete_ids)

        self.stdout.write(f'\n泡棉检测记录:')
        self.stdout.write(f'  总数: {foam_total}')
        self.stdout.write(f'  保留: {min(foam_keep, foam_total)}')
        self.stdout.write(f'  删除: {foam_delete_count}')

        if foam_delete_count > 0:
            if not dry_run:
                deleted_count, _ = VisionTask.objects.filter(id__in=foam_to_delete_ids).delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ 已删除 {deleted_count} 条泡棉检测记录'
                ))
            else:
                self.stdout.write(self.style.NOTICE(
                    f'  → 将删除以下泡棉记录 ID: {foam_to_delete_ids[:10]}...'
                ))

        # 处理料架定位记录
        rack_tasks = VisionTask.objects.filter(
            task_type=VisionTaskType.RACK_LOCATING
        ).order_by('-created_at')

        rack_total = rack_tasks.count()
        rack_to_delete_ids = list(rack_tasks.values_list('id', flat=True)[rack_keep:])
        rack_delete_count = len(rack_to_delete_ids)

        self.stdout.write(f'\n料架定位记录:')
        self.stdout.write(f'  总数: {rack_total}')
        self.stdout.write(f'  保留: {min(rack_keep, rack_total)}')
        self.stdout.write(f'  删除: {rack_delete_count}')

        if rack_delete_count > 0:
            if not dry_run:
                deleted_count, _ = VisionTask.objects.filter(id__in=rack_to_delete_ids).delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ 已删除 {deleted_count} 条料架定位记录'
                ))
            else:
                self.stdout.write(self.style.NOTICE(
                    f'  → 将删除以下料架记录 ID: {rack_to_delete_ids[:10]}...'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'\n清理完成！总共{"将"if dry_run else "已"}删除 {foam_delete_count + rack_delete_count} 条记录'
        ))
        
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                '\n如需实际删除，请运行: python manage.py cleanup_vision_tasks'
            ))

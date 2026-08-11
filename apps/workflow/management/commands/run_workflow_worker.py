"""持续推进可运行的流程实例。"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.core.constants import TERMINAL_STATES, WorkflowState
from apps.workflow.models import WorkflowInstance
from apps.workflow.services import WorkflowService


class Command(BaseCommand):
    help = '扫描未锁定流程并按状态机推进；生产运行时持续执行'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=float, default=1.0, help='扫描间隔秒数（默认 1）')
        parser.add_argument('--batch-size', type=int, default=50, help='每轮最多推进的流程数')
        parser.add_argument('--once', action='store_true', help='仅扫描一次后退出')

    def handle(self, *args, **options):
        interval = options['interval']
        batch_size = options['batch_size']
        if interval <= 0:
            raise CommandError('--interval 必须大于 0')
        if batch_size <= 0:
            raise CommandError('--batch-size 必须大于 0')

        service = WorkflowService()
        self.stdout.write(self.style.SUCCESS(f'流程 Worker 已启动，间隔 {interval:g} 秒'))
        try:
            while True:
                workflows = list(
                    WorkflowInstance.objects
                    .filter(is_locked=False)
                    .exclude(current_state__in=[*TERMINAL_STATES, WorkflowState.LOCKED])
                    .select_related('product')
                    .order_by('updated_at')[:batch_size]
                )
                advanced = 0
                for workflow in workflows:
                    try:
                        service.advance(workflow)
                        advanced += 1
                    except Exception as exc:  # 单条失败不应阻断其他流程
                        self.stderr.write(self.style.ERROR(
                            f'流程 #{workflow.pk} 推进失败：{exc}'
                        ))
                self.stdout.write(f'本轮扫描 {len(workflows)} 条，成功推进 {advanced} 条')

                if options['once']:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('流程 Worker 已停止'))

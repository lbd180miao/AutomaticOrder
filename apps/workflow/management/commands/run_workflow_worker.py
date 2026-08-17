"""Poll DB100 and run the persisted station handshake state machine."""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.workflow.station_service import StationWorkflowService


class Command(BaseCommand):
    help = '轮询 PLC DB100，并按触发/确认握手推进装箱工位流程'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=float, default=1.0, help='扫描间隔秒数（默认 1）')
        parser.add_argument('--once', action='store_true', help='仅扫描一次后退出')

    def handle(self, *args, **options):
        interval = options['interval']
        if interval <= 0:
            raise CommandError('--interval 必须大于 0')

        service = StationWorkflowService()
        self.stdout.write(self.style.SUCCESS(f'DB100 工位 Worker 已启动，间隔 {interval:g} 秒'))
        try:
            while True:
                try:
                    cycle, changed = service.poll_once()
                    self.stdout.write(
                        f'工位周期 #{cycle.pk} · {cycle.get_phase_display()}'
                        f' · {"已处理信号" if changed else "等待触发"}'
                    )
                except Exception as exc:
                    service.devices.mark_offline(service.plc_device_code)
                    self.stderr.write(self.style.ERROR(f'PLC DB100 轮询失败：{exc}'))
                    if options['once']:
                        raise CommandError(str(exc)) from exc

                if options['once']:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('流程 Worker 已停止'))

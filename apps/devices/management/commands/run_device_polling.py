"""持续轮询设备在线状态。"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.devices.models import Device
from apps.devices.services import DeviceService


class Command(BaseCommand):
    help = '轮询启用设备并刷新在线状态；生产运行时持续执行'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=float, default=5.0, help='轮询间隔秒数（默认 5）')
        parser.add_argument('--once', action='store_true', help='仅轮询一次后退出')

    def handle(self, *args, **options):
        interval = options['interval']
        if interval <= 0:
            raise CommandError('--interval 必须大于 0')

        service = DeviceService()
        self.stdout.write(self.style.SUCCESS(f'设备轮询已启动，间隔 {interval:g} 秒'))
        try:
            while True:
                try:
                    service.refresh_all_status()
                    enabled_count = Device.objects.filter(enabled=True).count()
                    self.stdout.write(f'设备状态已刷新：{enabled_count} 台启用设备')
                except Exception as exc:  # 守护进程需保留下一轮机会
                    self.stderr.write(self.style.ERROR(f'设备轮询失败：{exc}'))
                    if options['once']:
                        raise CommandError(str(exc)) from exc

                if options['once']:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('设备轮询已停止'))

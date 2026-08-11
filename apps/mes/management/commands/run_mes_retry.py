"""批量补传当前失败的 MES 记录。"""
from django.core.management.base import BaseCommand, CommandError

from apps.mes.services import MesService


class Command(BaseCommand):
    help = '按时间顺序补传失败 MES 记录；每次命令仅处理一个快照批次'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='单次最多补传条数（默认 100）')

    def handle(self, *args, **options):
        limit = options['limit']
        if limit <= 0:
            raise CommandError('--limit 必须大于 0')

        service = MesService()
        # 先固定 ID 快照；相同业务请求已有后续成功记录时不再重复补传。
        record_ids = [record.pk for record in service.pending_retry_records(limit=limit)]
        succeeded = 0
        failed = 0
        for record_id in record_ids:
            result = service.retry_record(record_id)
            if result.get('success'):
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(f'MES 记录 #{record_id} 补传成功'))
            else:
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f'MES 记录 #{record_id} 补传失败：{result.get("error", "未知错误")}'
                ))

        self.stdout.write(
            f'MES 补传完成：扫描 {len(record_ids)} 条，成功 {succeeded} 条，失败 {failed} 条'
        )

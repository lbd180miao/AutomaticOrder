"""报警闭环服务。

报警来源包括设备通讯、扫码、MES、视觉检测、流程超时和配置校验失败。
本服务负责创建、确认、关闭报警，并处理工位锁定/解除。
"""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.constants import AlarmLevel, AlarmSource, AlarmStatus
from .models import Alarm, AlarmAction


class AlarmService:
    """Creates, acknowledges, closes, and audits alarms."""

    @staticmethod
    def _generate_code():
        stamp = timezone.now().strftime('%Y%m%d%H%M%S')
        # 当秒内可能重复，追加当日序号保证唯一。
        today_count = Alarm.objects.filter(created_at__date=timezone.localdate()).count() + 1
        return f'ALM{stamp}{today_count:04d}'

    @staticmethod
    def _default_error_code(source, message):
        rules = (
            ('泡棉检测不合格', 'FOAM_INSPECTION_NG'),
            ('配方校验不通过', 'RECIPE_MEASUREMENT_OUT_OF_TOLERANCE'),
            ('POINTCLOUD_ERROR', 'VISION_POINTCLOUD_ERROR'),
            ('定位失败', 'VISION_3D_POSITION_FAILED'),
            ('条码', 'BARCODE_VALIDATION_FAILED'),
            ('MES', 'MES_REQUEST_FAILED'),
            ('通讯', 'DEVICE_COMMUNICATION_FAILED'),
            ('通信', 'DEVICE_COMMUNICATION_FAILED'),
        )
        for marker, code in rules:
            if marker in message:
                return code
        return f'{source}_ERROR'

    @transaction.atomic
    def create(self, *, source, message, level=AlarmLevel.ERROR,
               product=None, rack=None, workflow=None, lock_workstation=False,
               error_code='', scene='', phase='', context=None):
        """创建或合并活动报警；critical 或显式要求时锁定工位。"""
        if level not in AlarmLevel.values:
            level = AlarmLevel.ERROR
        if source not in AlarmSource.values:
            source = AlarmSource.WORKFLOW

        locked = lock_workstation or level == AlarmLevel.CRITICAL
        error_code = error_code or self._default_error_code(source, message)
        now = timezone.now()
        existing = (
            Alarm.objects.select_for_update()
            .exclude(status=AlarmStatus.CLOSED)
            .filter(
                source=source, error_code=error_code, message=message,
                product=product, rack=rack, workflow=workflow,
            )
            .order_by('-created_at')
            .first()
        )
        if existing is not None:
            Alarm.objects.filter(pk=existing.pk).update(
                occurrence_count=F('occurrence_count') + 1,
                last_occurred_at=now,
                locked_workstation=existing.locked_workstation or locked,
                scene=scene or existing.scene,
                phase=phase or existing.phase,
                context=context or existing.context,
                updated_at=now,
            )
            existing.refresh_from_db()
            return existing

        alarm = Alarm.objects.create(
            alarm_code=self._generate_code(),
            level=level,
            source=source,
            message=message,
            product=product,
            rack=rack,
            workflow=workflow,
            status=AlarmStatus.OPEN,
            locked_workstation=locked,
            error_code=error_code,
            scene=scene,
            phase=phase,
            context=context or {},
            last_occurred_at=now,
        )
        return alarm

    @transaction.atomic
    def acknowledge(self, alarm_id, operator_note='', operator=''):
        alarm = Alarm.objects.select_for_update().get(pk=alarm_id)
        if alarm.status == AlarmStatus.CLOSED:
            return alarm
        alarm.status = AlarmStatus.ACKNOWLEDGED
        alarm.acknowledged_at = timezone.now()
        if operator_note:
            alarm.operator_note = operator_note
        alarm.save(update_fields=['status', 'acknowledged_at', 'operator_note', 'updated_at'])
        AlarmAction.objects.create(
            alarm=alarm, action=AlarmAction.Action.ACKNOWLEDGE,
            operator=operator, note=operator_note,
        )
        return alarm

    @transaction.atomic
    def close(self, alarm_id, operator_note='', operator=''):
        """关闭报警并解除其工位锁定。"""
        alarm = Alarm.objects.select_for_update().get(pk=alarm_id)
        alarm.status = AlarmStatus.CLOSED
        alarm.closed_at = timezone.now()
        if alarm.acknowledged_at is None:
            alarm.acknowledged_at = timezone.now()
        if operator_note:
            alarm.operator_note = (
                f'{alarm.operator_note}\n{operator_note}'.strip()
                if alarm.operator_note else operator_note
            )
        alarm.locked_workstation = False
        alarm.save(update_fields=[
            'status', 'closed_at', 'acknowledged_at', 'operator_note',
            'locked_workstation', 'updated_at',
        ])
        AlarmAction.objects.create(
            alarm=alarm, action=AlarmAction.Action.CLOSE,
            operator=operator, note=operator_note,
        )
        return alarm

    def open_alarms(self):
        return Alarm.objects.exclude(status=AlarmStatus.CLOSED).order_by('-created_at')

    def has_active_lock(self, workflow=None):
        """是否存在未关闭且锁定工位的报警。"""
        qs = Alarm.objects.filter(locked_workstation=True).exclude(status=AlarmStatus.CLOSED)
        if workflow is not None:
            qs = qs.filter(workflow=workflow)
        return qs.exists()

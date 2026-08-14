"""为所有页面提供顶部状态栏所需的轻量只读数据。"""
from datetime import timedelta

from django.utils import timezone

from apps.core.constants import AlarmStatus, DeviceStatus, DeviceType


def system_status(request):
    from apps.alarms.models import Alarm
    from apps.devices.models import Device
    from apps.mes.models import MesRecord

    now = timezone.now()
    plc = Device.objects.filter(
        device_type=DeviceType.PLC,
        enabled=True,
    ).order_by('code').first()

    plc_recent = bool(
        plc
        and plc.status == DeviceStatus.ONLINE
        and plc.last_seen_at
        and now - plc.last_seen_at <= timedelta(seconds=10)
    )
    if not plc:
        plc_label = 'PLC 未配置'
        plc_tone = 'muted'
    elif plc_recent:
        plc_label = 'PLC 正常'
        plc_tone = 'ok'
    else:
        plc_label = 'PLC 离线'
        plc_tone = 'fail'

    latest_mes = MesRecord.objects.order_by('-created_at').first()
    if latest_mes and now - latest_mes.created_at <= timedelta(minutes=10):
        mes_label = 'MES 正常' if latest_mes.success else 'MES 异常'
        mes_tone = 'ok' if latest_mes.success else 'fail'
    else:
        mes_label = 'MES 待机'
        mes_tone = 'muted'

    return {
        'nav_plc_label': plc_label,
        'nav_plc_tone': plc_tone,
        'nav_mes_label': mes_label,
        'nav_mes_tone': mes_tone,
        'nav_alarm_count': Alarm.objects.exclude(status=AlarmStatus.CLOSED).count(),
    }

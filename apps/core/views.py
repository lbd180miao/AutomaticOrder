from django.conf import settings
from django.shortcuts import render

from apps.core.constants import DeviceType
from apps.devices.models import Device

from .services import DashboardService


def dashboard(request):
    context = DashboardService().get_summary()
    return render(request, 'dashboard.html', context)


def system_settings(request):
    """系统设置入口：集中收纳 PLC、外围设备和 MES 配置。"""
    config = getattr(settings, 'AUTOMATIC_ORDER', {})
    plc = Device.objects.filter(device_type=DeviceType.PLC).order_by('code').first()
    return render(request, 'system_settings.html', {
        'plc': plc,
        'devices': Device.objects.order_by('device_type', 'code'),
        'mes_base_url': config.get('MES_BASE_URL') or '尚未配置',
        'simulated_mode': config.get('USE_SIMULATED_DEVICES', False),
    })

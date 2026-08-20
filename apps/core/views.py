from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.constants import DeviceType
from apps.devices.models import Device


def dashboard(request):
    """总览页面已移除，访问根路径直接跳转至设备工位主流程页面。"""
    return redirect('devices:status')


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

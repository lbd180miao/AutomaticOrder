"""设备服务：解析设备适配器、记录信号、维护设备在线状态。"""
from django.conf import settings
from django.utils import timezone

from apps.core.constants import DeviceStatus, DeviceType, SignalDirection
from .adapters.camera import CameraAdapter
from .adapters.simulated import SimulatedDeviceAdapter
from .models import Device, DeviceSignalRecord


def get_device_adapter(**kwargs):
    """按配置返回设备适配器。"""
    conf = getattr(settings, 'AUTOMATIC_ORDER', {})
    device_type = kwargs.pop('device_type', None)
    if conf.get('USE_SIMULATED_DEVICES', True):
        return SimulatedDeviceAdapter(**kwargs)
    if device_type in (DeviceType.DEPTH_CAMERA, DeviceType.INSPECT_CAMERA):
        return CameraAdapter()
    # 其他真实设备适配器（PLC/Scanner...）后续按设备类型接入。
    return SimulatedDeviceAdapter(**kwargs)


class DeviceService:
    """Entry point for resolving and invoking device adapters."""

    def __init__(self, adapter=None):
        self.adapter = adapter or get_device_adapter()

    def record_signal(self, device_code, signal_name, signal_value,
                      direction=SignalDirection.IN, raw_payload=None):
        """记录一条设备信号，同时刷新设备在线时间。"""
        device = Device.objects.filter(code=device_code).first()
        record = DeviceSignalRecord.objects.create(
            device=device,
            signal_name=signal_name,
            signal_value=str(signal_value),
            direction=direction,
            raw_payload=raw_payload or {},
            recorded_at=timezone.now(),
        ) if device else None
        if device:
            device.last_seen_at = timezone.now()
            if device.status != DeviceStatus.DISABLED:
                device.status = DeviceStatus.ONLINE
            device.save(update_fields=['last_seen_at', 'status', 'updated_at'])
        return record

    def mark_offline(self, device_code):
        device = Device.objects.filter(code=device_code).first()
        if device:
            device.status = DeviceStatus.OFFLINE
            device.save(update_fields=['status', 'updated_at'])
        return device

    def refresh_all_status(self):
        """模拟轮询：将启用设备标记为在线。"""
        now = timezone.now()
        for device in Device.objects.filter(enabled=True):
            online = self.adapter.is_online()
            device.status = DeviceStatus.ONLINE if online else DeviceStatus.OFFLINE
            device.last_seen_at = now if online else device.last_seen_at
            device.save(update_fields=['status', 'last_seen_at', 'updated_at'])

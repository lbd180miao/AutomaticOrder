"""设备服务：解析设备适配器、记录信号、维护设备在线状态。"""
from django.conf import settings
from django.utils import timezone

from apps.core.constants import DeviceStatus, DeviceType, SignalDirection
from .adapters.camera import CameraAdapter
from .adapters.plc import PLCAdapter
from .models import Device, DeviceSignalRecord


def get_device_adapter(**kwargs):
    """只返回真实设备适配器，不在配置缺失时生成模拟结果。"""
    device_type = kwargs.pop('device_type', None)
    if device_type in (None, DeviceType.PLC):
        return get_plc_adapter()
    if device_type in (DeviceType.DEPTH_CAMERA, DeviceType.INSPECT_CAMERA):
        return CameraAdapter()
    raise RuntimeError(f'未配置真实设备适配器：{device_type}')


def get_plc_adapter():
    """根据设备配置返回真实 S7 PLC 适配器。"""
    device = Device.objects.filter(
        device_type=DeviceType.PLC, enabled=True,
    ).order_by('code').first()
    if device is None:
        raise RuntimeError('未配置启用的 PLC 设备')
    if not device.address:
        raise RuntimeError('PLC IP 地址未配置')
    if (device.protocol or 'S7').upper() not in {'S7', 'S7COMM'}:
        raise RuntimeError(f'DB2 Worker 当前仅支持 S7，现配置为 {device.protocol}')
    config = device.configuration or {}
    return PLCAdapter(
        address=device.address,
        rack=config.get('rack', 0),
        slot=config.get('slot', 1),
        tcp_port=config.get('tcp_port', 102),
        heartbeat_interval=config.get('heartbeat_interval', 1),
    )


class DeviceService:
    """Entry point for resolving and invoking device adapters."""

    def __init__(self, adapter=None):
        self._adapter = adapter

    @property
    def adapter(self):
        if self._adapter is None:
            self._adapter = get_device_adapter()
        return self._adapter

    @adapter.setter
    def adapter(self, value):
        self._adapter = value

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

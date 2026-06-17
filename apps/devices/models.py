from django.db import models

from apps.core.constants import DeviceStatus, DeviceType, SignalDirection
from apps.core.models import TimeStampedModel


class Device(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    device_type = models.CharField(max_length=64, choices=DeviceType.choices)
    protocol = models.CharField(max_length=64, blank=True)
    address = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=DeviceStatus.choices, default=DeviceStatus.UNKNOWN)

    def __str__(self):
        return self.code


class DeviceSignalRecord(TimeStampedModel):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='signals')
    signal_name = models.CharField(max_length=128)
    signal_value = models.CharField(max_length=255)
    direction = models.CharField(max_length=16, choices=SignalDirection.choices, default=SignalDirection.IN)
    raw_payload = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)

from django.shortcuts import render

from .models import Device, DeviceSignalRecord


def status(request):
    devices = Device.objects.order_by('device_type', 'code')
    return render(request, 'devices/status.html', {'devices': devices})


def signals(request):
    records = (
        DeviceSignalRecord.objects.select_related('device').order_by('-recorded_at')[:200]
    )
    return render(request, 'devices/signals.html', {'records': records})

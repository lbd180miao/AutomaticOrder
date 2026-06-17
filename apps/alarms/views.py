from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.constants import AlarmStatus
from .models import Alarm
from .services import AlarmService


def alarm_list(request):
    open_alarms = (
        Alarm.objects.exclude(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack', 'workflow').order_by('-created_at')
    )
    closed_alarms = (
        Alarm.objects.filter(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack').order_by('-closed_at')[:50]
    )
    return render(request, 'alarms/alarm_list.html', {
        'open_alarms': open_alarms,
        'closed_alarms': closed_alarms,
    })


@require_POST
def acknowledge(request, pk):
    get_object_or_404(Alarm, pk=pk)
    AlarmService().acknowledge(pk, operator_note=request.POST.get('operator_note', ''))
    messages.success(request, '报警已确认')
    return redirect(reverse('alarms:alarm_list'))


@require_POST
def close(request, pk):
    get_object_or_404(Alarm, pk=pk)
    AlarmService().close(pk, operator_note=request.POST.get('operator_note', ''))
    messages.success(request, '报警已关闭，工位锁定已解除')
    return redirect(reverse('alarms:alarm_list'))

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.alarms.services import AlarmService
from apps.core.constants import WorkflowState
from apps.core.exceptions import AutomaticOrderError
from .models import WorkflowEvent, WorkflowInstance
from .services import WorkflowService

def current(request):
    """兼容旧入口；实时流程监控已合并到设备页面。"""
    return redirect(reverse('devices:status'))


def history(request):
    instances = (
        WorkflowInstance.objects
        .select_related('product')
        .order_by('-updated_at')[:50]
    )
    events = (
        WorkflowEvent.objects
        .select_related('workflow', 'workflow__product')
        .order_by('-created_at')[:100]
    )
    return render(request, 'workflow/history.html', {
        'instances': instances,
        'events': events,
    })


@require_POST
def start(request):
    """创建一个新的演示流程实例。"""
    from apps.production.models import ProductionBatch

    code = request.POST.get('product_code', '').strip()
    if not code:
        # 自动生成一个演示条码。
        count = WorkflowInstance.objects.count() + 1
        code = f'P-DEMO-{count:04d}'
    batch = ProductionBatch.objects.filter(batch_no='BATCH-DEMO-001').first()
    workflow = WorkflowService().start(code, batch=batch)
    messages.success(request, f'已创建流程：{code}')
    return redirect(reverse('devices:status'))


@require_POST
def advance(request, pk):
    workflow = get_object_or_404(WorkflowInstance, pk=pk)
    try:
        WorkflowService().advance(workflow)
        messages.success(request, f'流程已推进至：{WorkflowState(workflow.current_state).label}')
    except AutomaticOrderError as exc:
        messages.error(request, str(exc))
    return redirect(reverse('devices:status'))


@require_POST
def unlock(request, pk):
    workflow = get_object_or_404(WorkflowInstance, pk=pk)
    resume = request.POST.get('action') != 'fail'
    note = request.POST.get('operator_note', '')
    try:
        try:
            station_cycle = workflow.station_cycle
        except Exception:
            station_cycle = None
        if station_cycle is not None and station_cycle.is_locked and resume:
            from apps.alarms.models import Alarm
            from apps.core.constants import AlarmStatus
            from .station_service import StationWorkflowService
            StationWorkflowService().unlock(station_cycle, operator_note=note)
            alarm_service = AlarmService()
            for alarm in Alarm.objects.filter(
                workflow=workflow, locked_workstation=True,
            ).exclude(status=AlarmStatus.CLOSED):
                alarm_service.close(alarm.pk, operator_note=note or '人工解除')
        else:
            WorkflowService().unlock(workflow, resume=resume, operator_note=note)
        messages.success(request, '已解除锁定' if resume else '已判定流程失败')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect(reverse('devices:status'))

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.constants import AlarmStatus
from .models import Alarm
from .services import AlarmService


def alarm_list(request):
    open_alarms = list(
        Alarm.objects.exclude(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack', 'workflow').order_by('-created_at')
    )
    guidance = {
        'DEVICE': ('通信中断或心跳超时', '自动流程暂停，禁止继续握手', '检查网线、电源与 PLC RUN 状态，恢复通信后再关闭报警。'),
        'SCANNER': ('条码缺失、重复或格式不符', '产品身份无法确认', '清洁扫码窗口并重新扫码；核对实物条码后再确认。'),
        'MES': ('接口超时或业务拒绝', '配方/绑定/装箱结果未确认', '先查看 MES 接口记录与返回信息，成功重传后再关闭。'),
        'VISION': ('图像质量不足或检测不合格', '定位或泡棉工序不可放行', '检查相机、光源和工件状态，复检合格后再关闭。'),
        'RECIPE': ('实测层高或层距超出容差', '工位锁定，不可装箱', '核对料框型号与 MES 配方，排除错框后重新测量。'),
        'WORKFLOW': ('PLC 握手未在规定时间完成', '当前循环停止', '在流程页定位停留点，检查对应 DB100 触发与复位。'),
        'OPERATOR': ('人工创建的生产异常', '按报警内容确定影响', '按现场作业指导书处理并填写处理备注。'),
    }
    for alarm in open_alarms:
        alarm.cause_hint, alarm.impact_hint, alarm.sop_hint = guidance.get(
            alarm.source, ('原因待确认', '当前工位可能受影响', '查看报警详情并按现场 SOP 排查。')
        )
    closed_alarms = (
        Alarm.objects.filter(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack').order_by('-closed_at')[:50]
    )
    return render(request, 'alarms/alarm_list.html', {
        'open_alarms': open_alarms,
        'closed_alarms': closed_alarms,
    })


def alarm_detail(request, pk):
    alarm = get_object_or_404(
        Alarm.objects.select_related('product', 'rack', 'workflow', 'workflow__product'),
        pk=pk,
    )
    return render(request, 'alarms/alarm_detail.html', {'alarm': alarm})


def _action_redirect(request, pk):
    if request.POST.get('return_to') == 'detail':
        return redirect(reverse('alarms:alarm_detail', args=[pk]))
    return redirect(reverse('alarms:alarm_list'))


@require_POST
def acknowledge(request, pk):
    get_object_or_404(Alarm, pk=pk)
    AlarmService().acknowledge(pk, operator_note=request.POST.get('operator_note', ''))
    messages.success(request, '报警已确认')
    return _action_redirect(request, pk)


@require_POST
def close(request, pk):
    alarm = get_object_or_404(Alarm.objects.select_related('workflow'), pk=pk)
    note = request.POST.get('operator_note', '')
    cycle = None
    if alarm.workflow_id:
        try:
            cycle = alarm.workflow.station_cycle
        except Exception:  # no station cycle for legacy workflow alarms
            cycle = None
    elif alarm.locked_workstation:
        from apps.workflow.models import StationCycle, StationPhase
        cycle = StationCycle.objects.filter(
            phase=StationPhase.LOCKED, is_locked=True,
        ).order_by('-created_at').first()
    if cycle is not None and cycle.is_locked:
        try:
            from apps.workflow.station_service import StationWorkflowService
            StationWorkflowService().unlock(cycle, operator_note=note)
        except Exception as exc:
            messages.error(request, f'PLC 工位解锁失败，报警未关闭：{exc}')
            return _action_redirect(request, pk)
    AlarmService().close(pk, operator_note=note)
    messages.success(request, '报警已关闭，工位锁定已解除')
    return _action_redirect(request, pk)

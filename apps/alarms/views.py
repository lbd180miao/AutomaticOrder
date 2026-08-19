from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.constants import AlarmStatus, DeviceStatus, DeviceType
from .models import Alarm
from .services import AlarmService


GUIDANCE = {
    'DEVICE': {
        'cause': 'PLC、相机或网络链路通信异常',
        'impact': '自动握手暂停，当前工序不可继续',
        'steps': ['检查设备电源、网线和急停状态', '确认 PLC 处于 RUN 且心跳恢复', '重新执行失败的握手步骤'],
        'recovery': '设备在线且 PLC 心跳恢复后，才允许解除锁定。',
    },
    'SCANNER': {
        'cause': '条码缺失、重复、格式错误或已有流程占用',
        'impact': '产品身份无法确认，禁止绑定和装箱',
        'steps': ['核对实物条码与当前料框', '清洁扫码窗口并重新扫码', '确认不存在重复或未结束流程'],
        'recovery': '条码重新校验通过并完成本地暂存后方可恢复。',
    },
    'MES': {
        'cause': 'MES 接口超时、业务拒绝或返回数据不完整',
        'impact': '配方、绑定清空或整框上传结果未确认',
        'steps': ['查看 MES 请求号与返回信息', '确认本地数据已经安全保存', '恢复接口后执行重试或补传'],
        'recovery': 'MES 返回成功，或已进入可追踪的待补传队列。',
    },
    'VISION': {
        'cause': '图像质量不足、ROI/点云异常或检测结果不合格',
        'impact': '定位或泡棉工序不可放行',
        'steps': ['检查相机、光源和工件姿态', '核对 ROI、点云或缺陷结果', '重新触发检测并确认结果合格'],
        'recovery': '复检合格且结果已正确写回 PLC。',
    },
    'RECIPE': {
        'cause': '料框型号、层高或层距与 MES 配方不一致',
        'impact': '可装箱信号保持为 0，工位锁定',
        'steps': ['核对料框码、型号与 MES 配方', '检查层高、层距实测值和容差', '排除错框后重新测量'],
        'recovery': '层高和层距均进入配方容差，boxing_allowed=1。',
    },
    'WORKFLOW': {
        'cause': 'PLC 握手未按顺序复位或流程执行超时',
        'impact': '当前循环停留在失败阶段',
        'steps': ['确认当前场景和失败握手点', '检查对应 DB100 触发/完成位', '复位触发后重新执行当前步骤'],
        'recovery': '触发位已复位，系统能够回到安全重试阶段。',
    },
    'OPERATOR': {
        'cause': '现场人员主动记录的生产异常',
        'impact': '按报警内容和现场 SOP 确认',
        'steps': ['核对报警描述和关联对象', '按现场作业指导书处理', '记录处理结果并确认恢复条件'],
        'recovery': '现场确认异常已排除并留下完整处置记录。',
    },
}

SCENE_BY_PHASE = {
    'WAIT_RACK': '场景一：料框到位',
    'WAIT_RACK_RESET': '场景一：料框到位',
    'WAIT_POSITION': '场景二：料架定位补偿',
    'WAIT_POSITION_RESET': '场景二：料架定位补偿',
    'WAIT_PRODUCT': '产品条码暂存',
    'WAIT_MARK_RESET': '产品条码暂存',
    'WAIT_RECIPE_VERIFY': '配方实测校验',
    'WAIT_RECIPE_RESET': '配方实测校验',
    'WAIT_FOAM': '场景三：泡棉检测',
    'WAIT_FOAM_RESET': '场景三：泡棉检测',
    'WAIT_BOXING': '场景四：装箱完成与上传',
    'WAIT_BOXING_RESET': '场景四：装箱完成与上传',
}


def _operator_name(request):
    if getattr(request.user, 'is_authenticated', False):
        return request.user.get_username()
    return '现场操作员'


def _matching_open_alarms(alarm):
    return Alarm.objects.exclude(status=AlarmStatus.CLOSED).filter(
        source=alarm.source,
        error_code=alarm.error_code,
        message=alarm.message,
        product_id=alarm.product_id,
        rack_id=alarm.rack_id,
        workflow_id=alarm.workflow_id,
    )


def _decorate_alarm(alarm):
    guide = GUIDANCE.get(alarm.source, GUIDANCE['WORKFLOW'])
    alarm.cause_hint = guide['cause']
    alarm.impact_hint = guide['impact']
    alarm.sop_steps = guide['steps']
    alarm.recovery_hint = guide['recovery']
    alarm.scene_label = alarm.scene or SCENE_BY_PHASE.get(alarm.phase, alarm.get_source_display())
    alarm.phase_label = alarm.phase or '—'
    if alarm.phase:
        try:
            from apps.workflow.models import StationPhase
            alarm.phase_label = StationPhase(alarm.phase).label
        except ValueError:
            pass
    return alarm


def _group_alarms(alarms):
    groups = {}
    for alarm in alarms:
        key = (
            alarm.source, alarm.error_code or alarm.message, alarm.message,
            alarm.product_id, alarm.rack_id, alarm.workflow_id,
        )
        group = groups.get(key)
        if group is None:
            groups[key] = {
                'alarm': _decorate_alarm(alarm),
                'count': alarm.occurrence_count,
                'record_count': 1,
                'first_seen': alarm.created_at,
                'last_seen': alarm.last_occurred_at or alarm.created_at,
            }
            continue
        group['count'] += alarm.occurrence_count
        group['record_count'] += 1
        group['first_seen'] = min(group['first_seen'], alarm.created_at)
        group['last_seen'] = max(group['last_seen'], alarm.last_occurred_at or alarm.created_at)

    level_weight = {'CRITICAL': 4, 'ERROR': 3, 'WARNING': 2, 'INFO': 1}
    return sorted(
        groups.values(),
        key=lambda item: (
            bool(item['alarm'].locked_workstation),
            level_weight.get(item['alarm'].level, 0),
            item['last_seen'],
        ),
        reverse=True,
    )


def _station_context(primary_alarm):
    from apps.workflow.models import StationCycle, StationPhase

    cycle = None
    if primary_alarm and primary_alarm.workflow_id:
        try:
            cycle = primary_alarm.workflow.station_cycle
        except StationCycle.DoesNotExist:
            cycle = None
    if cycle is None:
        cycle = (
            StationCycle.objects
            .exclude(phase=StationPhase.COMPLETED)
            .select_related('rack__current_recipe', 'workflow__product')
            .order_by('-created_at')
            .first()
        )
    rack = cycle.rack if cycle and cycle.rack_id else (primary_alarm.rack if primary_alarm else None)
    product = cycle.product if cycle and cycle.workflow_id else (primary_alarm.product if primary_alarm else None)
    phase = cycle.resume_phase if cycle and cycle.phase == StationPhase.LOCKED else (cycle.phase if cycle else '')
    return {
        'cycle': cycle,
        'locked': bool((cycle and cycle.is_locked) or (primary_alarm and primary_alarm.locked_workstation)),
        'phase': phase,
        'phase_label': (
            StationPhase(phase).label if phase in StationPhase.values else '等待新循环'
        ),
        'scene_label': (
            primary_alarm.scene_label if primary_alarm else SCENE_BY_PHASE.get(phase, '工位待命')
        ),
        'rack_code': rack.rack_code if rack else '—',
        'product_code': product.product_code if product else '—',
        'progress': f'{cycle.loaded_quantity} / {cycle.planned_quantity or "—"}' if cycle else '0 / —',
        'delta_z': cycle.position_delta_z if cycle else None,
    }


def _device_states():
    from apps.devices.models import Device
    from apps.mes.models import MesRecord

    now = timezone.now()
    devices = list(Device.objects.filter(enabled=True).order_by('code'))

    def device_state(label, device_type):
        matches = [device for device in devices if device.device_type == device_type]
        online = [
            device for device in matches
            if device.status == DeviceStatus.ONLINE and device.last_seen_at
            and (now - device.last_seen_at).total_seconds() <= 15
        ]
        if not matches:
            return {'label': label, 'value': '未配置', 'css': 'muted'}
        if len(online) == len(matches):
            return {'label': label, 'value': f'在线 {len(online)}/{len(matches)}', 'css': 'ok'}
        return {'label': label, 'value': f'在线 {len(online)}/{len(matches)}', 'css': 'fail'}

    mes = MesRecord.objects.order_by('-created_at').first()
    mes_state = {
        'label': 'MES 接口',
        'value': '最近成功' if mes and mes.success else ('最近失败' if mes else '暂无记录'),
        'css': 'ok' if mes and mes.success else ('fail' if mes else 'muted'),
    }
    return [
        device_state('PLC', DeviceType.PLC),
        mes_state,
        device_state('2D 相机', DeviceType.INSPECT_CAMERA),
        device_state('3D 相机', DeviceType.DEPTH_CAMERA),
    ]


def alarm_list(request):
    open_alarms = list(
        Alarm.objects.exclude(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack', 'workflow').order_by('-created_at')
    )
    groups = _group_alarms(open_alarms)
    primary_group = groups[0] if groups else None
    primary_alarm = primary_group['alarm'] if primary_group else None
    station = _station_context(primary_alarm)
    closed_alarms = (
        Alarm.objects.filter(status=AlarmStatus.CLOSED)
        .select_related('product', 'rack').order_by('-closed_at')[:50]
    )
    return render(request, 'alarms/alarm_list.html', {
        'open_alarms': open_alarms,
        'alarm_groups': groups,
        'primary_group': primary_group,
        'primary_alarm': primary_alarm,
        'station': station,
        'device_states': _device_states(),
        'locked_count': sum(1 for alarm in open_alarms if alarm.locked_workstation),
        'acknowledged_count': sum(1 for alarm in open_alarms if alarm.status == AlarmStatus.ACKNOWLEDGED),
        'closed_alarms': closed_alarms,
    })


def alarm_detail(request, pk):
    alarm = get_object_or_404(
        Alarm.objects.select_related(
            'product', 'rack', 'workflow', 'workflow__product',
        ).prefetch_related('actions'),
        pk=pk,
    )
    _decorate_alarm(alarm)
    return render(request, 'alarms/alarm_detail.html', {'alarm': alarm})


def _action_redirect(request, pk):
    if request.POST.get('return_to') == 'detail':
        return redirect(reverse('alarms:alarm_detail', args=[pk]))
    return redirect(reverse('alarms:alarm_list'))


@require_POST
def acknowledge(request, pk):
    alarm = get_object_or_404(Alarm, pk=pk)
    members = list(_matching_open_alarms(alarm).values_list('pk', flat=True))
    service = AlarmService()
    for alarm_id in members:
        service.acknowledge(
            alarm_id, operator_note=request.POST.get('operator_note', ''),
            operator=_operator_name(request),
        )
    messages.success(request, f'报警已确认，共处理 {len(members)} 条同类记录')
    return _action_redirect(request, pk)


@require_POST
def close(request, pk):
    alarm = get_object_or_404(Alarm.objects.select_related('workflow'), pk=pk)
    note = request.POST.get('operator_note', '').strip()
    members = _matching_open_alarms(alarm)
    if not note:
        messages.error(request, '请填写故障检查结果和恢复依据')
        return _action_redirect(request, pk)
    if members.filter(status=AlarmStatus.OPEN).exists():
        messages.error(request, '请先确认报警，再执行关闭和安全解锁')
        return _action_redirect(request, pk)
    member_ids = list(members.values_list('pk', flat=True))
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
    other_locks = Alarm.objects.filter(locked_workstation=True).exclude(
        status=AlarmStatus.CLOSED,
    ).exclude(pk__in=member_ids)
    if alarm.workflow_id:
        other_locks = other_locks.filter(workflow_id=alarm.workflow_id)
    elif cycle is not None:
        other_locks = other_locks.filter(Q(workflow__station_cycle=cycle) | Q(workflow__isnull=True))

    can_unlock = not other_locks.exists()
    if cycle is not None and cycle.is_locked and can_unlock:
        try:
            from apps.workflow.station_service import StationWorkflowService
            StationWorkflowService().unlock(cycle, operator_note=note)
        except Exception as exc:
            messages.error(request, f'PLC 工位解锁失败，报警未关闭：{exc}')
            return _action_redirect(request, pk)
    service = AlarmService()
    for alarm_id in member_ids:
        service.close(alarm_id, operator_note=note, operator=_operator_name(request))
    if can_unlock:
        messages.success(request, f'故障已关闭，共处理 {len(member_ids)} 条同类记录；安全锁定已解除')
    else:
        messages.warning(request, f'本组报警已关闭，但仍有 {other_locks.count()} 个锁定故障，工位保持锁定')
    return _action_redirect(request, pk)

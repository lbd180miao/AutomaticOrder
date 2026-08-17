from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.alarms.services import AlarmService
from apps.core.constants import STATE_STAGE_MAP, Stage, TERMINAL_STATES, WorkflowState
from apps.core.exceptions import AutomaticOrderError
from .models import StationCycle, StationPhase, WorkflowEvent, WorkflowInstance
from .services import WorkflowService

STAGE_ONE_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_ONE]
STAGE_TWO_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_TWO]
STAGE_THREE_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_THREE]

# 主流程状态的线性顺序，用于判断某状态是否已走过。
ORDERED_STATES = STAGE_ONE_STATES + STAGE_TWO_STATES + STAGE_THREE_STATES + [WorkflowState.COMPLETED]

HANDSHAKE_DEFINITIONS = [
    ('产品条码', 'DBX24.0', 'DBB2', 'DBX25.0', {StationPhase.WAIT_PRODUCT, StationPhase.WAIT_MARK_RESET}),
    ('料框与配方', 'DBX48.0', 'DBB26', 'DBX49.0', {StationPhase.WAIT_RACK, StationPhase.WAIT_RACK_RESET}),
    ('3D 定位', 'DBX118.0', 'DBB54–117', 'DBX119.0', {StationPhase.WAIT_POSITION, StationPhase.WAIT_POSITION_RESET}),
    ('配方核对', 'DBX50.0', 'DBX51.0', 'DBX52.0', {StationPhase.WAIT_RECIPE_VERIFY, StationPhase.WAIT_RECIPE_RESET}),
    ('泡棉检测', 'DBX120.0', 'DBX121.0', 'DBX122.0', {StationPhase.WAIT_FOAM, StationPhase.WAIT_FOAM_RESET}),
    ('装箱上传', 'DBX123.0', 'DBX124.0', 'DBX125.0', {StationPhase.WAIT_BOXING, StationPhase.WAIT_BOXING_RESET}),
]


def _handshake_cards(cycle, demo_mode=False):
    phase = cycle.phase if cycle else None
    active_index = next(
        (index for index, definition in enumerate(HANDSHAKE_DEFINITIONS) if phase in definition[4]),
        4 if demo_mode else 0,
    )
    completed = phase == StationPhase.COMPLETED
    cards = []
    for index, (name, trigger, result, confirm, _phases) in enumerate(HANDSHAKE_DEFINITIONS):
        status = 'done' if completed or index < active_index else ('active' if index == active_index else 'pending')
        cards.append({
            'number': index + 1, 'name': name, 'trigger': trigger,
            'result': result, 'confirm': confirm, 'status': status,
            'trigger_value': 1 if status == 'done' else 0,
            'confirm_value': 1 if status == 'done' else 0,
        })
    return cards


def _build_stage_view(states, current_state):
    """把状态列表转成带 label / done / active 标记的步骤列表。"""
    try:
        current_index = ORDERED_STATES.index(current_state)
    except ValueError:
        current_index = -1
    steps = []
    for st in states:
        idx = ORDERED_STATES.index(st) if st in ORDERED_STATES else -1
        steps.append({
            'code': st,
            'label': WorkflowState(st).label,
            'done': idx != -1 and current_index != -1 and idx < current_index,
            'active': st == current_state,
        })
    return steps


def current(request):
    station_cycle = (
        StationCycle.objects.exclude(phase=StationPhase.COMPLETED)
        .select_related('workflow__product__rack__current_recipe')
        .order_by('-created_at').first()
    )
    workflow = (
        WorkflowInstance.objects
        .exclude(current_state__in=list(TERMINAL_STATES))
        .select_related('product', 'product__rack')
        .order_by('-updated_at')
        .first()
    ) if station_cycle is None else station_cycle.workflow
    recent_events = []
    stage_order = []
    if workflow:
        recent_events = WorkflowEvent.objects.filter(workflow=workflow).order_by('-created_at')[:15]
        cur = workflow.current_state
        stage_order = [
            ('阶段一 注塑下线与打标', _build_stage_view(STAGE_ONE_STATES, cur)),
            ('阶段二 空中交接', _build_stage_view(STAGE_TWO_STATES, cur)),
            ('阶段三 视觉装箱与泡棉', _build_stage_view(STAGE_THREE_STATES, cur)),
        ]

    demo_mode = station_cycle is None and (workflow is None or workflow.product.product_code.startswith('P-DEMO'))
    display_product = workflow.product.product_code if workflow else ('P-20260815-0042' if demo_mode else '')
    display_rack = workflow.product.rack.rack_code if workflow and workflow.product.rack_id else ('RACK-A-0815-02' if demo_mode else '')
    display_recipe = (
        workflow.product.rack.current_recipe.recipe_code
        if workflow and workflow.product.rack_id and workflow.product.rack.current_recipe_id
        else ('BUMPER-A-04' if demo_mode else '')
    )
    display_phase = station_cycle.get_phase_display() if station_cycle else ('等待泡棉检测触发' if demo_mode else state_label if workflow else '等待生产任务')
    context = {
        'workflow': workflow,
        'recent_events': recent_events,
        'state_label': WorkflowState(workflow.current_state).label if workflow else '',
        'is_terminal': workflow.current_state in TERMINAL_STATES if workflow else False,
        'stage_order': stage_order,
        'station_cycle': station_cycle,
        'demo_mode': demo_mode,
        'handshakes': _handshake_cards(station_cycle, demo_mode=demo_mode),
        'display_product': display_product,
        'display_rack': display_rack,
        'display_recipe': display_recipe,
        'display_phase': display_phase,
    }
    return render(request, 'workflow/current.html', context)


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
    return redirect(reverse('workflow:current'))


@require_POST
def advance(request, pk):
    workflow = get_object_or_404(WorkflowInstance, pk=pk)
    try:
        WorkflowService().advance(workflow)
        messages.success(request, f'流程已推进至：{WorkflowState(workflow.current_state).label}')
    except AutomaticOrderError as exc:
        messages.error(request, str(exc))
    return redirect(reverse('workflow:current'))


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
    return redirect(reverse('workflow:current'))

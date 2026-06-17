from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.constants import STATE_STAGE_MAP, Stage, TERMINAL_STATES, WorkflowState
from apps.core.exceptions import AutomaticOrderError
from .models import WorkflowEvent, WorkflowInstance
from .services import WorkflowService

STAGE_ONE_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_ONE]
STAGE_TWO_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_TWO]
STAGE_THREE_STATES = [s for s, st in STATE_STAGE_MAP.items() if st == Stage.STAGE_THREE]

# 主流程状态的线性顺序，用于判断某状态是否已走过。
ORDERED_STATES = STAGE_ONE_STATES + STAGE_TWO_STATES + STAGE_THREE_STATES + [WorkflowState.COMPLETED]


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
    workflow = (
        WorkflowInstance.objects
        .exclude(current_state__in=list(TERMINAL_STATES))
        .select_related('product', 'product__rack')
        .order_by('-updated_at')
        .first()
    )
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

    context = {
        'workflow': workflow,
        'recent_events': recent_events,
        'state_label': WorkflowState(workflow.current_state).label if workflow else '',
        'is_terminal': workflow.current_state in TERMINAL_STATES if workflow else False,
        'stage_order': stage_order,
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
        WorkflowService().unlock(workflow, resume=resume, operator_note=note)
        messages.success(request, '已解除锁定' if resume else '已判定流程失败')
    except AutomaticOrderError as exc:
        messages.error(request, str(exc))
    return redirect(reverse('workflow:current'))

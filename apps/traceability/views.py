from datetime import datetime, time, timedelta

from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.alarms.models import Alarm
from apps.core.constants import AlarmStatus, MesUploadStatus, WorkflowState
from apps.devices.models import DeviceSignalRecord
from apps.mes.models import MesRecord
from apps.production.models import Product, Rack
from apps.vision.models import FoamInspectionResult
from apps.workflow.models import StationCycle

from .services import TraceabilityService


def search(request):
    query = request.GET.get('q', '').strip()
    mode = request.GET.get('mode', 'product')
    state_filter = request.GET.get('state', '').strip()
    mes_filter = request.GET.get('mes_status', '').strip()
    start_date_raw = request.GET.get('start_date', '').strip()
    end_date_raw = request.GET.get('end_date', '').strip()
    start_date = parse_date(start_date_raw) if start_date_raw else None
    end_date = parse_date(end_date_raw) if end_date_raw else None
    date_error = ''

    if start_date_raw and not start_date:
        date_error = '开始日期格式不正确'
    elif end_date_raw and not end_date:
        date_error = '结束日期格式不正确'
    elif start_date and end_date and start_date > end_date:
        date_error = '开始日期不能晚于结束日期'

    current_tz = timezone.get_current_timezone()
    start_at = None
    end_before = None
    if not date_error:
        if start_date:
            start_at = timezone.make_aware(datetime.combine(start_date, time.min), current_tz)
        if end_date:
            end_before = timezone.make_aware(
                datetime.combine(end_date + timedelta(days=1), time.min), current_tz,
            )

    products = Product.objects.select_related(
        'batch', 'rack', 'rack__current_recipe', 'workflowinstance',
    ).order_by('-created_at')
    racks = Rack.objects.select_related('current_recipe').order_by('-updated_at')
    cycles = StationCycle.objects.select_related(
        'workflow__product__rack__current_recipe',
    ).order_by('-created_at')
    foam_results = FoamInspectionResult.objects.select_related('product', 'rack').order_by('-created_at')
    mes_records = MesRecord.objects.select_related('product', 'rack').order_by('-created_at')
    signals = DeviceSignalRecord.objects.select_related('device').order_by('-recorded_at')
    alarms = Alarm.objects.select_related('product', 'rack').order_by('-created_at')

    if start_at:
        products = products.filter(created_at__gte=start_at)
        racks = racks.filter(created_at__gte=start_at)
        cycles = cycles.filter(created_at__gte=start_at)
        foam_results = foam_results.filter(created_at__gte=start_at)
        mes_records = mes_records.filter(created_at__gte=start_at)
        signals = signals.filter(recorded_at__gte=start_at)
        alarms = alarms.filter(created_at__gte=start_at)
    if end_before:
        products = products.filter(created_at__lt=end_before)
        racks = racks.filter(created_at__lt=end_before)
        cycles = cycles.filter(created_at__lt=end_before)
        foam_results = foam_results.filter(created_at__lt=end_before)
        mes_records = mes_records.filter(created_at__lt=end_before)
        signals = signals.filter(recorded_at__lt=end_before)
        alarms = alarms.filter(created_at__lt=end_before)

    if state_filter:
        products = products.filter(current_state=state_filter)
    if mes_filter:
        products = products.filter(mes_upload_status=mes_filter)

    time_filter_active = bool(start_at or end_before)
    result_limit = 100 if time_filter_active else 8
    if start_date and end_date and not date_error:
        record_scope_label = f'{start_date:%Y-%m-%d} 至 {end_date:%Y-%m-%d}'
    elif start_date and not date_error:
        record_scope_label = f'{start_date:%Y-%m-%d} 起'
    elif end_date and not date_error:
        record_scope_label = f'截至 {end_date:%Y-%m-%d}'
    else:
        record_scope_label = '最近 8 条'

    rack_list = list(racks[:result_limit])
    rack_ids = [rack.pk for rack in rack_list]
    rack_products = {rack_id: [] for rack_id in rack_ids}
    for product in Product.objects.filter(rack_id__in=rack_ids).select_related('batch').order_by('created_at'):
        rack_products.setdefault(product.rack_id, []).append(product)

    rack_foam = {rack_id: {'total': 0, 'ok': 0, 'ng': 0} for rack_id in rack_ids}
    for item in FoamInspectionResult.objects.filter(rack_id__in=rack_ids).values('rack_id', 'is_passed'):
        stats = rack_foam.setdefault(item['rack_id'], {'total': 0, 'ok': 0, 'ng': 0})
        stats['total'] += 1
        stats['ok' if item['is_passed'] else 'ng'] += 1

    rack_mes_failures = {rack_id: 0 for rack_id in rack_ids}
    for rack_id in MesRecord.objects.filter(rack_id__in=rack_ids, success=False).values_list('rack_id', flat=True):
        rack_mes_failures[rack_id] = rack_mes_failures.get(rack_id, 0) + 1

    rack_open_alarms = {rack_id: 0 for rack_id in rack_ids}
    for rack_id in Alarm.objects.filter(rack_id__in=rack_ids).exclude(status=AlarmStatus.CLOSED).values_list('rack_id', flat=True):
        rack_open_alarms[rack_id] = rack_open_alarms.get(rack_id, 0) + 1

    latest_cycle_by_rack = {}
    for cycle in StationCycle.objects.filter(
        workflow__product__rack_id__in=rack_ids,
    ).select_related('workflow__product__rack').order_by('-created_at'):
        rack_id = cycle.workflow.product.rack_id
        latest_cycle_by_rack.setdefault(rack_id, cycle)

    rack_tasks = []
    for rack in rack_list:
        recipe = rack.current_recipe
        products_for_rack = rack_products.get(rack.pk, [])
        cycle = latest_cycle_by_rack.get(rack.pk)
        planned = (
            cycle.planned_quantity if cycle and cycle.planned_quantity
            else recipe.total_quantity if recipe else 0
        )
        loaded = cycle.loaded_quantity if cycle else len(products_for_rack)
        gaps = []
        if recipe is None:
            gaps.append('缺少装箱配方')
        if cycle is None:
            gaps.append('未形成工位周期')
        if products_for_rack and cycle is None:
            gaps.append('产品缺少循环关联')
        foam = rack_foam.get(rack.pk, {'total': 0, 'ok': 0, 'ng': 0})
        rack_tasks.append({
            'rack': rack,
            'recipe': recipe,
            'cycle': cycle,
            'planned_quantity': planned,
            'loaded_quantity': loaded,
            'product_count': len(products_for_rack),
            'foam': foam,
            'mes_failures': rack_mes_failures.get(rack.pk, 0),
            'open_alarms': rack_open_alarms.get(rack.pk, 0),
            'gaps': gaps,
        })

    product_list = list(products[:result_limit])
    product_ids = [product.pk for product in product_list]
    product_foam = {product_id: {'total': 0, 'ok': 0, 'ng': 0} for product_id in product_ids}
    for item in FoamInspectionResult.objects.filter(product_id__in=product_ids).values('product_id', 'is_passed'):
        stats = product_foam.setdefault(item['product_id'], {'total': 0, 'ok': 0, 'ng': 0})
        stats['total'] += 1
        stats['ok' if item['is_passed'] else 'ng'] += 1
    latest_mes_by_product = {}
    for item in MesRecord.objects.filter(product_id__in=product_ids).order_by('-created_at'):
        latest_mes_by_product.setdefault(item.product_id, item)
    product_rows = []
    for product in product_list:
        gaps = []
        if product.rack_id is None:
            gaps.append('未绑定料框')
        if not hasattr(product, 'workflowinstance'):
            gaps.append('无流程实例')
        product_rows.append({
            'product': product,
            'foam': product_foam.get(product.pk, {'total': 0, 'ok': 0, 'ng': 0}),
            'latest_mes': latest_mes_by_product.get(product.pk),
            'gaps': gaps,
        })

    unbound_products = list(products.filter(rack__isnull=True)[:result_limit])
    incomplete_count = (
        products.filter(rack__isnull=True).count()
        + racks.filter(current_recipe__isnull=True).count()
        + cycles.filter(workflow__isnull=True).count()
    )
    foam_total = foam_results.count()
    foam_ok = foam_results.filter(is_passed=True).count()

    integrity_issues = []
    for product in unbound_products[:20]:
        integrity_issues.append({
            'level': 'warning',
            'category': '绑定断链',
            'object_code': product.product_code,
            'message': '产品已落库，但尚未关联料框及装箱位置。',
            'time': product.created_at,
            'product': product,
        })
    for rack in rack_list:
        if rack.current_recipe_id is None:
            integrity_issues.append({
                'level': 'error',
                'category': '配方断链',
                'object_code': rack.rack_code,
                'message': '料框没有关联装箱配方，无法证明计划结构。',
                'time': rack.updated_at,
            })
    for item in mes_records.filter(success=False)[:20]:
        integrity_issues.append({
            'level': 'error',
            'category': 'MES失败',
            'object_code': item.product.product_code if item.product else item.rack.rack_code if item.rack else '未关联',
            'message': item.error_message or 'MES 业务交互失败。',
            'time': item.created_at,
        })
    integrity_issues.sort(key=lambda item: item['time'] or timezone.now(), reverse=True)

    context = {
        'query': query,
        'mode': mode,
        'state_filter': state_filter,
        'mes_filter': mes_filter,
        'state_choices': WorkflowState.choices,
        'mes_choices': MesUploadStatus.choices,
        'start_date': start_date_raw,
        'end_date': end_date_raw,
        'date_error': date_error,
        'time_filter_active': time_filter_active,
        'record_scope_label': record_scope_label,
        'result': None,
        'rack_result': None,
        'recent_products': product_list,
        'product_rows': product_rows,
        'rack_tasks': rack_tasks,
        'unbound_products': unbound_products,
        'recent_cycles': cycles[:result_limit],
        'integrity_issues': integrity_issues[:result_limit],
        'recent_mes_records': mes_records[:result_limit],
        'recent_signals': signals[:result_limit],
        'recent_alarms': alarms[:result_limit],
        'record_stats': {
            'total_products': products.count(),
            'rack_tasks': racks.count(),
            'completed_products': products.filter(current_state=WorkflowState.COMPLETED).count(),
            'foam_total': foam_total,
            'foam_ok': foam_ok,
            'foam_ng': max(0, foam_total - foam_ok),
            'mes_total': mes_records.count(),
            'mes_failed': mes_records.filter(success=False).count(),
            'open_alarms': alarms.exclude(status=AlarmStatus.CLOSED).count(),
            'incomplete': incomplete_count,
        },
    }

    if query:
        service = TraceabilityService()
        if mode == 'rack':
            context['rack_result'] = service.trace_by_rack_code(query)
            if context['rack_result'] is None:
                context['not_found'] = True
        else:
            context['result'] = service.trace_by_product_code(query)
            if context['result'] is None:
                context['not_found'] = True
    return render(request, 'traceability/search.html', context)


def product_detail(request, product_code):
    result = TraceabilityService().trace_by_product_code(product_code)
    if result is None:
        raise Http404(f'未找到产品 {product_code}')
    return render(request, 'traceability/product_detail.html', {'result': result})

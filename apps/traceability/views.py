from datetime import datetime, time, timedelta
from collections import OrderedDict

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.constants import MesAction, MesUploadStatus, WorkflowState
from apps.production.models import Product, Rack
from apps.vision.models import FoamInspectionResult, RackLocationResult
from apps.mes.models import MesRecord

from .services import TraceabilityService

PAGE_SIZE = 20
RACK_PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def _parse_date_range(request):
    """从 GET 参数解析 start_date / end_date，返回 (start_at, end_before, error)。"""
    start_raw = request.GET.get('start_date', '').strip()
    end_raw = request.GET.get('end_date', '').strip()
    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None

    if start_raw and not start_date:
        return None, None, '开始日期格式不正确'
    if end_raw and not end_date:
        return None, None, '结束日期格式不正确'
    if start_date and end_date and start_date > end_date:
        return None, None, '开始日期不能晚于结束日期'

    tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.combine(start_date, time.min), tz) if start_date else None
    end_before = (
        timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
        if end_date else None
    )
    return start_at, end_before, ''


def _date_label(start_raw, end_raw, start_date, end_date):
    if start_date and end_date:
        return f'{start_date:%Y-%m-%d} 至 {end_date:%Y-%m-%d}'
    if start_date:
        return f'{start_date:%Y-%m-%d} 起'
    if end_date:
        return f'截至 {end_date:%Y-%m-%d}'
    return '全部历史数据'


# ---------------------------------------------------------------------------
# 模块一：料框检测记录
# ---------------------------------------------------------------------------

def rack_detection(request):
    """料框定位检测记录查询。"""
    q = request.GET.get('q', '').strip()           # 料框码
    success_filter = request.GET.get('success', '') # '' / 'true' / 'false'
    start_raw = request.GET.get('start_date', '').strip()
    end_raw = request.GET.get('end_date', '').strip()
    start_at, end_before, date_error = _parse_date_range(request)
    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None

    qs = (
        RackLocationResult.objects
        .select_related('vision_task', 'rack', 'recipe')
        .order_by('-created_at')
    )

    if q:
        qs = qs.filter(rack__rack_code__icontains=q)
    if not date_error:
        if start_at:
            qs = qs.filter(created_at__gte=start_at)
        if end_before:
            qs = qs.filter(created_at__lt=end_before)
    if success_filter == 'true':
        qs = qs.filter(is_success=True)
    elif success_filter == 'false':
        qs = qs.filter(is_success=False)

    total = qs.count()
    ok_count = qs.filter(is_success=True).count()
    ng_count = qs.filter(is_success=False).count()

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'tab': 'rack',
        'q': q,
        'success_filter': success_filter,
        'start_date': start_raw,
        'end_date': end_raw,
        'date_error': date_error,
        'date_label': _date_label(start_raw, end_raw, start_date, end_date),
        'page_obj': page_obj,
        'stats': {
            'total': total,
            'ok': ok_count,
            'ng': ng_count,
            'rate': f'{ok_count / total * 100:.1f}%' if total else '—',
        },
    }
    return render(request, 'traceability/index.html', context)


# ---------------------------------------------------------------------------
# 模块二：产品与料框绑定记录（一框多件结构化视图）
# ---------------------------------------------------------------------------

def product_binding(request):
    """产品与料框绑定记录查询（以料框为主体聚合多个产品条码）。"""
    q = request.GET.get('q', '').strip()               # 产品条码 / 料框码 / 批次号
    state_filter = request.GET.get('state', '').strip()
    mes_filter = request.GET.get('mes_status', '').strip()
    start_raw = request.GET.get('start_date', '').strip()
    end_raw = request.GET.get('end_date', '').strip()
    start_at, end_before, date_error = _parse_date_range(request)
    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None

    # 1. 基础产品数据集
    prod_qs = Product.objects.select_related('batch', 'rack', 'rack__current_recipe').order_by('created_at')

    if q:
        prod_qs = prod_qs.filter(
            Q(product_code__icontains=q)
            | Q(rack__rack_code__icontains=q)
            | Q(batch__batch_no__icontains=q)
        )

    if not date_error:
        if start_at:
            prod_qs = prod_qs.filter(created_at__gte=start_at)
        if end_before:
            prod_qs = prod_qs.filter(created_at__lt=end_before)
    if state_filter:
        prod_qs = prod_qs.filter(current_state=state_filter)
    if mes_filter:
        prod_qs = prod_qs.filter(mes_upload_status=mes_filter)

    total_prods = prod_qs.count()
    bound_prods_count = prod_qs.filter(rack__isnull=False).count()
    unbound_prods_count = prod_qs.filter(rack__isnull=True).count()
    uploaded_prods_count = prod_qs.filter(mes_upload_status=MesUploadStatus.UPLOADED).count()

    all_products = list(prod_qs)
    product_ids = [p.pk for p in all_products]

    # 批量预加载泡棉检测结果与 MES 上传回执，避免 N+1
    foam_map = {}
    for foam in FoamInspectionResult.objects.filter(product_id__in=product_ids).order_by('-created_at'):
        foam_map.setdefault(foam.product_id, foam)

    mes_map = {}
    for mes in MesRecord.objects.filter(product_id__in=product_ids).order_by('-created_at'):
        mes_map.setdefault(mes.product_id, mes)

    # 2. 按料框分组归纳（一个料框 -> 多个产品条码）
    rack_groups_dict = OrderedDict()
    unbound_products = []

    for p in all_products:
        if not p.rack_id:
            unbound_products.append({
                'product': p,
                'foam': foam_map.get(p.pk),
                'latest_mes': mes_map.get(p.pk),
            })
            continue

        rack_id = p.rack_id
        if rack_id not in rack_groups_dict:
            recipe = p.rack.current_recipe
            total_slots = recipe.total_quantity if recipe and recipe.total_quantity else 0
            rack_groups_dict[rack_id] = {
                'rack': p.rack,
                'recipe': recipe,
                'total_slots': total_slots,
                'products': [],
            }

        recipe = rack_groups_dict[rack_id]['recipe']
        foam = foam_map.get(p.pk)
        pos_idx = foam.position_index if foam and foam.position_index else len(rack_groups_dict[rack_id]['products']) + 1
        
        layer_no = None
        slot_no = None
        if recipe and recipe.quantity_per_layer and recipe.quantity_per_layer > 0:
            layer_no = (pos_idx - 1) // recipe.quantity_per_layer + 1
            slot_no = (pos_idx - 1) % recipe.quantity_per_layer + 1

        rack_groups_dict[rack_id]['products'].append({
            'product': p,
            'position_index': pos_idx,
            'layer_no': layer_no,
            'slot_no': slot_no,
            'foam': foam,
            'latest_mes': mes_map.get(p.pk),
        })

    # 计算各料框的占用率与满载状态
    rack_groups = []
    for g in rack_groups_dict.values():
        occupied = len(g['products'])
        total = g['total_slots']
        percent = min(100, round(occupied / total * 100)) if total > 0 else 100
        g['occupied_count'] = occupied
        g['occupancy_percent'] = percent
        rack_groups.append(g)

    # 3. 分页（按料框分页）
    paginator = Paginator(rack_groups, RACK_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'tab': 'binding',
        'q': q,
        'state_filter': state_filter,
        'mes_filter': mes_filter,
        'start_date': start_raw,
        'end_date': end_raw,
        'date_error': date_error,
        'date_label': _date_label(start_raw, end_raw, start_date, end_date),
        'state_choices': WorkflowState.choices,
        'mes_choices': MesUploadStatus.choices,
        'page_obj': page_obj,
        'rack_groups': page_obj.object_list,
        'unbound_products': unbound_products,
        'stats': {
            'rack_total': len(rack_groups),
            'total': total_prods,
            'bound': bound_prods_count,
            'unbound': unbound_prods_count,
            'uploaded': uploaded_prods_count,
        },
    }
    return render(request, 'traceability/index.html', context)


# ---------------------------------------------------------------------------
# 模块三：泡棉检测记录
# ---------------------------------------------------------------------------

def foam_inspection(request):
    """泡棉检测记录查询。"""
    q = request.GET.get('q', '').strip()             # 产品条码 / 料框码
    passed_filter = request.GET.get('passed', '')    # '' / 'true' / 'false'
    defect_filter = request.GET.get('defect', '').strip()
    start_raw = request.GET.get('start_date', '').strip()
    end_raw = request.GET.get('end_date', '').strip()
    start_at, end_before, date_error = _parse_date_range(request)
    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None

    qs = (
        FoamInspectionResult.objects
        .select_related('product', 'rack', 'vision_task')
        .order_by('-created_at')
    )

    if q:
        qs = qs.filter(
            Q(product__product_code__icontains=q)
            | Q(rack__rack_code__icontains=q)
        )
    if not date_error:
        if start_at:
            qs = qs.filter(created_at__gte=start_at)
        if end_before:
            qs = qs.filter(created_at__lt=end_before)
    if passed_filter == 'true':
        qs = qs.filter(is_passed=True)
    elif passed_filter == 'false':
        qs = qs.filter(is_passed=False)
    if defect_filter:
        qs = qs.filter(defect_type=defect_filter)

    total = qs.count()
    ok_count = qs.filter(is_passed=True).count()
    ng_count = qs.filter(is_passed=False).count()

    # 获取缺陷类型列表（用于筛选下拉）
    defect_choices = (
        FoamInspectionResult.objects
        .exclude(defect_type='NONE')
        .exclude(defect_type='')
        .values_list('defect_type', flat=True)
        .distinct()
        .order_by('defect_type')
    )

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'tab': 'foam',
        'q': q,
        'passed_filter': passed_filter,
        'defect_filter': defect_filter,
        'defect_choices': list(defect_choices),
        'start_date': start_raw,
        'end_date': end_raw,
        'date_error': date_error,
        'date_label': _date_label(start_raw, end_raw, start_date, end_date),
        'page_obj': page_obj,
        'stats': {
            'total': total,
            'ok': ok_count,
            'ng': ng_count,
            'rate': f'{ok_count / total * 100:.1f}%' if total else '—',
        },
    }
    return render(request, 'traceability/index.html', context)


# ---------------------------------------------------------------------------
# 单件产品详情（保留）
# ---------------------------------------------------------------------------

def product_detail(request, product_code):
    result = TraceabilityService().trace_by_product_code(product_code)
    if result is None:
        raise Http404(f'未找到产品 {product_code}')
    return render(request, 'traceability/product_detail.html', {'result': result})

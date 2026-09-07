import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import cv2
import numpy as np
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.constants import MesAction, MesUploadStatus
from apps.production.models import Product, Rack, RackRecipe
from apps.production.services import ProductionService
from apps.workflow.models import StationCycle, StationPhase
from apps.vision.models import FoamInspectionResult
from apps.vision.models import RackMeasurementProfile
from apps.vision.rack_measurement import (
    RackMeasurementError,
    RackMeasurementService,
    profile_parameters,
)
from .models import MesRecord
from .services import MesService


# ─── 页面视图 ─────────────────────────────────────────────────────

def record_list(request):
    """MES 数据工作台：业务查询、补传和接口审计统一入口。"""
    tab = request.GET.get('tab', 'bindings')
    valid_tabs = {'bindings', 'recipes', 'pending', 'consistency', 'records'}
    if tab not in valid_tabs:
        tab = 'bindings'

    keyword = request.GET.get('keyword', '').strip()
    rack_code = request.GET.get('rack_code', '').strip()
    product_code = request.GET.get('product_code', '').strip()
    recipe_code = request.GET.get('recipe_code', '').strip()
    sync_status = request.GET.get('sync_status', '').strip()
    product_status = request.GET.get('product_status', '').strip()
    action_filter = request.GET.get('action', '')
    result_filter = request.GET.get('result', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    record_qs = MesRecord.objects.select_related('product', 'rack').order_by('-created_at')

    if action_filter:
        record_qs = record_qs.filter(action=action_filter)
    if result_filter == 'ok':
        record_qs = record_qs.filter(success=True)
    elif result_filter == 'fail':
        record_qs = record_qs.filter(success=False)

    start_value = parse_date(start_date) if start_date else None
    end_value = parse_date(end_date) if end_date else None
    if start_value:
        record_qs = record_qs.filter(created_at__gte=timezone.make_aware(datetime.combine(start_value, time.min)))
    if end_value:
        exclusive_end = end_value + timedelta(days=1)
        record_qs = record_qs.filter(created_at__lt=timezone.make_aware(datetime.combine(exclusive_end, time.min)))

    records = list(record_qs[:200])
    _decorate_mes_records(records)

    binding_qs = Product.objects.select_related(
        'rack', 'rack__current_recipe', 'batch', 'replaced_by',
    ).order_by('-bound_at', '-pk')

    latest_upload = MesRecord.objects.filter(
        action=MesAction.UPLOAD_PRODUCT_BARCODE,
        product_id=OuterRef('pk'),
    ).order_by('-created_at', '-pk')
    binding_qs = binding_qs.annotate(
        latest_mes_success=Subquery(latest_upload.values('success')[:1]),
    )
    if keyword:
        binding_qs = binding_qs.filter(
            Q(product_code__icontains=keyword) |
            Q(rack__rack_code__icontains=keyword) |
            Q(rack__current_recipe__recipe_code__icontains=keyword)
        )
    if rack_code:
        binding_qs = binding_qs.filter(rack__rack_code__icontains=rack_code)
    if product_code:
        binding_qs = binding_qs.filter(product_code__icontains=product_code)
    if recipe_code:
        binding_qs = binding_qs.filter(rack__current_recipe__recipe_code__icontains=recipe_code)
    if sync_status == 'UPLOADED':
        binding_qs = binding_qs.filter(
            Q(latest_mes_success=True) |
            Q(latest_mes_success__isnull=True, mes_upload_status='UPLOADED')
        )
    elif sync_status == 'FAILED':
        binding_qs = binding_qs.filter(
            Q(latest_mes_success=False) |
            Q(latest_mes_success__isnull=True, mes_upload_status='FAILED')
        )
    elif sync_status == 'PENDING':
        binding_qs = binding_qs.filter(
            latest_mes_success__isnull=True, mes_upload_status='PENDING',
        )
    if product_status == 'DEFECTIVE':
        binding_qs = binding_qs.filter(is_defective=True)
    elif product_status == 'NORMAL':
        binding_qs = binding_qs.filter(is_defective=False)

    if start_value:
        binding_qs = binding_qs.filter(bound_at__gte=timezone.make_aware(datetime.combine(start_value, time.min)))
    if end_value:
        binding_qs = binding_qs.filter(bound_at__lt=timezone.make_aware(datetime.combine(end_value + timedelta(days=1), time.min)))

    binding_page = Paginator(binding_qs, 50).get_page(request.GET.get('page'))
    binding_rows = _build_binding_rows(binding_page.object_list)
    recipe_rows = _build_recipe_rows(keyword=keyword, rack_code=rack_code, recipe_code=recipe_code)
    pending_records = MesService.pending_retry_records(limit=200)
    _decorate_mes_records(pending_records)
    consistency_issues = _build_consistency_issues(pending_records, recipe_rows)

    stats = MesService.get_stats(hours=24)
    latest_record = MesRecord.objects.order_by('-created_at').first()
    recent_cutoff = timezone.now() - timedelta(minutes=10)
    mes_link = {
        'label': '尚无通信', 'tone': 'muted', 'detail': '等待第一次 MES 调用',
    }
    if latest_record:
        if latest_record.created_at < recent_cutoff:
            mes_link = {'label': '无近期通信', 'tone': 'warn', 'detail': '最后一次调用超过 10 分钟'}
        elif latest_record.success:
            mes_link = {'label': '通信正常', 'tone': 'ok', 'detail': '最近一次调用成功'}
        else:
            mes_link = {'label': '通信异常', 'tone': 'fail', 'detail': latest_record.error_message or '最近一次调用失败'}

    active_cycle = (
        StationCycle.objects.exclude(phase=StationPhase.COMPLETED)
        .select_related('rack').order_by('-created_at').first()
    )
    current_rack = active_cycle.rack if active_cycle and active_cycle.rack_id else None

    context = {
        'tab': tab,
        'keyword': keyword,
        'rack_code': rack_code,
        'product_code': product_code,
        'recipe_code': recipe_code,
        'sync_status': sync_status,
        'product_status': product_status,
        'binding_rows': binding_rows,
        'binding_page': binding_page,
        'binding_total': Product.objects.count(),
        'recipe_rows': recipe_rows,
        'recipe_total': RackRecipe.objects.count(),
        'pending_records': pending_records,
        'consistency_issues': consistency_issues,
        'mes_link': mes_link,
        'current_rack': current_rack,
        'records': records,
        'stats': stats,
        'action_choices': MesAction.choices,
        'action_filter': action_filter,
        'result_filter': result_filter,
        'start_date': start_date,
        'end_date': end_date,
        'latest_record': latest_record,
    }
    return render(request, 'mes/record_list.html', context)


def _decorate_mes_records(records):
    """Expose safe display values even when historical JSON lacks a key."""
    for record in records:
        record.display_rack_code = (
            record.rack.rack_code if record.rack_id
            else record.request_payload.get('rack_code') or '—'
        )
        record.display_product_code = (
            record.product.product_code if record.product_id
            else record.request_payload.get('product_code') or '—'
        )


def _build_binding_rows(products):
    """Combine local binding, foam result and latest MES acknowledgement."""
    products = list(products)
    if not products:
        return []
    product_ids = [item.pk for item in products]
    foam_by_product = {}
    for foam in (
        FoamInspectionResult.objects.filter(product_id__in=product_ids)
        .order_by('-created_at', '-pk')
    ):
        foam_by_product.setdefault(foam.product_id, foam)

    upload_by_code = {}
    upload_records = MesRecord.objects.filter(
        action=MesAction.UPLOAD_PRODUCT_BARCODE,
    ).select_related('product').order_by('-created_at', '-pk')[:2000]
    for record in upload_records:
        code = record.product.product_code if record.product_id else record.request_payload.get('product_code')
        if code:
            upload_by_code.setdefault(str(code), record)

    from collections import OrderedDict
    rack_groups = OrderedDict()
    for product in products:
        rack_id = product.rack_id or 0
        if rack_id not in rack_groups:
            recipe = product.rack.current_recipe if product.rack_id else None
            rack_groups[rack_id] = {
                'rack': product.rack,
                'recipe': recipe,
                'latest_bound_at': product.bound_at,
                'capacity': recipe.total_quantity if recipe and recipe.total_quantity else None,
                'layer_count': recipe.layer_count if recipe and recipe.layer_count else None,
                'quantity_per_layer': recipe.quantity_per_layer if recipe and recipe.quantity_per_layer else None,
                'products': [],
            }
        elif product.bound_at and (
            rack_groups[rack_id]['latest_bound_at'] is None
            or product.bound_at > rack_groups[rack_id]['latest_bound_at']
        ):
            rack_groups[rack_id]['latest_bound_at'] = product.bound_at
        foam = foam_by_product.get(product.pk)
        upload = upload_by_code.get(product.product_code)
        recipe = rack_groups[rack_id]['recipe']
        position = foam.position_index if foam and foam.position_index else None
        layer_no = slot_no = None
        if position and recipe and recipe.quantity_per_layer:
            layer_no = (position - 1) // recipe.quantity_per_layer + 1
            slot_no = (position - 1) % recipe.quantity_per_layer + 1
        if upload:
            sync_label = '已确认' if upload.success else '上传失败'
            sync_tone = 'ok' if upload.success else 'fail'
        else:
            sync_labels = {'UPLOADED': '已上传', 'FAILED': '上传失败', 'PENDING': '待上传'}
            sync_label = sync_labels.get(product.mes_upload_status, '待上传')
            sync_tone = {'UPLOADED': 'ok', 'FAILED': 'fail'}.get(product.mes_upload_status, 'warn')
        rack_groups[rack_id]['products'].append({
            'product': product, 'rack': product.rack, 'recipe': recipe,
            'foam': foam, 'upload': upload, 'position': position,
            'layer_no': layer_no, 'slot_no': slot_no,
            'sync_label': sync_label, 'sync_tone': sync_tone,
            'mes_id': upload.response_payload.get('mes_id', '') if upload and upload.success else '',
        })

    result = []
    for g in rack_groups.values():
        layer_count = g['layer_count'] or 1
        qty_per_layer = g['quantity_per_layer'] or max(len(g['products']), 1)
        total_slots = g['capacity'] or (layer_count * qty_per_layer)

        slot_map = {}
        unpositioned = []
        for p_row in g['products']:
            if p_row.get('position'):
                slot_map[p_row['position']] = p_row
            else:
                unpositioned.append(p_row)

        slot_cursor = 1
        for p_row in unpositioned:
            while slot_cursor in slot_map and slot_cursor <= total_slots:
                slot_cursor += 1
            slot_map[slot_cursor] = p_row
            p_row['slot_no'] = ((slot_cursor - 1) % qty_per_layer) + 1
            p_row['layer_no'] = ((slot_cursor - 1) // qty_per_layer) + 1
            p_row['slot_label'] = f"L{p_row['layer_no']}-{p_row['slot_no']}"
            slot_cursor += 1

        layers = []
        for l_idx in range(layer_count, 0, -1):
            slots = []
            for s_idx in range(1, qty_per_layer + 1):
                pos_idx = (l_idx - 1) * qty_per_layer + s_idx
                p_data = slot_map.get(pos_idx)
                slots.append({
                    'slot_no': s_idx,
                    'layer_no': l_idx,
                    'position_index': pos_idx,
                    'slot_label': f'L{l_idx}-{s_idx}',
                    'data': p_data,
                    'is_occupied': bool(p_data),
                })
            layers.append({'layer_no': l_idx, 'slots': slots})

        g['layers'] = layers
        g['occupied_count'] = len(g['products'])
        g['total_slots'] = total_slots
        g['occupancy_percent'] = int((len(g['products']) / total_slots * 100)) if total_slots else 0
        result.append(g)

    return sorted(
        result,
        key=lambda group: (
            group['latest_bound_at'] is not None,
            group['latest_bound_at'] or timezone.make_aware(datetime.min),
            group['rack'].pk if group['rack'] else 0,
        ),
        reverse=True,
    )


def _build_recipe_rows(*, keyword='', rack_code='', recipe_code=''):
    racks = Rack.objects.select_related('current_recipe').order_by('-updated_at')
    if keyword:
        racks = racks.filter(
            Q(rack_code__icontains=keyword) |
            Q(current_recipe__recipe_code__icontains=keyword) |
            Q(current_recipe__name__icontains=keyword)
        )
    if rack_code:
        racks = racks.filter(rack_code__icontains=rack_code)
    if recipe_code:
        racks = racks.filter(current_recipe__recipe_code__icontains=recipe_code)

    latest_by_rack = {}
    for record in (
        MesRecord.objects.filter(action=MesAction.GET_RACK_RECIPE)
        .order_by('-created_at', '-pk')[:1000]
    ):
        code = record.rack.rack_code if record.rack_id else record.request_payload.get('rack_code')
        if code:
            latest_by_rack.setdefault(str(code), record)

    compare_fields = (
        ('layer_count', '层数'), ('quantity_per_layer', '每层数量'),
        ('total_quantity', '总数量'), ('layer_height', '层高'),
        ('layer_spacing', '层距'), ('tolerance_x', 'X 容差'),
        ('tolerance_y', 'Y 容差'), ('tolerance_z', 'Z 容差'),
    )
    rows = []
    for rack in racks[:200]:
        recipe = rack.current_recipe
        record = latest_by_rack.get(rack.rack_code)
        mes_data = record.response_payload.get('recipe', {}) if record and record.success else {}
        comparisons = []
        mismatch_count = 0
        for key, label in compare_fields:
            local_value = getattr(recipe, key, None) if recipe else None
            mes_value = mes_data.get(key)
            matches = None
            if local_value is not None and mes_value is not None:
                try:
                    matches = Decimal(str(local_value)) == Decimal(str(mes_value))
                except InvalidOperation:
                    matches = str(local_value) == str(mes_value)
                mismatch_count += 0 if matches else 1
            comparisons.append({
                'key': key, 'label': label, 'local': local_value,
                'mes': mes_value, 'matches': matches,
            })
        rows.append({
            'rack': rack, 'recipe': recipe, 'record': record,
            'mes_data': mes_data, 'comparisons': comparisons,
            'mismatch_count': mismatch_count,
        })
    return rows


def _build_consistency_issues(pending_records, recipe_rows):
    issues = []
    for product in Product.objects.filter(rack__isnull=True).order_by('-updated_at')[:100]:
        issues.append({
            'level': 'warn', 'type': '产品未绑定料框', 'rack_code': '—',
            'product_code': product.product_code,
            'message': '产品已在本地创建，但尚未建立料框绑定。',
            'updated_at': product.updated_at,
        })
    for record in pending_records[:100]:
        issues.append({
            'level': 'fail', 'type': 'MES 请求待补传',
            'rack_code': record.rack.rack_code if record.rack_id else record.request_payload.get('rack_code', '—'),
            'product_code': record.product.product_code if record.product_id else record.request_payload.get('product_code', '—'),
            'message': record.error_message or f'{record.get_action_display()}尚未成功',
            'updated_at': record.created_at, 'record_id': record.pk,
        })
    for row in recipe_rows:
        if row['mismatch_count']:
            issues.append({
                'level': 'fail', 'type': '配方参数不一致',
                'rack_code': row['rack'].rack_code, 'product_code': '—',
                'message': f"本地缓存与最近 MES 返回有 {row['mismatch_count']} 个参数不一致。",
                'updated_at': row['record'].created_at if row['record'] else row['rack'].updated_at,
            })
    return sorted(issues, key=lambda item: item['updated_at'], reverse=True)


def recipe_check(request):
    """第 7 步配方核对及 2D 料架测量调试页。"""
    station_cycle = _display_station_cycle()
    measurement_profile = RackMeasurementService.active_profile()
    return render(request, 'mes/recipe_check.html', {
        'verification': _build_recipe_verification(station_cycle),
        'measurement_profile': measurement_profile,
        'profile_data': _serialize_profile(measurement_profile),
    })


def _display_station_cycle():
    cycle_qs = StationCycle.objects.select_related(
        'workflow__product__rack__current_recipe',
    ).order_by('-created_at')
    return cycle_qs.exclude(phase=StationPhase.COMPLETED).first() or cycle_qs.first()


def _build_recipe_verification(cycle):
    """Build the compact two-item MES/2D comparison read model."""
    product = cycle.product if cycle else None
    rack = product.rack if product else None
    recipe = rack.current_recipe if rack else None

    if cycle is None:
        state = ('等待生产任务', 'muted', '当前没有可核对的装箱任务')
        camera_state = '等待任务'
    elif cycle.recipe_verified is True:
        state = ('校验通过', 'ok', '层高、层距均在 MES 配方容差内')
        camera_state = '测量完成'
    elif cycle.recipe_verified is False:
        state = ('校验不通过', 'fail', cycle.last_error or '实测值超出 MES 配方容差')
        camera_state = '测量完成'
    elif cycle.phase == StationPhase.WAIT_RECIPE_VERIFY:
        state = ('等待校验', 'running', '等待 PLC 配方校验触发 DB100.DBX50.0')
        camera_state = '等待 PLC 触发'
    elif cycle.phase in {
        StationPhase.WAIT_RECIPE_RESET,
        StationPhase.WAIT_FOAM,
        StationPhase.WAIT_FOAM_RESET,
        StationPhase.WAIT_BOXING,
        StationPhase.WAIT_BOXING_RESET,
        StationPhase.COMPLETED,
    }:
        state = ('校验已完成', 'ok', '本次任务已完成配置核对')
        camera_state = '测量完成'
    else:
        state = ('等待前序流程', 'muted', '料框配方和定位完成后自动进入配置核对')
        camera_state = '等待前序流程'

    tolerance = recipe.tolerance_z if recipe else 3.0

    def item(label, expected, measured):
        difference = None
        passed = None
        if expected is not None and measured is not None:
            difference = measured - expected
            passed = tolerance is not None and abs(difference) <= tolerance
        return {
            'label': label,
            'expected': expected,
            'measured': measured,
            'difference': difference,
            'tolerance': tolerance,
            'passed': passed,
        }

    return {
        'cycle': cycle,
        'product': product,
        'rack': rack,
        'recipe': recipe,
        'state_label': state[0],
        'state_tone': state[1],
        'state_message': state[2],
        'camera_state': camera_state,
        'items': [
            item(
                '料架层高',
                recipe.layer_height if recipe else None,
                cycle.measured_layer_height if cycle else None,
            ),
            item(
                '料架层距',
                recipe.layer_spacing if recipe else None,
                cycle.measured_layer_spacing if cycle else None,
            ),
        ],
        'plc_allowed': cycle.recipe_verified if cycle else None,
        'plc_done': cycle.recipe_verified is not None if cycle else False,
        'updated_at': cycle.updated_at if cycle else None,
    }


def _serialize_verification(data):
    def serialize_item(item):
        return {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in item.items()
        }

    return {
        'cycle_id': data['cycle'].pk if data['cycle'] else None,
        'state_label': data['state_label'],
        'state_tone': data['state_tone'],
        'state_message': data['state_message'],
        'camera_state': data['camera_state'],
        'items': [serialize_item(item) for item in data['items']],
        'plc_allowed': data['plc_allowed'],
        'plc_done': data['plc_done'],
        'updated_at': data['updated_at'].isoformat() if data['updated_at'] else None,
    }


def _serialize_profile(profile):
    if profile is None:
        return {
            'id': None, 'name': '默认料架测量配置',
            'camera_code': 'CAM-INSPECT-RACK-01',
            'roi_x': 0, 'roi_y': 0, 'roi_width': 0, 'roi_height': 0,
            'mm_per_pixel': 1.0, 'edge_threshold': 0.18, 'min_peak_distance': 8,
            'is_active': False,
        }
    return {
        'id': profile.pk,
        'name': profile.name,
        'camera_code': profile.camera_code,
        **profile_parameters(profile),
        'is_active': profile.is_active,
    }


# ─── API 端点 ─────────────────────────────────────────────────────

def stats_api(request):
    """GET /mes/api/stats/ - 返回最近24小时统计 JSON。"""
    hours = int(request.GET.get('hours', 24))
    data = MesService.get_stats(hours=hours)
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(['POST'])
def refresh_recipe_api(request, rack_id: int):
    """Read the latest recipe from MES and refresh the local rack cache."""
    rack = get_object_or_404(Rack, pk=rack_id)
    response = MesService().get_rack_recipe(rack.rack_code, rack=rack)
    if not response.get('success'):
        return JsonResponse(response, status=502)
    data = response.get('recipe') or {}
    required = {
        'recipe_code', 'name', 'rack_type', 'layer_count',
        'quantity_per_layer', 'total_quantity', 'layer_height', 'layer_spacing',
    }
    missing = sorted(required - data.keys())
    if missing:
        return JsonResponse({
            'success': False,
            'error': f'MES 配方缺少字段: {", ".join(missing)}',
        }, status=422)

    production = ProductionService()
    with transaction.atomic():
        recipe = production.upsert_recipe(
            data['recipe_code'],
            name=data['name'], rack_type=data['rack_type'],
            layer_count=data['layer_count'],
            quantity_per_layer=data['quantity_per_layer'],
            total_quantity=data['total_quantity'],
            layer_height=data['layer_height'],
            layer_spacing=data['layer_spacing'],
            tolerance_x=data.get('tolerance_x', 0),
            tolerance_y=data.get('tolerance_y', 0),
            tolerance_z=data.get('tolerance_z', 0),
        )
        production.assign_recipe_to_rack(rack, recipe)
    return JsonResponse({
        'success': True, 'rack_code': rack.rack_code,
        'recipe_code': recipe.recipe_code, 'message': 'MES 配方已刷新并保存到本地',
    })


def recipe_verification_api(request):
    """页面轮询端点：PLC 自动计算完成后无刷新更新第 7 步状态。"""
    return JsonResponse(_serialize_verification(_build_recipe_verification(_display_station_cycle())))


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def rack_measurement_profile_api(request):
    """读取或保存手动调试与 PLC 自动测量共用参数。"""
    if request.method == 'GET':
        return JsonResponse({'success': True, 'profile': _serialize_profile(RackMeasurementService.active_profile())})
    try:
        body = json.loads(request.body or b'{}')
        values = {
            'name': str(body.get('name') or '默认料架测量配置').strip()[:128],
            'camera_code': str(body.get('camera_code') or 'CAM-INSPECT-RACK-01').strip()[:64],
            'roi_x': int(body.get('roi_x', 0)),
            'roi_y': int(body.get('roi_y', 0)),
            'roi_width': int(body.get('roi_width', 0)),
            'roi_height': int(body.get('roi_height', 0)),
            'mm_per_pixel': Decimal(str(body.get('mm_per_pixel'))),
            'edge_threshold': Decimal(str(body.get('edge_threshold', 0.18))),
            'min_peak_distance': int(body.get('min_peak_distance', 8)),
        }
        if any(values[key] < 0 for key in ('roi_x', 'roi_y', 'roi_width', 'roi_height')):
            raise ValueError('ROI 参数不能为负数')
        if not Decimal('0.000001') <= values['mm_per_pixel'] <= Decimal('100'):
            raise ValueError('毫米/像素标定值必须在 0.000001～100 之间')
        if not Decimal('0.03') <= values['edge_threshold'] <= Decimal('0.95'):
            raise ValueError('边缘阈值必须在 0.03～0.95 之间')
        if not 3 <= values['min_peak_distance'] <= 500:
            raise ValueError('最小峰间距必须在 3～500 像素之间')
        with transaction.atomic():
            RackMeasurementProfile.objects.filter(is_active=True).update(is_active=False)
            profile = RackMeasurementProfile.objects.create(**values, is_active=True)
        return JsonResponse({'success': True, 'profile': _serialize_profile(profile)})
    except (json.JSONDecodeError, ValueError, TypeError, InvalidOperation) as exc:
        return JsonResponse({'success': False, 'error': str(exc) or '参数格式错误'}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def rack_measurement_debug_api(request):
    """旁路调试：上传图片或拍照计算，不写 PLC、不推进 StationCycle。"""
    try:
        params = json.loads(request.POST.get('parameters', '{}'))
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'parameters 不是有效 JSON'}, status=400)

    cycle = _display_station_cycle()
    recipe = cycle.product.rack.current_recipe if cycle and cycle.product and cycle.product.rack else None
    try:
        if recipe is None:
            recipe = SimpleNamespace(
                layer_count=int(params.get('layer_count', 0)),
                layer_height=Decimal(str(params.get('expected_layer_height'))),
                layer_spacing=Decimal(str(params.get('expected_layer_spacing'))),
                tolerance_z=Decimal(str(params.get('tolerance', 3))),
            )
        uploaded = request.FILES.get('image')
        mode = request.POST.get('mode', 'upload')
        input_path = ''
        service = RackMeasurementService()
        if mode == 'camera':
            camera_code = str(params.get('camera_code') or 'CAM-INSPECT-RACK-01')
            image, input_path = service.capture(camera_code)
            source = 'MANUAL_CAMERA'
        else:
            if uploaded is None:
                raise RackMeasurementError('请选择一张料架图片')
            max_bytes = int(getattr(settings, 'VISION_MAX_UPLOAD_BYTES', 25 * 1024 * 1024))
            if uploaded.size > max_bytes:
                raise RackMeasurementError(f'图片不能超过 {max_bytes // 1024 // 1024} MB')
            data = np.frombuffer(uploaded.read(), dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                raise RackMeasurementError('上传文件不是可识别的图片')
            max_pixels = int(getattr(settings, 'VISION_MAX_IMAGE_PIXELS', 25_000_000))
            if image.shape[0] * image.shape[1] > max_pixels:
                raise RackMeasurementError(f'图片像素总数不能超过 {max_pixels}')
            source = 'MANUAL_UPLOAD'
        profile = RackMeasurementService.active_profile()
        result, record = service.measure(
            image,
            source=source,
            recipe=recipe,
            cycle=cycle,
            profile=profile,
            parameters=params,
            input_image_path=input_path,
        )
        return JsonResponse({
            'success': result.success,
            'measurement_id': record.pk,
            'detected_layer_count': result.detected_layer_count,
            'measured_layer_height': result.measured_layer_height,
            'measured_layer_spacing': result.measured_layer_spacing,
            'confidence': round(result.confidence, 4),
            'passed': record.passed,
            'error': result.error,
            'roi': result.roi,
            'candidate_lines': result.candidate_lines,
            'result_image_url': f'{settings.MEDIA_URL}{record.result_image_path}',
            'side_effects': '旁路调试，未写入 PLC，未改变工位阶段',
        }, status=200 if result.success else 422)
    except (RackMeasurementError, ValueError, TypeError, InvalidOperation, AttributeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def retry_api(request, record_id: int):
    """POST /mes/api/retry/<id>/ - 重传指定失败记录。"""
    svc = MesService()
    result = svc.retry_record(record_id)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(['POST'])
def test_upload_api(request):
    """POST /mes/api/test/ - 开发调试：手动触发一次 MES 上传测试。"""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    action = body.get('action', 'UPLOAD_BOXING_RESULT')
    payload = body.get('payload', {'test': True})

    svc = MesService()
    if action == MesAction.UPLOAD_BOXING_RESULT:
        result = svc.upload_boxing_result(payload)
    elif action == MesAction.UPLOAD_PRODUCT_BARCODE:
        result = svc.upload_product_barcode(
            payload.get('product_code', 'TEST-P'),
            payload.get('rack_code', 'TEST-R'),
        )
    elif action == MesAction.GET_RACK_RECIPE:
        result = svc.get_rack_recipe(payload.get('rack_code', 'TEST-R'))
    elif action == MesAction.UPLOAD_ALARM:
        result = svc.upload_alarm(
            payload.get('alarm_code', 'TEST'),
            payload.get('message', '测试报警'),
        )
    else:
        result = svc.upload_boxing_result(payload)

    return JsonResponse(result)


@csrf_exempt
@require_http_methods(['POST'])
def binding_update_api(request):
    """POST /mes/api/binding/update/"""
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    update_type = body.get('type', '')
    product_id = body.get('product_id')
    new_value = str(body.get('new_value', '')).strip()

    if not product_id:
        return JsonResponse({'success': False, 'error': '缺少 product_id'}, status=400)
    if not new_value:
        return JsonResponse({'success': False, 'error': '新值不能为空'}, status=400)

    product = get_object_or_404(Product, pk=product_id)

    try:
        with transaction.atomic():
            if update_type == 'rack_code':
                rack, _ = Rack.objects.get_or_create(rack_code=new_value)
                old_rack_code = product.rack.rack_code if product.rack_id else '—'
                product.rack = rack
                product.save(update_fields=['rack', 'updated_at'])
                return JsonResponse({
                    'success': True,
                    'message': f'料框码已更新: {old_rack_code} → {new_value}',
                    'rack_code': rack.rack_code,
                    'rack_id': rack.pk,
                })
            elif update_type == 'product_code':
                if Product.objects.filter(product_code=new_value).exclude(pk=product_id).exists():
                    return JsonResponse({'success': False, 'error': f'产品条码 {new_value} 已存在'}, status=409)
                old_code = product.product_code
                product.product_code = new_value
                product.save(update_fields=['product_code', 'updated_at'])
                return JsonResponse({
                    'success': True,
                    'message': f'产品条码已更新: {old_code} → {new_value}',
                    'product_code': new_value,
                    'product_id': product.pk,
                })
            else:
                return JsonResponse({'success': False, 'error': f'不支持的修改类型: {update_type}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def binding_add_api(request):
    """POST /mes/api/binding/add/"""
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    rack_code = str(body.get('rack_code', '')).strip()
    product_code = str(body.get('product_code', '')).strip()

    if not rack_code:
        return JsonResponse({'success': False, 'error': '料框码不能为空'}, status=400)
    if not product_code:
        return JsonResponse({'success': False, 'error': '产品条码不能为空'}, status=400)

    try:
        with transaction.atomic():
            rack, _ = Rack.objects.get_or_create(rack_code=rack_code)
            if Product.objects.filter(product_code=product_code).exists():
                return JsonResponse({'success': False, 'error': f'产品条码 {product_code} 已存在'}, status=409)
            product = Product.objects.create(product_code=product_code, rack=rack)
            return JsonResponse({
                'success': True,
                'message': f'已新增绑定: 料框 {rack_code} ← 产品 {product_code}',
                'rack_code': rack.rack_code,
                'rack_id': rack.pk,
                'product_code': product.product_code,
                'product_id': product.pk,
            })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def rack_binding_save_api(request):
    """
    POST /mes/api/rack-binding/save/
    批量保存料框与多个产品条码的绑定关系。
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    rack_id = body.get('rack_id')
    rack_code = str(body.get('rack_code', '')).strip()
    products_data = body.get('products', [])
    deleted_product_ids = body.get('deleted_product_ids', [])

    if not rack_code:
        return JsonResponse({'success': False, 'error': '料框码不能为空'}, status=400)

    try:
        with transaction.atomic():
            if rack_id:
                rack = get_object_or_404(Rack, pk=rack_id)
                if rack.rack_code != rack_code:
                    existing_rack = Rack.objects.filter(rack_code=rack_code).exclude(pk=rack_id).first()
                    if existing_rack:
                        rack = existing_rack
                    else:
                        rack.rack_code = rack_code
                        rack.save(update_fields=['rack_code', 'updated_at'])
            else:
                rack, _ = Rack.objects.get_or_create(rack_code=rack_code)

            if deleted_product_ids:
                Product.objects.filter(pk__in=deleted_product_ids, rack=rack).update(rack=None, bound_at=None)

            saved_products = []
            seen_codes = set()
            for item in products_data:
                p_code = str(item.get('product_code', '')).strip()
                if not p_code:
                    continue
                if p_code in seen_codes:
                    return JsonResponse({'success': False, 'error': f'提交的产品列表中包含重复条码: {p_code}'}, status=400)
                seen_codes.add(p_code)

                p_id = item.get('id')
                if p_id:
                    prod = get_object_or_404(Product, pk=p_id)
                    conflict = Product.objects.filter(product_code=p_code).exclude(pk=p_id).first()
                    if conflict:
                        return JsonResponse({'success': False, 'error': f'产品条码 {p_code} 已被其他记录占用'}, status=409)
                    prod.product_code = p_code
                    prod.rack = rack
                    prod.save(update_fields=['product_code', 'rack', 'updated_at'])
                    saved_products.append(prod)
                else:
                    existing_prod = Product.objects.filter(product_code=p_code).first()
                    if existing_prod:
                        existing_prod.rack = rack
                        existing_prod.save(update_fields=['rack', 'updated_at'])
                        saved_products.append(existing_prod)
                    else:
                        new_prod = Product.objects.create(product_code=p_code, rack=rack)
                        saved_products.append(new_prod)

            return JsonResponse({
                'success': True,
                'message': f'料框 {rack.rack_code} 绑定已保存（共 {len(saved_products)} 件产品）',
                'rack_id': rack.pk,
                'rack_code': rack.rack_code,
                'product_count': len(saved_products),
            })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_http_methods(['GET'])
def rack_products_api(request, rack_code: str):
    """
    GET /mes/api/rack-products/<rack_code>/
    查询指定料框当前绑定的全部产品条码数据，供人工修改/补全弹窗拉取。
    """
    rack = Rack.objects.filter(rack_code=rack_code).select_related('current_recipe').first()
    if not rack:
        return JsonResponse({'success': True, 'rack_code': rack_code, 'products': [], 'recipe': None})

    products = list(
        Product.objects.filter(rack=rack)
        .order_by('created_at', 'pk')
        .values('id', 'product_code', 'current_state', 'mes_upload_status')
    )
    recipe_info = None
    if rack.current_recipe:
        r = rack.current_recipe
        recipe_info = {
            'recipe_code': r.recipe_code,
            'name': r.name,
            'layer_count': r.layer_count,
            'quantity_per_layer': r.quantity_per_layer,
            'total_quantity': r.total_quantity,
            'layer_height': float(r.layer_height) if r.layer_height else None,
            'layer_spacing': float(r.layer_spacing) if r.layer_spacing else None,
            'tolerance_z': float(r.tolerance_z) if r.tolerance_z else 3.0,
        }

    return JsonResponse({
        'success': True,
        'rack_id': rack.pk,
        'rack_code': rack.rack_code,
        'products': products,
        'product_count': len(products),
        'recipe': recipe_info,
    })


@csrf_exempt
@require_http_methods(['POST'])
def recipe_tolerance_save_api(request):
    """
    POST /mes/api/recipe-tolerance/save/
    【新功能 1】：动态设置和保存配方核验允许容差阈值。
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    recipe_id = body.get('recipe_id')
    recipe_code = str(body.get('recipe_code', '')).strip()
    rack_code = str(body.get('rack_code', '')).strip()
    tolerance_val = body.get('tolerance_z') or body.get('tolerance_height') or body.get('tolerance')

    if tolerance_val is None:
        return JsonResponse({'success': False, 'error': '容差阈值不能为空'}, status=400)

    try:
        tolerance_dec = Decimal(str(tolerance_val))
        if tolerance_dec < 0 or tolerance_dec > 100:
            raise ValueError('容差阈值需在 0 ~ 100 mm 之间')
    except (InvalidOperation, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'无效的容差数值: {e}'}, status=400)

    recipe = None
    if recipe_id:
        recipe = RackRecipe.objects.filter(pk=recipe_id).first()
    elif recipe_code:
        recipe = RackRecipe.objects.filter(recipe_code=recipe_code).first()
    elif rack_code:
        rack = Rack.objects.filter(rack_code=rack_code).first()
        if rack and rack.current_recipe:
            recipe = rack.current_recipe

    if not recipe:
        recipe = RackRecipe.objects.first()

    if not recipe:
        return JsonResponse({'success': False, 'error': '未找到对应配方'}, status=404)

    recipe.tolerance_z = tolerance_dec
    recipe.save(update_fields=['tolerance_z', 'updated_at'])

    return JsonResponse({
        'success': True,
        'message': f'配方 {recipe.recipe_code} 容差阈值已成功更新为 ±{tolerance_dec} mm',
        'recipe_code': recipe.recipe_code,
        'tolerance_z': float(tolerance_dec),
    })


@csrf_exempt
@require_http_methods(['POST'])
def manual_reupload_binding_api(request):
    """
    POST /mes/api/manual-reupload/
    【新功能 2】：人工修改/新增/补全料框与产品条码绑定数据，并立即重新上传 MES。
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求体不是有效的 JSON'}, status=400)

    rack_code = str(body.get('rack_code', '')).strip()
    products_data = body.get('products', [])
    deleted_ids = body.get('deleted_product_ids', [])

    if not rack_code:
        return JsonResponse({'success': False, 'error': '料框码不能为空'}, status=400)

    try:
        with transaction.atomic():
            rack, _ = Rack.objects.get_or_create(rack_code=rack_code)

            if deleted_ids:
                Product.objects.filter(pk__in=deleted_ids, rack=rack).update(rack=None, bound_at=None)

            saved_products = []
            seen_codes = set()
            for item in products_data:
                p_code = str(item.get('product_code', '')).strip()
                if not p_code:
                    continue
                if p_code in seen_codes:
                    return JsonResponse({'success': False, 'error': f'列表中包含重复产品条码: {p_code}'}, status=400)
                seen_codes.add(p_code)

                p_id = item.get('id')
                if p_id:
                    prod = get_object_or_404(Product, pk=p_id)
                    conflict = Product.objects.filter(product_code=p_code).exclude(pk=p_id).first()
                    if conflict:
                        return JsonResponse({'success': False, 'error': f'条码 {p_code} 已被占用'}, status=409)
                    prod.product_code = p_code
                    prod.rack = rack
                    prod.save(update_fields=['product_code', 'rack', 'updated_at'])
                    saved_products.append(prod)
                else:
                    existing_prod = Product.objects.filter(product_code=p_code).first()
                    if existing_prod:
                        existing_prod.rack = rack
                        existing_prod.save(update_fields=['rack', 'updated_at'])
                        saved_products.append(existing_prod)
                    else:
                        new_prod = Product.objects.create(product_code=p_code, rack=rack)
                        saved_products.append(new_prod)

            payload = {
                'rack_code': rack.rack_code,
                'recipe_code': rack.current_recipe.recipe_code if rack.current_recipe else 'DEFAULT-RECIPE',
                'total_quantity': len(saved_products),
                'products': [p.product_code for p in saved_products],
                'is_manual_reupload': True,
            }

            mes_svc = MesService()
            mes_res = mes_svc.upload_boxing_result(payload, rack=rack)
            is_success = bool(mes_res.get('success'))

            new_status = MesUploadStatus.UPLOADED if is_success else MesUploadStatus.FAILED
            for p in saved_products:
                p.mes_upload_status = new_status
                p.save(update_fields=['mes_upload_status', 'updated_at'])

            msg = (
                f'已补全并成功重新上传 MES！料框 {rack.rack_code} 包含 {len(saved_products)} 件产品。'
                if is_success else
                f'本地绑定已保存，但 MES 上传失败：{mes_res.get("error", "接口异常")}'
            )

            return JsonResponse({
                'success': is_success,
                'message': msg,
                'rack_code': rack.rack_code,
                'product_count': len(saved_products),
                'mes_response': mes_res,
            })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

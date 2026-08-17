import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import cv2
import numpy as np
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.constants import MesAction
from apps.workflow.models import StationCycle, StationPhase
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
    """MES 接口监控页；视觉测量和配方核对在独立页面展示。"""
    action_filter = request.GET.get('action', '')
    result_filter = request.GET.get('result', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    qs = MesRecord.objects.select_related('product', 'rack').order_by('-created_at')

    if action_filter:
        qs = qs.filter(action=action_filter)
    if result_filter == 'ok':
        qs = qs.filter(success=True)
    elif result_filter == 'fail':
        qs = qs.filter(success=False)

    start_value = parse_date(start_date) if start_date else None
    end_value = parse_date(end_date) if end_date else None
    if start_value:
        qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(start_value, time.min)))
    if end_value:
        exclusive_end = end_value + timedelta(days=1)
        qs = qs.filter(created_at__lt=timezone.make_aware(datetime.combine(exclusive_end, time.min)))

    records = list(qs[:200])

    # 统计数据
    stats = MesService.get_stats(hours=24)
    demo_mode = not records
    if demo_mode:
        stats = {
            'hours': 24, 'total': 128, 'success': 126, 'fail': 2,
            'success_rate': 98.4, 'pending_retry': 1, 'by_action': [],
        }

    context = {
        'records': records,
        'stats': stats,
        'action_choices': MesAction.choices,
        'action_filter': action_filter,
        'result_filter': result_filter,
        'start_date': start_date,
        'end_date': end_date,
        'latest_record': records[0] if records else None,
        'demo_mode': demo_mode,
    }
    return render(request, 'mes/record_list.html', context)


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

    tolerance = recipe.tolerance_z if recipe else None

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
    """
    POST /mes/api/test/ - 开发调试：手动触发一次 MES 上传测试。
    Body (JSON): { "action": "UPLOAD_BOXING_RESULT", "payload": {...} }
    """
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

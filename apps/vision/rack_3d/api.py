"""
REST API (函数视图，JsonResponse)

3D 料架定位 MOCK/REAL 接口，前缀 /vision/rack-3d/：
- GET   recipes/                      配方列表
- GET   recipes/<id>/rois/            某配方某层的 ROI（?layer_no=）
- POST  rois/                         创建/更新 ROI
- PATCH recipes/<id>/coordinates/     更新理论坐标
- POST  capture/                      采集点云 + 坐标转换（预览）
- POST  calculate/                    执行定位计算（?save）
- GET   results/                      历史定位结果

统一响应：成功 {"success": true, "data": ...}
         失败 {"success": false, "error": {"code","message","details"}}

Requirements: 20.1-20.9
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.vision.models import (
    RackLocationRecipe,
    RackLocationROI3DEnhanced,
    RackLocationResult,
    ROI3DType,
)
from .services import RackPositioningService
from .exceptions import RackPositioningException, RackPositioningErrorCode as EC

logger = logging.getLogger(__name__)

_ROI_BOUND_FIELDS = ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')


def _ok(data, status=200):
    return JsonResponse({'success': True, 'data': data}, status=status)


def _err(code, message, details=None, status=400):
    return JsonResponse(
        {'success': False, 'error': {'code': code, 'message': message, 'details': details or {}}},
        status=status,
    )


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode('utf-8'))


def _handle_exc(exc):
    if isinstance(exc, RackPositioningException):
        status = 404 if exc.error_code in (EC.RECIPE_NOT_FOUND, EC.ROI_NOT_FOUND) else 400
        return _err(exc.error_code, exc.message, exc.details, status=status)
    logger.exception('rack-3d API 未处理异常')
    return _err('E9999', str(exc), status=500)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def page(request):
    """3D 料架定位工作台页面（Canvas 双窗口）。"""
    mode = getattr(settings, 'RACK_3D_POSITIONING_MODE', 'MOCK')
    return render(request, 'vision/rack_3d_positioning.html', {'mode': mode})


# ---------------------------------------------------------------------------
# 配方与 ROI
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def recipes(request):
    qs = RackLocationRecipe.objects.all()
    pos = request.GET.get('position_no')
    if pos not in (None, ''):
        qs = qs.filter(position_no=int(pos))
    data = [{
        'id': r.id,
        'recipe_name': r.recipe_name,
        'rack_type': r.rack_type,
        'position_no': r.position_no,
        'layer_no': r.layer_no,
        'layer_count': r.layer_count,
        'standard_x': float(r.standard_x),
        'standard_y': float(r.standard_y),
        'standard_z': float(r.standard_z),
        'confidence_threshold': float(r.confidence_threshold),
        'enabled': r.enabled,
    } for r in qs]
    return _ok(data)


@require_http_methods(['GET'])
def recipe_rois(request, recipe_id):
    qs = RackLocationROI3DEnhanced.objects.filter(recipe_id=recipe_id, enabled=True)
    layer_no = request.GET.get('layer_no')
    if layer_no not in (None, ''):
        qs = qs.filter(layer_no=int(layer_no))
    return _ok([roi.to_dict() for roi in qs.order_by('layer_no', 'priority')])


@csrf_exempt
@require_http_methods(['POST'])
def upsert_roi(request):
    try:
        payload = _body(request)
        recipe_id = payload.get('recipe_id')
        layer_no = payload.get('layer_no')
        roi_type = payload.get('roi_type', ROI3DType.MAIN)
        if not recipe_id or layer_no is None:
            return _err(EC.ROI_INVALID_BOUNDS, '缺少 recipe_id 或 layer_no')

        bounds = {}
        for f in _ROI_BOUND_FIELDS:
            if f not in payload:
                return _err(EC.ROI_INVALID_BOUNDS, f'缺少边界字段 {f}')
            bounds[f] = Decimal(str(payload[f]))
        # min < max 校验
        for axis in ('x', 'y', 'z'):
            if bounds[f'{axis}_min'] >= bounds[f'{axis}_max']:
                return _err(EC.ROI_INVALID_BOUNDS, f'{axis}_min 必须小于 {axis}_max')

        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        roi, created = RackLocationROI3DEnhanced.objects.update_or_create(
            recipe=recipe, layer_no=layer_no, roi_type=roi_type,
            defaults=dict(
                roi_name=payload.get('roi_name', f'L{layer_no}-{roi_type}'),
                position_no=recipe.position_no,
                **bounds,
            ),
        )
        return _ok(roi.to_dict(), status=201 if created else 200)
    except RackLocationRecipe.DoesNotExist:
        return _err(EC.RECIPE_NOT_FOUND, f'配方不存在: {payload.get("recipe_id")}', status=404)
    except (InvalidOperation, ValueError, json.JSONDecodeError) as exc:
        return _err(EC.ROI_INVALID_BOUNDS, str(exc))


@csrf_exempt
@require_http_methods(['PATCH', 'POST'])
def update_coordinates(request, recipe_id):
    try:
        payload = _body(request)
        recipe = RackLocationRecipe.objects.get(id=recipe_id)
        for field in ('standard_x', 'standard_y', 'standard_z'):
            if field in payload:
                setattr(recipe, field, Decimal(str(payload[field])))
        recipe.save(update_fields=['standard_x', 'standard_y', 'standard_z', 'updated_at'])
        return _ok({
            'id': recipe.id,
            'standard_x': float(recipe.standard_x),
            'standard_y': float(recipe.standard_y),
            'standard_z': float(recipe.standard_z),
        })
    except RackLocationRecipe.DoesNotExist:
        return _err(EC.RECIPE_NOT_FOUND, f'配方不存在: {recipe_id}', status=404)
    except (InvalidOperation, ValueError, json.JSONDecodeError) as exc:
        return _err('E9003', str(exc))


# ---------------------------------------------------------------------------
# 采集 / 计算
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def capture(request):
    try:
        payload = _body(request)
        recipe_id = int(payload['recipe_id'])
        layer_no = int(payload.get('layer_no', 1))
        data = RackPositioningService().capture_and_transform(recipe_id, layer_no)
        return _ok(data)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        return _err('E9003', f'参数错误: {exc}')
    except Exception as exc:  # noqa: BLE001
        return _handle_exc(exc)


@csrf_exempt
@require_http_methods(['POST'])
def calculate(request):
    try:
        payload = _body(request)
        recipe_id = int(payload['recipe_id'])
        layer_no = int(payload.get('layer_no', 1))
        save = bool(payload.get('save', False))
        result = RackPositioningService().execute_positioning(recipe_id, layer_no, save=save)
        return _ok(result)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        return _err('E9003', f'参数错误: {exc}')
    except Exception as exc:  # noqa: BLE001
        return _handle_exc(exc)


# ---------------------------------------------------------------------------
# 历史结果
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def results(request):
    qs = RackLocationResult.objects.all().order_by('-created_at')
    pos = request.GET.get('position_no')
    layer = request.GET.get('layer_no')
    if pos not in (None, ''):
        qs = qs.filter(position_no=int(pos))
    if layer not in (None, ''):
        qs = qs.filter(layer_no=int(layer))
    limit = min(int(request.GET.get('limit', 20)), 200)
    data = [{
        'id': r.id,
        'position_no': r.position_no,
        'layer_no': r.layer_no,
        'actual_x': float(r.actual_x), 'actual_y': float(r.actual_y), 'actual_z': float(r.actual_z),
        'offset_x': float(r.offset_x), 'offset_y': float(r.offset_y), 'offset_z': float(r.offset_z),
        'confidence': float(r.confidence),
        'is_success': r.is_success,
        'created_at': r.created_at.isoformat(),
    } for r in qs[:limit]]
    return _ok(data)

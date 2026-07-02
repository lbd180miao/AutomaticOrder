import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .services import CoordinateWorkbenchError, CoordinateWorkbenchService


logger = logging.getLogger(__name__)


def workbench(request):
    return render(request, 'coordinates/workbench.html')


@require_GET
def api_workbench(request):
    try:
        data = CoordinateWorkbenchService().get_workbench(request.GET.get('layer_no', 1))
        return _success(data)
    except Exception as exc:
        return _failure(exc)


@require_POST
def api_preview(request):
    try:
        data = CoordinateWorkbenchService().preview(_json_body(request))
        return _success(data)
    except Exception as exc:
        return _failure(exc)


@require_POST
def api_save(request):
    try:
        service = CoordinateWorkbenchService()
        saved = service.save(_json_body(request))
        return _success(service.preview(saved))
    except Exception as exc:
        return _failure(exc)


def _json_body(request):
    try:
        value = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinateWorkbenchError('INVALID_JSON', '请求体不是有效 JSON') from exc
    if not isinstance(value, dict):
        raise CoordinateWorkbenchError('INVALID_JSON', '请求体必须是 JSON 对象')
    return value


def _success(data):
    return JsonResponse({'success': True, 'data': data, 'error': None})


def _failure(exc):
    if isinstance(exc, CoordinateWorkbenchError):
        return JsonResponse({
            'success': False,
            'data': None,
            'error': {
                'code': exc.code, 'message': exc.message, 'fields': exc.fields,
            },
        }, status=exc.status)
    logger.exception('坐标模块请求失败', exc_info=exc)
    return JsonResponse({
        'success': False,
        'data': None,
        'error': {'code': 'INTERNAL_ERROR', 'message': '坐标模块内部错误', 'fields': {}},
    }, status=500)

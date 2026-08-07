import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.constants import MesAction
from .models import MesRecord
from .services import MesService


# ─── 页面视图 ─────────────────────────────────────────────────────

def record_list(request):
    """MES 监控主页：统计卡片 + 过滤表格。"""
    action_filter = request.GET.get('action', '')
    result_filter = request.GET.get('result', '')

    qs = MesRecord.objects.select_related('product', 'rack').order_by('-created_at')

    if action_filter:
        qs = qs.filter(action=action_filter)
    if result_filter == 'ok':
        qs = qs.filter(success=True)
    elif result_filter == 'fail':
        qs = qs.filter(success=False)

    records = qs[:200]

    # 统计数据
    stats = MesService.get_stats(hours=24)

    context = {
        'records': records,
        'stats': stats,
        'action_choices': MesAction.choices,
        'action_filter': action_filter,
        'result_filter': result_filter,
    }
    return render(request, 'mes/record_list.html', context)


# ─── API 端点 ─────────────────────────────────────────────────────

def stats_api(request):
    """GET /mes/api/stats/ - 返回最近24小时统计 JSON。"""
    hours = int(request.GET.get('hours', 24))
    data = MesService.get_stats(hours=hours)
    return JsonResponse(data)


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

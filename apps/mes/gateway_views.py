import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import remote_client


def page(request):
    return render(request, 'mes/gateway.html')


def status(request):
    try:
        cfg = remote_client.config()
        return JsonResponse({'gateway_url': cfg['gateway_url'], 'tasks': remote_client.rows()})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@require_POST
def test(request):
    try:
        data = json.loads(request.body or '{}')
        if data.get('mode') == 'health':
            return JsonResponse(remote_client.health())
        if data.get('mode') == 'rack_query':
            from apps.core.barcode_validator import validate_rack_barcode
            checked = validate_rack_barcode(data.get('rack_code'), check_db_duplicate=False)
            if not checked.is_valid:
                raise ValueError(checked.error_message)
            task_id = remote_client.submit('GET_RACK_RECIPE', {
                'rack_code': checked.cleaned_code, '_source': 'manual_arrival_test'})
            return JsonResponse({'success': True, 'id': task_id,
                'message': '已模拟料框到位事件并提交真实 MES 查询；不读写 PLC、不修改生产绑定'})
        if data.get('mode') != 'self_test':
            raise ValueError('不支持的测试动作')
        task_id = remote_client.submit('SELF_TEST', {'message': 'AGV 通信自检，不操作 PLC 和 MES'})
        return JsonResponse({'success': True, 'id': task_id, 'message': '任务已落库，等待网关执行'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

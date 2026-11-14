"""MES page proxy for the paired external computer; credentials stay server-side."""
import json
import uuid
import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings
from pathlib import Path
from urllib.parse import urlsplit
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_GET, require_POST
from . import remote_client
from .models import PkgTypeMapping

ACTIONS = ('GET_RACK_RECIPE', 'UPLOAD_PRODUCT_BARCODE', 'UPLOAD_BOXING_RESULT')


def gateway_call(path, payload=None):
    cfg = remote_client.config()
    with requests.Session() as session:
        session.trust_env = False
        response = session.request('POST' if payload is not None else 'GET',
            cfg['gateway_url'].rstrip('/') + path,
            headers={'Authorization':'Bearer ' + cfg['token']}, json=payload, timeout=(3, 8))
        try:
            body = response.json()
        except ValueError:
            raise ValueError('外部电脑未返回有效 JSON，请检查网关地址和版本') from None
        if not response.ok:
            raise ValueError(body.get('error') or f'外部网关 HTTP {response.status_code}')
        return body


def read_body(request):
    if len(request.body) > 16384:
        raise ValueError('请求内容过大')
    body = json.loads(request.body or '{}')
    if not isinstance(body, dict):
        raise ValueError('请求必须是 JSON 对象')
    return body


@require_GET
def status(request):
    data = {'connected':False, 'tasks':[], 'events':[], 'outbox':[], 'modes':{},
            'mappings':list(PkgTypeMapping.objects.filter(enabled=True).values('pkg_type_code','rack_type','plc_value'))}
    try:
        cfg = remote_client.config()
        data['gateway_url'] = cfg['gateway_url']
        data['outbox'] = [{**row, 'payload':json.loads(row['payload']), 'result':json.loads(row['result'])}
                          for row in remote_client.rows()]
        data.update(gateway_call('/api/communication'), connected=True)
    except (OSError, ValueError, KeyError, requests.RequestException) as exc:
        data['error'] = str(exc)
    response = JsonResponse(data)
    response['Cache-Control'] = 'no-store'
    return response


@require_POST
def control(request):
    try:
        body = read_body(request)
        operation = body.get('operation')
        if operation == 'mode':
            result = gateway_call('/api/communication/mode', {'action':body.get('action'), 'mode':body.get('mode')})
        elif operation == 'reply':
            result = gateway_call('/api/communication/reply', {'id':body.get('id'),
                'action':body.get('action'), 'result':body.get('result')})
        elif operation == 'send':
            action = body.get('action')
            if action not in ACTIONS:
                raise ValueError('请选择三个业务接口之一')
            from apps.core.barcode_validator import validate_rack_barcode, validate_product_barcode
            rack = validate_rack_barcode(body.get('rack_code')).raise_if_invalid()
            payload = {'rack_code':rack, '_source':'communication_debug'}
            if action == 'UPLOAD_PRODUCT_BARCODE':
                payload['product_code'] = validate_product_barcode(body.get('product_code'), check_db_duplicate=False).raise_if_invalid()
            # Durable requests remain queued when the paired computer is offline.
            if not isinstance(body.get('request_id'), str):
                raise ValueError('调试请求编号无效')
            key = 'communication-debug:' + str(uuid.UUID(body['request_id']))
            with remote_client.database() as db:
                old = db.execute('SELECT action,payload FROM tasks WHERE business_key=?', (key,)).fetchone()
                if old and (old['action'] != action or json.loads(old['payload']) != payload):
                    raise ValueError('重试请求编号不能更换接口或条码')
            task_id = remote_client.submit(action, payload, key)
            result = {'success':True, 'id':task_id, 'message':'请求已记录，等待 HTTP 同步；请在通信记录查看结果'}
        else:
            raise ValueError('未知通信操作')
        return JsonResponse(result)
    except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as exc:
        return JsonResponse({'success':False, 'error':str(exc)}, status=400)


@require_GET
def page(request):
    return render(request, 'mes/communication_page.html')


@require_http_methods(['GET', 'POST'])
def connection_config(request):
    path = Path(settings.DATA_DIR) / 'agv_gateway.json'
    try:
        current = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
        if not isinstance(current, dict):
            raise ValueError('本机配置格式无效')
        if request.method == 'GET':
            response = JsonResponse({'success': True, 'gateway_url': current.get('gateway_url', 'http://192.168.3.10:8001'),
                                     'token_configured': bool(current.get('token'))})
            response['Cache-Control'] = 'no-store'
            return response
        body = read_body(request)
        address = str(body.get('gateway_url', '')).strip().rstrip('/')
        parsed = urlsplit(address)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in address)):
            raise ValueError('请输入有效的 HTTP 地址和端口，例如 http://192.168.3.10:8001')
        if parsed.port is None or parsed.port < 1:
            raise ValueError('请填写通信端口，例如 8001')
        token = body.get('token')
        if token is not None and not isinstance(token, str):
            raise ValueError('配对认证格式无效')
        token = (token or '').strip() or current.get('token', '')
        if not isinstance(token, str) or not 24 <= len(token) <= 4096 or any(c.isspace() for c in token):
            raise ValueError('请填写与外部电脑一致的配对认证，至少 24 个字符')
        updated = dict(current, gateway_url=address, token=token)
        updated.setdefault('wait_seconds', 20)
        temporary = path.with_name('agv-gateway-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        remote_client.start_worker()
        remote_client._wake.set()
        return JsonResponse({'success': True, 'gateway_url': address,
                             'message': '配置已保存，后续通信使用新地址。首次配置后请重启程序。'})
    except (OSError, ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

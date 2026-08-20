"""MES 服务层：封装 MES 调用，记录每次请求/响应，支持失败重传。"""
import json
import logging

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.constants import MesAction
from .client import HttpMesClient, SimulatedMesClient
from .models import MesRecord

logger = logging.getLogger(__name__)


def get_mes_client():
    """按配置返回 MES 客户端实例。"""
    conf = getattr(settings, 'AUTOMATIC_ORDER', {})
    base_url = conf.get('MES_BASE_URL') or ''
    if conf.get('USE_SIMULATED_DEVICES', False) or not base_url.strip() or not base_url.startswith(('http://', 'https://')):
        return SimulatedMesClient()
    timeout = conf.get('MES_TIMEOUT', conf.get('DEVICE_TIMEOUT_SECONDS', 8))
    token = conf.get('MES_TOKEN') or None
    return HttpMesClient(base_url=base_url, timeout=timeout, token=token)


class MesService:
    """封装 MES 调用并持久化每次请求/响应记录。"""

    def __init__(self, client=None):
        self.client = client or get_mes_client()

    def _record(self, action, request_payload, response, product=None, rack=None):
        success = bool(response.get('success'))
        error_msg = ''
        if not success:
            error_msg = response.get('error', response.get('message', '未知错误'))
        MesRecord.objects.create(
            action=action,
            product=product,
            rack=rack,
            request_payload=request_payload,
            response_payload=response,
            success=success,
            error_message=error_msg,
        )
        return response

    # ── 业务动作 ─────────────────────────────────────

    def get_rack_recipe(self, rack_code, rack=None):
        payload = {'rack_code': rack_code}
        resp = self.client.get_rack_recipe(rack_code)
        return self._record(MesAction.GET_RACK_RECIPE, payload, resp, rack=rack)

    def upload_product_barcode(self, product_code, rack_code, product=None, rack=None):
        payload = {'product_code': product_code, 'rack_code': rack_code}
        resp = self.client.upload_product_barcode(product_code, rack_code)
        return self._record(MesAction.UPLOAD_PRODUCT_BARCODE, payload, resp,
                            product=product, rack=rack)

    def upload_boxing_result(self, payload, product=None, rack=None):
        resp = self.client.upload_boxing_result(payload)
        return self._record(MesAction.UPLOAD_BOXING_RESULT, payload, resp,
                            product=product, rack=rack)

    def upload_vision_result(self, payload, product=None, rack=None):
        resp = self.client.upload_vision_result(payload)
        return self._record(MesAction.UPLOAD_VISION_RESULT, payload, resp,
                            product=product, rack=rack)

    def upload_alarm(self, alarm_code, message, product=None, rack=None):
        payload = {'alarm_code': alarm_code, 'message': message}
        resp = self.client.upload_alarm(payload)
        return self._record(MesAction.UPLOAD_ALARM, payload, resp,
                            product=product, rack=rack)

    # ── 重传失败记录 ─────────────────────────────────

    @staticmethod
    def pending_retry_records(limit=100):
        """返回每组业务请求的最新失败记录，已被后续成功覆盖的不再重复补传。"""
        pending = []
        seen = set()
        records = (
            MesRecord.objects.select_related('product', 'rack')
            .order_by('-created_at', '-pk')
        )
        for record in records.iterator():
            key = (
                record.action,
                record.product_id,
                record.rack_id,
                json.dumps(record.request_payload, ensure_ascii=False, sort_keys=True, default=str),
            )
            if key in seen:
                continue
            seen.add(key)
            if not record.success:
                pending.append(record)
                if len(pending) >= limit:
                    break
        return pending

    def retry_record(self, record_id: int) -> dict:
        """
        按原始 request_payload 重新发送一次 MES 请求，
        并将重试结果追加为新的 MesRecord。
        """
        try:
            record = MesRecord.objects.get(pk=record_id)
        except MesRecord.DoesNotExist:
            return {'success': False, 'error': f'记录 #{record_id} 不存在'}

        action = record.action
        payload = record.request_payload

        action_map = {
            MesAction.GET_RACK_RECIPE: lambda p: self.client.get_rack_recipe(
                p.get('rack_code', '')),
            MesAction.UPLOAD_PRODUCT_BARCODE: lambda p: self.client.upload_product_barcode(
                p.get('product_code', ''), p.get('rack_code', '')),
            MesAction.UPLOAD_BOXING_RESULT: lambda p: self.client.upload_boxing_result(p),
            MesAction.UPLOAD_VISION_RESULT: lambda p: self.client.upload_vision_result(p),
            MesAction.UPLOAD_ALARM: lambda p: self.client.upload_alarm(p),
        }

        handler = action_map.get(action)
        if handler is None:
            return {'success': False, 'error': f'不支持重传的动作: {action}'}

        resp = handler(payload)
        new_record = MesRecord.objects.create(
            action=action,
            product=record.product,
            rack=record.rack,
            request_payload=payload,
            response_payload=resp,
            success=bool(resp.get('success')),
            error_message='' if resp.get('success') else resp.get('error', ''),
        )
        resp['record_id'] = new_record.pk
        logger.info('[MES] 重传 action=%s record_id=%s -> new_id=%s success=%s',
                    action, record_id, new_record.pk, resp.get('success'))
        return resp

    # ── 统计 ─────────────────────────────────────────

    @staticmethod
    def get_stats(hours: int = 24) -> dict:
        """返回最近 N 小时内各动作的成功/失败统计。"""
        since = timezone.now() - timezone.timedelta(hours=hours)
        qs = MesRecord.objects.filter(created_at__gte=since)
        total = qs.count()
        success_count = qs.filter(success=True).count()
        fail_count = total - success_count

        by_action = (
            qs.values('action')
            .annotate(total=Count('id'),
                      ok=Count('id', filter=Q(success=True)),
                      fail=Count('id', filter=Q(success=False)))
            .order_by('action')
        )

        pending_retry = len(MesService.pending_retry_records(limit=10000))

        return {
            'hours': hours,
            'total': total,
            'success': success_count,
            'fail': fail_count,
            'success_rate': round(success_count / total * 100, 1) if total else 0,
            'pending_retry': pending_retry,
            'by_action': list(by_action),
        }

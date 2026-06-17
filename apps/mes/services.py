"""MES 服务：封装 MES 调用并把每次请求/响应落库到 MesRecord。"""
from django.conf import settings

from apps.core.constants import MesAction
from .client import SimulatedMesClient
from .models import MesRecord


def get_mes_client():
    """按配置返回 MES 客户端。前期固定返回模拟客户端。"""
    conf = getattr(settings, 'AUTOMATIC_ORDER', {})
    if conf.get('USE_SIMULATED_DEVICES', True):
        return SimulatedMesClient()
    # 真实 MES 客户端在此接入。
    return SimulatedMesClient()


class MesService:
    """Handles MES calls and persistence of request/response records."""

    def __init__(self, client=None):
        self.client = client or get_mes_client()

    def _record(self, action, request_payload, response, product=None, rack=None):
        success = bool(response.get('success'))
        MesRecord.objects.create(
            action=action,
            product=product,
            rack=rack,
            request_payload=request_payload,
            response_payload=response,
            success=success,
            error_message=response.get('error', '') if not success else '',
        )
        return response

    def get_rack_recipe(self, rack_code, rack=None):
        resp = self.client.get_rack_recipe(rack_code)
        self._record(MesAction.GET_RACK_RECIPE, {'rack_code': rack_code}, resp, rack=rack)
        return resp

    def upload_product_barcode(self, product_code, rack_code, product=None, rack=None):
        resp = self.client.upload_product_barcode(product_code, rack_code)
        self._record(
            MesAction.UPLOAD_PRODUCT_BARCODE,
            {'product_code': product_code, 'rack_code': rack_code},
            resp, product=product, rack=rack,
        )
        return resp

    def upload_boxing_result(self, payload, product=None, rack=None):
        resp = self.client.upload_boxing_result(payload)
        self._record(MesAction.UPLOAD_BOXING_RESULT, payload, resp, product=product, rack=rack)
        return resp

    def upload_vision_result(self, payload, product=None, rack=None):
        resp = self.client.upload_vision_result(payload)
        self._record(MesAction.UPLOAD_VISION_RESULT, payload, resp, product=product, rack=rack)
        return resp

    def upload_alarm(self, alarm_code, message, product=None, rack=None):
        payload = {'alarm_code': alarm_code, 'message': message}
        resp = self.client.upload_alarm(payload)
        self._record(MesAction.UPLOAD_ALARM, payload, resp, product=product, rack=rack)
        return resp

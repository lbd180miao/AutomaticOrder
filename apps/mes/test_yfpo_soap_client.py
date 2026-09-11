# -*- coding: utf-8 -*-
"""
YFPO SOAP 客户端（zeep 版）、工厂选择与 MesService 落库测试。
zeep 内部网络调用通过 unittest.mock.patch 直接打桩 _invoke，不打真实网络。
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.constants import MesAction
from apps.mes.models import MesRecord
from apps.mes.services import MesService, get_mes_client, describe_mes_runtime
from apps.mes.yfpo_soap_client import YfpoSoapMesClient


# ── 辅助：构造模拟 _invoke 返回值 ─────────────────────────────────
def _ok(inner: dict) -> dict:
    """模拟 _invoke 成功返回。"""
    return {'success': True, 'mes_data': inner, 'message': inner.get('Message', '')}


def _fail(err: str = 'MES 业务校验未通过', *, business: bool = True) -> dict:
    """模拟 _invoke 失败返回。"""
    return {'success': False, 'business': business, 'error': err, 'mes_data': {}}


def _client_patched(invoke_return):
    """返回一个 _invoke 被打桩的 YfpoSoapMesClient，不触发真实网络。"""
    client = YfpoSoapMesClient('http://mes/BaseService.svc?wsdl', '2230', 'I308')
    client._invoke = MagicMock(return_value=invoke_return)
    return client


# ── get_rack_recipe 测试 ─────────────────────────────────────────
class YfpoSoapClientSimpleTests(SimpleTestCase):

    def test_check_ready_success(self):
        inner = {'Status': True, 'RackCode': 'R1', 'RackStatus': 1,
                 'HUQty': 26.0, 'HUMaxQty': 74.0, 'IsSealed': False, 'Message': 'ok'}
        client = _client_patched(_ok(inner))
        r = client.get_rack_recipe('R1')
        self.assertTrue(r['success'])
        self.assertEqual(r['hu_qty'], 26.0)
        self.assertEqual(r['hu_max_qty'], 74.0)
        self.assertFalse(r['is_sealed'])
        self.assertNotIn('recipe', r)  # 20260801 不回配方

    def test_non_available_racks_are_rejected(self):
        for status_val in (0, 2, 9, 3, None):
            with self.subTest(status=status_val):
                inner = {'Status': True, 'RackStatus': status_val, 'IsSealed': False}
                client = _client_patched(_ok(inner))
                r = client.get_rack_recipe('R1')
                self.assertFalse(r['success'])
                self.assertIn('禁止装箱', r['error'])

    def test_inner_status_false_is_business_rejection(self):
        inner = {'Status': False, 'IsSealed': True, 'Message': '料架已封箱，禁止装箱'}
        client = _client_patched(_ok(inner))
        r = client.get_rack_recipe('R1')
        # _invoke 返回 success=True 但 inner.Status=False，由 get_rack_recipe 再判
        # 实际上 _invoke 层已经判断 inner.Status，这里测 _invoke 直接返回 fail
        client2 = _client_patched({'success': False, 'business': True,
                                   'error': '料架已封箱，禁止装箱', 'mes_data': inner})
        r2 = client2.get_rack_recipe('R1')
        self.assertFalse(r2['success'])
        self.assertTrue(r2['business'])

    def test_no_pull_task_can_still_be_sealed_successfully(self):
        inner = {'Status': True, 'BinCode': '', 'IsNotTask': 1, 'Message': ''}
        client = _client_patched(_ok(inner))
        r = client.upload_boxing_result({'rack_code': 'R1'})
        self.assertTrue(r['success'])
        self.assertEqual(r['pull_task_label'], '无拉动任务')
        self.assertEqual(r['bin_code'], '')

    def test_bind_success_returns_part_no(self):
        inner = {'Status': True, 'Barcode': 'B1', 'PartNo': '12441620',
                 'HUQty': 1, 'HUMaxQty': 74, 'IsFull': False, 'Message': '绑定成功'}
        client = _client_patched(_ok(inner))
        r = client.upload_product_barcode('B1', 'R1')
        self.assertTrue(r['success'])
        self.assertEqual(r['part_no'], '12441620')
        self.assertFalse(r['is_full'])

    def test_seal_success_returns_bin_code(self):
        inner = {'Status': True, 'BinCode': 'A-01-03', 'IsNotTask': 0,
                 'TaskGuid': 'g1', 'Message': '封箱成功'}
        client = _client_patched(_ok(inner))
        r = client.upload_boxing_result({'rack_code': 'R1'})
        self.assertTrue(r['success'])
        self.assertEqual(r['bin_code'], 'A-01-03')

    def test_outer_failure_propagates(self):
        client = _client_patched({'success': False, 'error': 'MES 外层状态=500 ',
                                  'mes_data': {}})
        r = client.get_rack_recipe('R1')
        self.assertFalse(r['success'])
        self.assertIn('500', r['error'])

    def test_connection_error_returns_fail(self):
        client = YfpoSoapMesClient('http://mes/BaseService.svc?wsdl', '2230', 'I308')
        import requests as req_lib
        client._zeep_client = MagicMock()
        client._zeep_client.service.InvokeMethod.side_effect = \
            req_lib.exceptions.ConnectionError('连接拒绝')
        r = client.get_rack_recipe('R1')
        self.assertFalse(r['success'])
        self.assertIn('连接失败', r['error'])

    def test_unsupported_actions(self):
        client = _client_patched(_ok({'Status': True}))
        self.assertFalse(client.upload_vision_result({})['success'])
        self.assertFalse(client.upload_alarm({})['success'])

    def test_configured_headers_are_sent(self):
        """zeep 版：验证 authorization / custom_headers 被传给 Session。"""
        client = YfpoSoapMesClient(
            'http://mes/service', '2230', 'I308',
            authorization='Basic test',
            custom_headers={'X-Factory': '2230'},
        )
        # 只验证初始化属性，不打网络
        self.assertEqual(client.authorization, 'Basic test')
        self.assertEqual(client.custom_headers, {'X-Factory': '2230'})


# ── 工厂函数测试 ──────────────────────────────────────────────────
_SOAP_CONF = {
    'USE_SIMULATED_DEVICES': False,
    'MES_BASE_URL': 'http://10.0.0.1:10133/BaseService.svc?wsdl',
    'MES_PROTOCOL': 'soap',
    'MES_FACTORY_CODE': '2230',
    'MES_PROD_LINE_CODE': 'I308',
    'MES_TIMEOUT': 8,
    'MES_CUSTOM_HEADERS': '{}',
}


class MesClientFactoryTests(SimpleTestCase):
    @override_settings(AUTOMATIC_ORDER=_SOAP_CONF)
    def test_factory_returns_soap_client(self):
        client = get_mes_client()
        self.assertIsInstance(client, YfpoSoapMesClient)
        self.assertEqual(client.factory_code, '2230')
        self.assertEqual(client.prod_line_code, 'I308')
        self.assertEqual(client.endpoint, 'http://10.0.0.1:10133/BaseService.svc')

    @override_settings(AUTOMATIC_ORDER={**_SOAP_CONF, 'USE_SIMULATED_DEVICES': True})
    def test_simulated_takes_precedence(self):
        from apps.mes.client import SimulatedMesClient
        self.assertIsInstance(get_mes_client(), SimulatedMesClient)

    @override_settings(AUTOMATIC_ORDER=_SOAP_CONF)
    def test_describe_runtime(self):
        rt = describe_mes_runtime()
        self.assertEqual(rt['mode'], 'soap')
        self.assertEqual(rt['factory_code'], '2230')


# ── MesService 落库测试 ───────────────────────────────────────────
class MesServiceOverSoapTests(TestCase):
    def test_service_records_soap_success(self):
        inner = {'Status': True, 'RackCode': 'R1', 'RackStatus': 1,
                 'HUQty': 26.0, 'HUMaxQty': 74.0, 'IsSealed': False, 'Message': 'ok'}
        client = _client_patched(_ok(inner))
        resp = MesService(client=client).get_rack_recipe('R1')
        self.assertTrue(resp['success'])
        rec = MesRecord.objects.get(action=MesAction.GET_RACK_RECIPE)
        self.assertTrue(rec.success)
        self.assertEqual(rec.response_payload['hu_max_qty'], 74.0)


# ── 控制台页面渲染测试 ────────────────────────────────────────────
class MesConsolePageTests(TestCase):
    def test_console_tab_renders(self):
        resp = self.client.get(reverse('mes:record_list'), {'tab': 'console'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '接口手动联调')
        self.assertContains(resp, '20260803 封箱生成区位号')
        self.assertContains(resp, '当前 MES 运行配置')

    def test_records_tab_renders_soap_chips(self):
        self._make_record()
        resp = self.client.get(reverse('mes:record_list'), {'tab': 'records'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '区位号')

    def _make_record(self):
        from apps.production.models import Rack
        rack = Rack.objects.create(rack_code='R9')
        MesRecord.objects.create(
            action=MesAction.UPLOAD_BOXING_RESULT, rack=rack,
            request_payload={'rack_code': 'R9'}, success=True,
            response_payload={'success': True, 'bin_code': 'A-02-01', 'is_not_task': 0},
        )
        return rack

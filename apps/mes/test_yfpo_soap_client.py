# -*- coding: utf-8 -*-
"""YFPO SOAP 客户端、工厂选择与 MesService 落库测试：注入假 session，不打真实网络。"""
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.constants import MesAction
from apps.mes.models import MesRecord
from apps.mes.services import MesService, get_mes_client, describe_mes_runtime
from apps.mes.yfpo_soap_client import YfpoSoapMesClient


class _Resp:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, xml):
        self.xml = xml
        self.sent = None
    def post(self, url, data=None, headers=None, timeout=None):
        self.headers = headers
        self.sent = data.decode('utf-8')
        return _Resp(self.xml)


def _soap(data, code='20260801', status='200'):
    return (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        '<InvokeMethodResponse xmlns="http://tempuri.org/"><InvokeMethodResult '
        'xmlns:a="http://schemas.datacontract.org/2004/07/YFPO.MES.Models.IF">'
        f'<a:Code>{code}</a:Code><a:Data>{data}</a:Data>'
        f'<a:ErrMsg/><a:Status>{status}</a:Status>'
        '</InvokeMethodResult></InvokeMethodResponse></s:Body></s:Envelope>'
    )


def _client(xml):
    session = _Session(xml)
    client = YfpoSoapMesClient(
        'http://mes/BaseService.svc?wsdl', '2230', 'I308', session=session,
    )
    return client, session


class YfpoSoapClientSimpleTests(SimpleTestCase):
    def test_configured_headers_are_sent(self):
        session = _Session(_soap('{"Status":true}', code='20260803'))
        client = YfpoSoapMesClient('http://mes/service', '2230', 'I308',
            soap_action='urn:test:InvokeMethod', authorization='Basic test',
            custom_headers={'X-Factory': '2230'}, session=session)
        client.upload_boxing_result({'rack_code': 'R1'})
        self.assertEqual(session.headers, {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': '"urn:test:InvokeMethod"',
            'Authorization': 'Basic test', 'X-Factory': '2230'})

    def test_non_available_racks_are_rejected(self):
        for value in (0, 2, 9, 3, None):
            import json
            with self.subTest(status=value):
                client, _ = _client(_soap(json.dumps({
                    'Status': True, 'RackStatus': value, 'IsSealed': False})))
                result = client.get_rack_recipe('R1')
                self.assertFalse(result['success'])
                self.assertIn('禁止装箱', result['error'])

    def test_no_pull_task_can_still_be_sealed_successfully(self):
        client, _ = _client(_soap('{"Status":true,"BinCode":"","IsNotTask":1}', code='20260803'))
        result = client.upload_boxing_result({'rack_code': 'R1'})
        self.assertTrue(result['success'])
        self.assertEqual(result['pull_task_label'], '无拉动任务')
        self.assertEqual(result['bin_code'], '')

    def test_check_ready_success(self):
        xml = _soap('{"Status":true,"RackCode":"R1","RackStatus":1,'
                    '"HUQty":26.00000000,"HUMaxQty":74.00000000,"IsSealed":false,"Message":"ok"}')
        client, session = _client(xml)
        r = client.get_rack_recipe('R1')
        self.assertTrue(r['success'])
        self.assertEqual(r['hu_qty'], 26.0)
        self.assertEqual(r['hu_max_qty'], 74.0)
        self.assertFalse(r['is_sealed'])
        self.assertNotIn('recipe', r)  # 20260801 不回配方，不得伪造
        self.assertIn('<yfpo:Code>20260801</yfpo:Code>', session.sent)
        self.assertIn('"ProdLineCode":"I308"', session.sent)
        self.assertEqual(client.endpoint, 'http://mes/BaseService.svc')

    def test_bind_success_returns_part_no(self):
        xml = _soap('{"Status":true,"Barcode":"B1","PartNo":"12441620",'
                    '"HUQty":1,"HUMaxQty":74,"IsFull":false,"Message":"绑定成功"}', code='20260802')
        client, session = _client(xml)
        r = client.upload_product_barcode('B1', 'R1')
        self.assertTrue(r['success'])
        self.assertEqual(r['part_no'], '12441620')
        self.assertFalse(r['is_full'])
        self.assertIn('"Barcode":"B1"', session.sent)

    def test_seal_success_returns_bin_code(self):
        xml = _soap('{"Status":true,"BinCode":"A-01-03","IsNotTask":0,'
                    '"TaskGuid":"g1","Message":"封箱成功"}', code='20260803')
        client, _ = _client(xml)
        r = client.upload_boxing_result({'rack_code': 'R1'})
        self.assertTrue(r['success'])
        self.assertEqual(r['bin_code'], 'A-01-03')

    def test_inner_status_false_is_business_rejection(self):
        client, _ = _client(_soap('{"Status":false,"IsSealed":true,"Message":"料架已封箱，禁止装箱"}'))
        r = client.get_rack_recipe('R1')
        self.assertFalse(r['success'])
        self.assertTrue(r['business'])
        self.assertIn('已封箱', r['error'])

    def test_outer_500_is_failure(self):
        client, _ = _client(_soap('{"Status":true}', status='500'))
        r = client.get_rack_recipe('R1')
        self.assertFalse(r['success'])
        self.assertIn('500', r['error'])

    def test_malformed_xml_never_raises(self):
        class Bad:
            def post(self, *a, **k):
                return _Resp('<not-xml')
        client = YfpoSoapMesClient('http://x/BaseService.svc', '2230', 'I308', session=Bad())
        r = client.get_rack_recipe('R1')
        self.assertFalse(r['success'])

    def test_unsupported_actions(self):
        client, _ = _client(_soap('{}'))
        self.assertFalse(client.upload_vision_result({})['success'])
        self.assertFalse(client.upload_alarm({})['success'])


_SOAP_CONF = {
    'USE_SIMULATED_DEVICES': False,
    'MES_BASE_URL': 'http://10.0.0.1:10133/BaseService.svc?wsdl',
    'MES_PROTOCOL': 'soap',
    'MES_FACTORY_CODE': '2230',
    'MES_PROD_LINE_CODE': 'I308',
    'MES_TIMEOUT': 8,
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


class MesServiceOverSoapTests(TestCase):
    def test_service_records_soap_success(self):
        client, _ = _client(_soap(
            '{"Status":true,"RackCode":"R1","RackStatus":1,"HUQty":26.0,'
            '"HUMaxQty":74.0,"IsSealed":false,"Message":"ok"}'))
        resp = MesService(client=client).get_rack_recipe('R1')
        self.assertTrue(resp['success'])
        rec = MesRecord.objects.get(action=MesAction.GET_RACK_RECIPE)
        self.assertTrue(rec.success)
        self.assertEqual(rec.response_payload['hu_max_qty'], 74.0)


class MesConsolePageTests(TestCase):
    def test_console_tab_renders(self):
        resp = self.client.get(reverse('mes:record_list'), {'tab': 'console'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '接口手动联调')
        self.assertContains(resp, '20260803 封箱生成区位号')
        self.assertContains(resp, '当前 MES 运行配置')

    def test_records_tab_renders_soap_chips(self):
        rack = self._make_record()
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

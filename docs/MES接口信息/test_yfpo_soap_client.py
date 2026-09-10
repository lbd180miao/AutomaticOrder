# -*- coding: utf-8 -*-
"""YFPO SOAP 客户端测试：注入假 session，不打真实网络。
放到 apps/mes/test_yfpo_soap_client.py，随 `python manage.py test apps.mes` 一起跑。
"""
from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.constants import MesAction
from apps.mes.models import MesRecord
from apps.mes.services import MesService
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
    def test_check_ready_success(self):
        xml = _soap('{"Status":true,"RackCode":"R1","RackStatus":1,'
                    '"HUQty":26.00000000,"HUMaxQty":74.00000000,"IsSealed":false,'
                    '"Message":"ok"}')
        client, session = _client(xml)
        r = client.get_rack_recipe('R1')
        self.assertTrue(r['success'])
        self.assertEqual(r['hu_qty'], 26.0)
        self.assertEqual(r['hu_max_qty'], 74.0)
        self.assertFalse(r['is_sealed'])
        self.assertNotIn('recipe', r)  # 20260801 不回配方，不得伪造
        self.assertIn('<yfpo:Code>20260801</yfpo:Code>', session.sent)
        self.assertIn('"ProdLineCode":"I308"', session.sent)
        self.assertEqual(client.endpoint, 'http://mes/BaseService.svc')  # 去掉 ?wsdl

    def test_bind_success_returns_part_no(self):
        xml = _soap('{"Status":true,"Barcode":"B1","PartNo":"12441620",'
                    '"HUQty":1,"HUMaxQty":74,"IsFull":false,"Message":"绑定成功"}',
                    code='20260802')
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
        self.assertEqual(r['is_not_task'], 0)

    def test_inner_status_false_is_business_rejection(self):
        xml = _soap('{"Status":false,"IsSealed":true,"Message":"料架已封箱，禁止装箱"}')
        client, _ = _client(xml)
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


class MesServiceOverSoapTests(TestCase):
    """真实 SOAP 客户端可被 MesService 直接包裹，落库/重传链路不变。"""
    def test_service_records_soap_success(self):
        xml = _soap('{"Status":true,"RackCode":"R1","RackStatus":1,'
                    '"HUQty":26.0,"HUMaxQty":74.0,"IsSealed":false,"Message":"ok"}')
        client, _ = _client(xml)
        resp = MesService(client=client).get_rack_recipe('R1')
        self.assertTrue(resp['success'])
        rec = MesRecord.objects.get(action=MesAction.GET_RACK_RECIPE)
        self.assertTrue(rec.success)
        self.assertEqual(rec.response_payload['hu_max_qty'], 74.0)

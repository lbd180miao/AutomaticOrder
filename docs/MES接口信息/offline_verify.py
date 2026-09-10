# -*- coding: utf-8 -*-
"""离线验证：不依赖 Django/网络，stub 掉 apps.mes.client 后按文件路径加载真实模块，
用甲方原始示例回执 + 假 session 跑全部断言。用项目 venv 运行：
  .venv\\Scripts\\python.exe offline_verify.py
"""
import sys, os, types, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))

# stub 包层级，避免 import apps.mes.client 触发 Django
for name in ('apps', 'apps.mes'):
    m = types.ModuleType(name); m.__path__ = []
    sys.modules[name] = m
client_stub = types.ModuleType('apps.mes.client')
class MesClient:  # 与真实基类同名的最小占位
    pass
client_stub.MesClient = MesClient
sys.modules['apps.mes.client'] = client_stub

spec = importlib.util.spec_from_file_location(
    'apps.mes.yfpo_soap_client', os.path.join(HERE, 'yfpo_soap_client.py'))
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

YfpoSoapMesClient = mod.YfpoSoapMesClient
build_envelope = mod.build_envelope


class FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200
    def raise_for_status(self):
        pass


class FakeSession:
    """按业务代码返回预置 XML，并记录最近一次请求。"""
    def __init__(self, by_code):
        self.by_code = by_code
        self.last = None
    def post(self, url, data=None, headers=None, timeout=None):
        text = data.decode('utf-8')
        code = text.split('<yfpo:Code>')[1].split('</yfpo:Code>')[0]
        self.last = {'url': url, 'body': text, 'headers': headers}
        return FakeResp(self.by_code[code])


def wrap(code, data, status='200'):
    return ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            '<InvokeMethodResponse xmlns="http://tempuri.org/"><InvokeMethodResult '
            'xmlns:a="http://schemas.datacontract.org/2004/07/YFPO.MES.Models.IF">'
            f'<a:Code>{code}</a:Code><a:Data>{data}</a:Data>'
            f'<a:ErrMsg/><a:Status>{status}</a:Status>'
            '</InvokeMethodResult></InvokeMethodResponse></s:Body></s:Envelope>')


S1 = wrap('20260801', '{"Status":true,"FactoryCode":"2230","ProdLineCode":"I308","RackCode":"INN0117G00","RackStatus":1,"HUQty":26.00000000,"HUMaxQty":74.00000000,"IsSealed":false,"Message":"料架校验通过，可开始装箱"}')
S2 = wrap('20260802', '{"Status":true,"FactoryCode":"2230","ProdLineCode":"I308","RackCode":"INN0117G00","Barcode":"LG260624130024","PartNo":"12441620","HUQty":26.00000000,"HUMaxQty":74.00000000,"IsFull":false,"Message":"绑定成功"}')
S3 = wrap('20260803', '{"Status":true,"FactoryCode":"2230","ProdLineCode":"I308","RackCode":"INN0117G00","BinCode":"","IsNotTask":1,"TaskGuid":"","Message":"封箱成功，暂无可用区位号"}')


def main():
    # 信封
    env = build_envelope('20260801', {'FactoryCode': '2230', 'ProdLineCode': 'I308', 'RackCode': 'INN0117G00'}, '2230')
    assert '<yfpo:Code>20260801</yfpo:Code>' in env
    assert '"RackCode":"INN0117G00"' in env
    print('[1] 信封拼装 OK')

    session = FakeSession({'20260801': S1, '20260802': S2, '20260803': S3})
    c = YfpoSoapMesClient('http://localhost:10133/BaseService.svc?wsdl', '2230', 'I308', session=session)
    assert c.endpoint == 'http://localhost:10133/BaseService.svc', '运行时地址必须去掉 ?wsdl'

    r1 = c.get_rack_recipe('INN0117G00')
    assert r1['success'] and r1['hu_qty'] == 26.0 and r1['hu_max_qty'] == 74.0
    assert r1['is_sealed'] is False and r1['rack_status'] == 1
    assert 'recipe' not in r1, '20260801 不返回配方，不能伪造 recipe 键'
    assert session.last['headers']['Content-Type'].startswith('text/xml')
    assert session.last['headers']['SOAPAction'] == '""'
    print('[2] 20260801 校验 OK ->', {k: r1[k] for k in ('success', 'hu_qty', 'hu_max_qty', 'is_sealed')})

    r2 = c.upload_product_barcode('LG260624130024', 'INN0117G00')
    assert r2['success'] and r2['part_no'] == '12441620' and r2['is_full'] is False
    assert '"Barcode":"LG260624130024"' in session.last['body']
    print('[3] 20260802 绑定 OK -> part_no =', r2['part_no'])

    r3 = c.upload_boxing_result({'rack_code': 'INN0117G00'})
    assert r3['success'] and r3['bin_code'] == '' and r3['is_not_task'] == 1
    print('[4] 20260803 封箱 OK -> bin_code =', repr(r3['bin_code']), 'is_not_task =', r3['is_not_task'])

    # 业务拒绝：外层200，内层 Status=false
    sf = FakeSession({'20260801': wrap('20260801', '{"Status":false,"IsSealed":true,"Message":"料架已封箱，禁止装箱"}')})
    cf = YfpoSoapMesClient('http://x/BaseService.svc', '2230', 'I308', session=sf)
    rf = cf.get_rack_recipe('R1')
    assert rf['success'] is False and rf.get('business') is True and '已封箱' in rf['error']
    print('[5] 业务拒绝 OK ->', rf['error'])

    # 外层 500
    sf2 = FakeSession({'20260801': wrap('20260801', '{"Status":true}', status='500')})
    cf2 = YfpoSoapMesClient('http://x/BaseService.svc', '2230', 'I308', session=sf2)
    rf2 = cf2.get_rack_recipe('R1')
    assert rf2['success'] is False and '500' in rf2['error']
    print('[6] 外层 500 OK ->', rf2['error'][:40])

    # 坏 XML 不抛异常，回错误字典
    class BadSession:
        def post(self, *a, **k): return FakeResp('<not-xml')
    rb = YfpoSoapMesClient('http://x/BaseService.svc', '2230', 'I308', session=BadSession()).get_rack_recipe('R1')
    assert rb['success'] is False and 'XML' in rb['error']
    print('[7] 坏 XML 安全兜底 OK')

    # 未提供的动作
    assert c.upload_vision_result({})['success'] is False
    assert c.upload_alarm({})['success'] is False
    print('[8] 未提供动作安全返回 OK')

    print('\n全部离线断言通过 ✅')


if __name__ == '__main__':
    main()

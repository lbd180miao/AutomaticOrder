# -*- coding: utf-8 -*-
"""
延锋 YFPO MES —— SOAP(WCF / InvokeMethod) 客户端，实现本项目的 MesClient 接口。

为什么是新增一个客户端实现、而不是另起一套：
- apps/mes/client.py 里已有抽象基类 MesClient，以及 REST 版 HttpMesClient、
  模拟版 SimulatedMesClient；MesService 只依赖 MesClient 的统一返回契约
  （成功 {'success': True, ...}，失败 {'success': False, 'error': '...'}，不抛异常）。
- 本类就是第三种实现：YfpoSoapMesClient。放进 get_mes_client() 工厂后，
  MesService 的 MesRecord 落库、失败重传(run_mes_retry)、统计全部原样复用。

甲方三个接口共用同一个 WCF 端点 BaseService.svc 的 InvokeMethod，
仅业务代码 Code 与 Data(JSON 字符串) 不同，正好对应现有三个动作：
  20260801 CheckIMMRackReadyToPkg 注塑料架待装箱校验 -> get_rack_recipe        (GET_RACK_RECIPE)
  20260802 BindIMMBarcodeToRK     注塑条码绑定 RK     -> upload_product_barcode (UPLOAD_PRODUCT_BARCODE)
  20260803 SealIMMRKAndGenBin     注塑封箱生成区位号   -> upload_boxing_result   (UPLOAD_BOXING_RESULT)
  upload_vision_result / upload_alarm 在这份 WCF 契约里没有对应接口，返回明确的不支持字典。

依赖 requests（已在 requirements.txt）；传输会话可注入，便于单测打桩、不打真实网络。
"""
from __future__ import annotations

import json
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.sax.saxutils import escape

from .client import MesClient

logger = logging.getLogger(__name__)

# 业务代码（来自甲方《注塑封箱测试用例.xlsx》）
CODE_CHECK_RACK_READY = '20260801'   # 待装箱校验
CODE_BIND_BARCODE = '20260802'      # 条码绑定料架
CODE_SEAL_GEN_BIN = '20260803'      # 封箱生成区位号
RACK_STATUS_LABELS = {1: '可用', 0: '禁用', 2: '隔离', 9: '不可用'}

# 固定 SOAP 1.1 信封；Id 与 TaskId 用同一个 GUID，与甲方示例一致
_ENVELOPE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/" xmlns:yfpo="http://schemas.datacontract.org/2004/07/YFPO.MES.Models.IF">
  <soapenv:Header/>
  <soapenv:Body>
    <tem:InvokeMethod>
      <tem:message>
        <yfpo:Code>{code}</yfpo:Code>
        <yfpo:Data>{data}</yfpo:Data>
        <yfpo:ErrMsg></yfpo:ErrMsg>
        <yfpo:FactoryCode>{factory}</yfpo:FactoryCode>
        <yfpo:Id>{guid}</yfpo:Id>
        <yfpo:RT>1</yfpo:RT>
        <yfpo:Sender>1</yfpo:Sender>
        <yfpo:SenderUrl>?</yfpo:SenderUrl>
        <yfpo:Status>1</yfpo:Status>
        <yfpo:TaskId>{guid}</yfpo:TaskId>
        <yfpo:TelId>1</yfpo:TelId>
        <yfpo:TimeStamp>{date}</yfpo:TimeStamp>
        <yfpo:Timestamp>{date}</yfpo:Timestamp>
      </tem:message>
    </tem:InvokeMethod>
  </soapenv:Body>
</soapenv:Envelope>"""


def build_envelope(code: str, data_obj: dict, factory_code: str) -> str:
    """组装 SOAP 信封；Data 是紧凑 JSON 字符串并做 XML 转义。"""
    data_json = json.dumps(data_obj, ensure_ascii=False, separators=(',', ':'))
    return _ENVELOPE.format(
        code=escape(str(code)),
        data=escape(data_json),
        factory=escape(str(factory_code)),
        guid=str(uuid.uuid4()).upper(),
        date=datetime.now().strftime('%Y-%m-%d'),
    )


def _localname(tag: str) -> str:
    """去掉 XML 命名空间前缀，兼容 s:/a:/默认命名空间三种写法。"""
    return tag.split('}', 1)[-1]


def parse_soap_response(xml_text: str) -> dict:
    """
    解析 InvokeMethodResponse：
      {'outer_status': int|None, 'code': str, 'err_msg': str, 'data': dict}
    外层 <a:Status>200</a:Status> 是 WCF 包装层状态；
    内层 data['Status'](bool) 才是业务成功与否。
    XML/Data 非法时抛 ValueError，由上层统一转成 {'success': False, ...}。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f'MES 返回不是合法 XML: {exc}') from exc

    nodes = {_localname(el.tag): el for el in root.iter()}
    if 'InvokeMethodResult' not in nodes:
        raise ValueError('MES 返回缺少 InvokeMethodResult 节点')

    def _text(name: str) -> str:
        node = nodes.get(name)
        return (node.text or '').strip() if node is not None else ''

    raw_status = _text('Status')
    try:
        outer_status = int(raw_status) if raw_status else None
    except ValueError:
        outer_status = None

    raw_data = _text('Data')
    data = json.loads(raw_data) if raw_data else {}
    return {'outer_status': outer_status, 'code': _text('Code'),
            'err_msg': _text('ErrMsg'), 'data': data}


class YfpoSoapMesClient(MesClient):
    """对接 YFPO MES BaseService.svc 的真实 SOAP 客户端。"""

    def __init__(self, base_url: str, factory_code: str, prod_line_code: str, *,
                 timeout: int = 8, soap_action: str = 'http://tempuri.org/IBaseService/InvokeMethod', content_type: str = 'text/xml; charset=utf-8',
                 authorization: str = '', custom_headers=None, session=None):
        # 运行时调用地址要去掉 ?wsdl（那只是取元数据/契约用的）
        self.endpoint = (base_url or '').split('?')[0]
        self.factory_code = factory_code
        self.prod_line_code = prod_line_code
        self.timeout = timeout
        # action 必须取自现场 InvokeMethod 契约，不能使用文档中的 GetData 示例。
        self.soap_action = soap_action
        self.content_type = content_type or 'text/xml; charset=utf-8'
        self.authorization = authorization or ''
        self.custom_headers = dict(custom_headers or {})
        self._session = session

    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    # ── 统一调用：发信封 -> 解析 -> 两层成功判定，全程不抛异常 ──────────
    def _invoke(self, code: str, biz_data: dict) -> dict:
        payload = {'FactoryCode': self.factory_code,
                   'ProdLineCode': self.prod_line_code}
        payload.update(biz_data or {})
        envelope = build_envelope(code, payload, self.factory_code)

        try:
            import requests
            headers = {'Content-Type': self.content_type}
            if self.soap_action:
                headers['SOAPAction'] = f'"{self.soap_action}"'
            if self.authorization:
                headers['Authorization'] = self.authorization
            headers.update({str(k): str(v) for k, v in self.custom_headers.items()})
            resp = self._get_session().post(
                self.endpoint,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            parsed = parse_soap_response(resp.text)
        except requests.exceptions.ConnectionError as exc:
            logger.error('[MES-SOAP] 连接失败 code=%s: %s', code, exc)
            return {'success': False, 'error': f'MES 连接失败: {exc}'}
        except requests.exceptions.Timeout:
            logger.error('[MES-SOAP] 请求超时 code=%s (%ss)', code, self.timeout)
            return {'success': False, 'error': f'MES 请求超时 ({self.timeout}s)'}
        except requests.exceptions.HTTPError as exc:
            logger.error('[MES-SOAP] HTTP 错误 code=%s: %s', code, exc)
            return {'success': False, 'error': f'MES HTTP 错误: {exc}'}
        except ValueError as exc:
            logger.error('[MES-SOAP] 报文解析失败 code=%s: %s', code, exc)
            return {'success': False, 'error': f'MES 报文解析失败: {exc}'}

        # 外层非 200：WCF 包装层/系统级失败
        outer = parsed.get('outer_status')
        if outer != 200:
            return {'success': False,
                    'error': f'MES 外层状态={outer} {parsed.get("err_msg", "")}'.strip(),
                    'mes_data': parsed.get('data', {})}

        inner = parsed.get('data', {}) or {}
        if not bool(inner.get('Status', False)):
            # 业务拒绝（如料架已封箱/不满足装箱条件）
            return {'success': False, 'business': True,
                    'error': inner.get('Message') or parsed.get('err_msg') or 'MES 业务校验未通过',
                    'mes_data': inner}
        return {'success': True, 'mes_data': inner,
                'message': inner.get('Message', '')}

    # ── 20260801 待装箱校验（对齐 get_rack_recipe）────────────────────
    def get_rack_recipe(self, rack_code: str) -> dict:
        result = self._invoke(CODE_CHECK_RACK_READY, {'RackCode': rack_code})
        if not result.get('success'):
            return result
        inner = result['mes_data']
        rack_status = inner.get('RackStatus')
        status_label = RACK_STATUS_LABELS.get(rack_status, '未知')
        if rack_status != 1 or inner.get('IsSealed') is not False:
            reason = '料架已封箱或封箱状态缺失' if rack_status == 1 else f'料架状态为{status_label}（{rack_status}）'
            return {'success': False, 'business': True, 'error': f'{reason}，禁止装箱',
                    'rack_status': rack_status, 'rack_status_label': status_label,
                    'is_sealed': inner.get('IsSealed'), 'mes_data': inner}
        # 注意：20260801 只回“校验结果 + 当前/最大数量”，不回配方几何参数，
        # 因此这里【不】构造 'recipe'；配方请走本地 RackRecipe 或另一配方接口。
        return {
            'success': True,
            'rack_code': inner.get('RackCode', rack_code),
            'rack_status': rack_status,
            'rack_status_label': status_label,
            'hu_qty': inner.get('HUQty'),                                 # 当前已装数量
            'hu_max_qty': inner.get('HUMaxQty'),                          # 料架最大容量
            'is_sealed': bool(inner.get('IsSealed', False)),              # 是否已封箱
            'message': inner.get('Message', ''),
            'mes_data': inner,
        }

    # ── 20260802 条码绑定料架（对齐 upload_product_barcode）───────────
    def upload_product_barcode(self, product_code: str, rack_code: str) -> dict:
        result = self._invoke(
            CODE_BIND_BARCODE, {'RackCode': rack_code, 'Barcode': product_code},
        )
        if not result.get('success'):
            return result
        inner = result['mes_data']
        return {
            'success': True,
            'product_code': product_code,
            'rack_code': inner.get('RackCode', rack_code),
            'barcode': inner.get('Barcode', product_code),
            'part_no': inner.get('PartNo'),                               # 零件号/物料号
            'hu_qty': inner.get('HUQty'),
            'hu_max_qty': inner.get('HUMaxQty'),
            'is_full': bool(inner.get('IsFull', False)),                  # 料架是否已装满
            'message': inner.get('Message', ''),
            'mes_data': inner,
        }

    # ── 20260803 封箱并生成区位号（对齐 upload_boxing_result）─────────
    def upload_boxing_result(self, payload: dict) -> dict:
        payload = payload or {}
        rack_code = payload.get('rack_code', '')
        result = self._invoke(CODE_SEAL_GEN_BIN, {'RackCode': rack_code})
        if not result.get('success'):
            return result
        inner = result['mes_data']
        return {
            'success': True,
            'rack_code': inner.get('RackCode', rack_code),
            'bin_code': inner.get('BinCode', ''),                         # 区位号，可能为空串
            'is_not_task': inner.get('IsNotTask'),                        # 0=有拉动任务，1=无拉动任务
            'pull_task_label': {0: '有拉动任务', 1: '无拉动任务'}.get(inner.get('IsNotTask'), '未知'),
            'task_guid': inner.get('TaskGuid', ''),
            'message': inner.get('Message', ''),
            'mes_data': inner,
        }

    # ── 本份 WCF 契约未提供的动作：明确返回不支持，避免静默成功 ────────
    def upload_vision_result(self, payload: dict) -> dict:
        return {'success': False, 'error': 'YFPO SOAP 契约未提供视觉结果上传接口'}

    def upload_alarm(self, payload: dict) -> dict:
        return {'success': False, 'error': 'YFPO SOAP 契约未提供报警上传接口'}

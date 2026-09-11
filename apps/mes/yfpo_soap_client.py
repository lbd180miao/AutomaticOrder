# -*- coding: utf-8 -*-
"""
延锋 YFPO MES —— 基于 zeep 的 SOAP(WCF / InvokeMethod) 客户端。

为什么改用 zeep：
- zeep 和 SoapUI 原理完全相同：启动时加载 WSDL，自动解析真实 SOAPAction、
  命名空间、字段类型，不需要手写 XML 模板，不会出现 SOAPAction 不匹配的问题。
- 旧方案手写 XML 模板，SOAPAction 写死 "IBaseService/InvokeMethod"，
  与 WCF 服务实际注册的 Action 不一致，导致 ContractFilter 匹配失败 → HTTP 500。

甲方三个接口共用同一个 WCF 端点 BaseService.svc 的 InvokeMethod：
  20260801  CheckIMMRackReadyToPkg  注塑料架待装箱校验  -> get_rack_recipe
  20260802  BindIMMBarcodeToRK      注塑条码绑定 RK     -> upload_product_barcode
  20260803  SealIMMRKAndGenBin      注塑封箱生成区位号  -> upload_boxing_result
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from .client import MesClient

logger = logging.getLogger(__name__)

# 业务代码
CODE_CHECK_RACK_READY = '20260801'
CODE_BIND_BARCODE     = '20260802'
CODE_SEAL_GEN_BIN     = '20260803'
RACK_STATUS_LABELS    = {1: '可用', 0: '禁用', 2: '隔离', 9: '不可用'}


def _make_zeep_client(wsdl_url: str, timeout: int = 8,
                      authorization: str = '', custom_headers: dict | None = None):
    """
    创建 zeep Client：
    - zeep 自动从 WSDL 读取正确的 SOAPAction，不用手填。
    - Transport 注入 requests.Session，支持自定义 header / 超时。
    """
    import requests as req_lib
    from zeep import Client, Settings
    from zeep.transports import Transport

    session = req_lib.Session()
    # Content-Type 由 zeep 自动设置为 text/xml; charset=utf-8
    if authorization:
        session.headers['Authorization'] = authorization
    if custom_headers:
        session.headers.update({str(k): str(v) for k, v in custom_headers.items()})

    transport = Transport(session=session, timeout=timeout)
    settings  = Settings(strict=False, xml_huge_tree=True)
    return Client(wsdl_url, transport=transport, settings=settings)


class YfpoSoapMesClient(MesClient):
    """对接 YFPO MES BaseService.svc 的 zeep SOAP 客户端。"""

    def __init__(self, base_url: str, factory_code: str, prod_line_code: str, *,
                 timeout: int = 8,
                 soap_action: str = '',          # zeep 自动读 WSDL，此参数保留但不使用
                 content_type: str = '',         # zeep 自动设置，此参数保留但不使用
                 authorization: str = '',
                 custom_headers=None,
                 session=None):                  # session 参数保留兼容旧接口，zeep 内部管理
        # WSDL 地址保留 ?wsdl 供 zeep 加载；运行时端点 zeep 从 WSDL 自动读
        self.wsdl_url       = base_url if '?' in base_url else base_url + '?wsdl'
        self.endpoint       = base_url.split('?')[0]  # 供日志显示
        self.factory_code   = factory_code
        self.prod_line_code = prod_line_code
        self.timeout        = timeout
        self.authorization  = authorization or ''
        self.custom_headers = dict(custom_headers or {})
        self._zeep_client   = None              # 懒加载，首次调用时初始化

    def _get_client(self):
        """懒加载 zeep Client（WSDL 只解析一次）。"""
        if self._zeep_client is None:
            logger.warning('[MES-SOAP] 正在加载 WSDL: %s', self.wsdl_url)
            self._zeep_client = _make_zeep_client(
                self.wsdl_url, self.timeout,
                self.authorization, self.custom_headers,
            )
            logger.warning('[MES-SOAP] WSDL 加载完成，endpoint: %s', self.endpoint)
        return self._zeep_client

    # ── 统一调用 ──────────────────────────────────────────────────────
    def _invoke(self, code: str, biz_data: dict) -> dict:
        payload = {'FactoryCode': self.factory_code,
                   'ProdLineCode': self.prod_line_code}
        payload.update(biz_data or {})

        guid     = str(uuid.uuid4()).upper()
        now      = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        data_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))

        # zeep 参数字典 —— 字段名与类型完全按 WSDL 签名：
        # Code:xsd:int, Data:xsd:string, ErrMsg:xsd:string, FactoryCode:xsd:string,
        # Id:guid, RT:xsd:int, Sender:xsd:string, SenderUrl:xsd:string,
        # Status:xsd:short, TaskId:xsd:string, TelId:xsd:int,   ← 单 l
        # TimeStamp:xsd:string, Timestamp:xsd:dateTime           ← 需要 datetime 对象
        message_params = {
            'Code':        int(code),      # xsd:int，不能传字符串
            'Data':        data_json,      # xsd:string
            'ErrMsg':      '',             # xsd:string
            'FactoryCode': self.factory_code,
            'Id':          guid,           # guid
            'RT':          1,              # xsd:int
            'Sender':      '1',            # xsd:string
            'SenderUrl':   '?',            # xsd:string
            'Status':      1,              # xsd:short
            'TaskId':      guid,           # xsd:string
            'TelId':       1,              # xsd:int，单 l（WSDL 确认）
            'TimeStamp':   date_str,       # xsd:string，日期字符串
            'Timestamp':   now,            # xsd:dateTime，datetime 对象
        }

        logger.warning('[MES-SOAP] >>> 发送请求 code=%s endpoint=%s data=%s',
                       code, self.endpoint, data_json)
        try:
            client   = self._get_client()
            response = client.service.InvokeMethod(message=message_params)
            logger.warning('[MES-SOAP] <<< 原始响应: %s', response)
        except Exception as exc:
            import requests as req_lib
            # 网络/超时/连接错误
            if isinstance(exc, req_lib.exceptions.ConnectionError):
                logger.error('[MES-SOAP] 连接失败 code=%s: %s', code, exc)
                return {'success': False, 'error': f'MES 连接失败: {exc}'}
            if isinstance(exc, req_lib.exceptions.Timeout):
                logger.error('[MES-SOAP] 超时 code=%s (%ss)', code, self.timeout)
                return {'success': False, 'error': f'MES 请求超时 ({self.timeout}s)'}
            # zeep 解析错误 / WCF Fault（含 500）
            logger.error('[MES-SOAP] 调用异常 code=%s: %s', code, exc)
            return {'success': False, 'error': f'MES 调用失败: {exc}'}

        # ── 解析 zeep 返回对象 ──────────────────────────────────────
        # zeep 把 WCF 响应反序列化为 Python 对象（类似 SimpleNamespace）
        try:
            outer_status = int(getattr(response, 'Status', 0) or 0)
            raw_data     = getattr(response, 'Data', '') or ''
            err_msg      = getattr(response, 'ErrMsg', '') or ''
        except Exception as exc:
            logger.error('[MES-SOAP] 响应字段解析失败: %s', exc)
            return {'success': False, 'error': f'MES 响应解析失败: {exc}'}

        logger.warning('[MES-SOAP] outer_status=%s err_msg=%s data_raw=%s',
                       outer_status, err_msg, raw_data[:200])

        if outer_status != 200:
            return {'success': False,
                    'error': f'MES 外层状态={outer_status} {err_msg}'.strip(),
                    'mes_data': {}}

        try:
            inner = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError:
            inner = {}

        if not bool(inner.get('Status', False)):
            return {'success': False, 'business': True,
                    'error': inner.get('Message') or err_msg or 'MES 业务校验未通过',
                    'mes_data': inner}

        return {'success': True, 'mes_data': inner, 'message': inner.get('Message', '')}

    # ── 20260801 待装箱校验 ────────────────────────────────────────
    def get_rack_recipe(self, rack_code: str) -> dict:
        result = self._invoke(CODE_CHECK_RACK_READY, {'RackCode': rack_code})
        if not result.get('success'):
            return result
        inner        = result['mes_data']
        rack_status  = inner.get('RackStatus')
        status_label = RACK_STATUS_LABELS.get(rack_status, '未知')
        if rack_status != 1 or inner.get('IsSealed') is not False:
            reason = ('料架已封箱或封箱状态缺失' if rack_status == 1
                      else f'料架状态为{status_label}（{rack_status}）')
            return {'success': False, 'business': True,
                    'error': f'{reason}，禁止装箱',
                    'rack_status': rack_status, 'rack_status_label': status_label,
                    'is_sealed': inner.get('IsSealed'), 'mes_data': inner}
        return {
            'success': True,
            'rack_code':          inner.get('RackCode', rack_code),
            'rack_status':        rack_status,
            'rack_status_label':  status_label,
            'hu_qty':             inner.get('HUQty'),
            'hu_max_qty':         inner.get('HUMaxQty'),
            'is_sealed':          bool(inner.get('IsSealed', False)),
            'message':            inner.get('Message', ''),
            'mes_data':           inner,
        }

    # ── 20260802 条码绑定料架 ──────────────────────────────────────
    def upload_product_barcode(self, product_code: str, rack_code: str) -> dict:
        result = self._invoke(CODE_BIND_BARCODE,
                              {'RackCode': rack_code, 'Barcode': product_code})
        if not result.get('success'):
            return result
        inner = result['mes_data']
        return {
            'success':      True,
            'product_code': product_code,
            'rack_code':    inner.get('RackCode', rack_code),
            'barcode':      inner.get('Barcode', product_code),
            'part_no':      inner.get('PartNo'),
            'hu_qty':       inner.get('HUQty'),
            'hu_max_qty':   inner.get('HUMaxQty'),
            'is_full':      bool(inner.get('IsFull', False)),
            'message':      inner.get('Message', ''),
            'mes_data':     inner,
        }

    # ── 20260803 封箱生成区位号 ────────────────────────────────────
    def upload_boxing_result(self, payload: dict) -> dict:
        payload    = payload or {}
        rack_code  = payload.get('rack_code', '')
        result     = self._invoke(CODE_SEAL_GEN_BIN, {'RackCode': rack_code})
        if not result.get('success'):
            return result
        inner = result['mes_data']
        return {
            'success':          True,
            'rack_code':        inner.get('RackCode', rack_code),
            'bin_code':         inner.get('BinCode', ''),
            'is_not_task':      inner.get('IsNotTask'),
            'pull_task_label':  {0: '有拉动任务', 1: '无拉动任务'}.get(
                                    inner.get('IsNotTask'), '未知'),
            'task_guid':        inner.get('TaskGuid', ''),
            'message':          inner.get('Message', ''),
            'mes_data':         inner,
        }

    # ── 本份契约未提供的动作 ───────────────────────────────────────
    def upload_vision_result(self, payload: dict) -> dict:
        return {'success': False, 'error': 'YFPO SOAP 契约未提供视觉结果上传接口'}

    def upload_alarm(self, payload: dict) -> dict:
        return {'success': False, 'error': 'YFPO SOAP 契约未提供报警上传接口'}

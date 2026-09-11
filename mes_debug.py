#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MES SOAP 诊断脚本 —— 直接运行，不依赖 Django
用途：打印实际发出的 XML 报文 + 服务器返回的完整 500 响应体
运行：.venv\Scripts\python.exe mes_debug.py
"""
import json, uuid, requests
from xml.sax.saxutils import escape
from datetime import datetime

MES_URL     = 'http://10.252.6.51/MESService_LG/BaseService.svc'
FACTORY     = '2230'
PROD_LINE   = 'I308'
RACK_CODE   = 'INN0117G00'
SOAP_ACTION = 'http://tempuri.org/IBaseService/InvokeMethod'

ENVELOPE = (
    '<soapenv:Envelope'
    ' xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
    ' xmlns:tem="http://tempuri.org/"'
    ' xmlns:yfpo="http://schemas.datacontract.org/2004/07/YFPO.MES.Models.IF">'
    '<soapenv:Header/>'
    '<soapenv:Body>'
    '<tem:InvokeMethod>'
    '<tem:message>'
    '<yfpo:Code>{code}</yfpo:Code>'
    '<yfpo:Data>{data}</yfpo:Data>'
    '<yfpo:ErrMsg></yfpo:ErrMsg>'
    '<yfpo:FactoryCode>{factory}</yfpo:FactoryCode>'
    '<yfpo:Id>{guid}</yfpo:Id>'
    '<yfpo:RT>1</yfpo:RT>'
    '<yfpo:Sender>1</yfpo:Sender>'
    '<yfpo:SenderUrl></yfpo:SenderUrl>'
    '<yfpo:Status>1</yfpo:Status>'
    '<yfpo:TaskId>{guid}</yfpo:TaskId>'
    '<yfpo:TellId>1</yfpo:TellId>'
    '<yfpo:TimeStamp>{date}</yfpo:TimeStamp>'
    '<yfpo:Timestamp>{date}</yfpo:Timestamp>'
    '</tem:message>'
    '</tem:InvokeMethod>'
    '</soapenv:Body>'
    '</soapenv:Envelope>'
)

data_obj = {'FactoryCode': FACTORY, 'ProdLineCode': PROD_LINE, 'RackCode': RACK_CODE}
data_json = json.dumps(data_obj, ensure_ascii=False, separators=(',', ':'))
guid = str(uuid.uuid4()).upper()
date = datetime.now().strftime('%Y-%m-%d')

xml_body = ENVELOPE.format(
    code=escape('20260801'),
    data=escape(data_json),
    factory=escape(FACTORY),
    guid=guid,
    date=date,
)

headers = {
    'Content-Type': 'text/xml; charset=utf-8',
    'SOAPAction': '"' + SOAP_ACTION + '"',
}

print('=' * 70)
print('[发送的 XML 报文]')
print('=' * 70)
print(xml_body)
print()
print('[请求 Headers]')
for k, v in headers.items():
    print('  ' + k + ': ' + v)
print('[目标 URL]', MES_URL)
print('=' * 70)

try:
    resp = requests.post(MES_URL, data=xml_body.encode('utf-8'), headers=headers, timeout=10)
    print('\n[HTTP 状态码]', resp.status_code)
    print('\n[响应 Headers]')
    for k, v in resp.headers.items():
        print('  ' + k + ': ' + v)
    print('\n[响应 Body 完整内容]')
    print(resp.text)
except Exception as e:
    print('\n[异常]', type(e).__name__, str(e))

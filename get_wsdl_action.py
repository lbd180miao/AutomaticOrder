#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
运行在甲方内网服务器上，自动从 WSDL 读取正确的 SOAPAction
运行命令：.venv\Scripts\python.exe get_wsdl_action.py
"""
import urllib.request
import re

WSDL_URL = 'http://10.252.6.51/MESService_LG/BaseService.svc?wsdl'

print('正在获取 WSDL:', WSDL_URL)
try:
    with urllib.request.urlopen(WSDL_URL, timeout=10) as resp:
        content = resp.read().decode('utf-8', errors='replace')
except Exception as e:
    print('获取失败:', e)
    print('请确认在甲方内网服务器上运行此脚本！')
    exit(1)

print('\n======== 完整 WSDL（前3000字符）========')
print(content[:3000])

print('\n======== 所有 soapAction 值 ========')
actions = re.findall(r'soapAction="([^"]*)"', content)
for a in actions:
    print(' ', a)

print('\n======== 所有 operation 名 ========')
ops = re.findall(r'<(?:wsdl:)?operation\s+name="([^"]*)"', content)
for o in ops:
    print(' ', o)

print('\n======== 所有命名空间 ========')
ns_matches = re.findall(r'xmlns(?::\w+)?="([^"]*tempuri[^"]*|[^"]*YFPO[^"]*)"', content)
for n in set(ns_matches):
    print(' ', n)

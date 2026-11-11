"""Exercise both frozen roles over HTTP and a local SOAP fixture, no real hardware/MES."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'delivery/20261111-Dual-Full-v2'
RUN = ROOT / 'build' / ('dual-smoke-' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)
calls = []
fields = ['Code', 'Data', 'ErrMsg', 'FactoryCode', 'Id', 'RT', 'Sender', 'SenderUrl',
          'Status', 'TaskId', 'TelId', 'TimeStamp', 'Timestamp']
elements = ''.join(f'<xsd:element name="{f}" type="xsd:string" minOccurs="0"/>' for f in fields)


class SoapFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_xml(self, body):
        raw = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/xml; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.send_xml(f'''<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="http://tempuri.org/"
 xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" targetNamespace="http://tempuri.org/">
 <types><xsd:schema targetNamespace="http://tempuri.org/" elementFormDefault="qualified">
 <xsd:complexType name="Message"><xsd:sequence>{elements}</xsd:sequence></xsd:complexType>
 <xsd:element name="InvokeMethod"><xsd:complexType><xsd:sequence><xsd:element name="message" type="tns:Message"/></xsd:sequence></xsd:complexType></xsd:element>
 <xsd:element name="InvokeMethodResponse"><xsd:complexType><xsd:sequence><xsd:element name="InvokeMethodResult" type="tns:Message"/></xsd:sequence></xsd:complexType></xsd:element>
 </xsd:schema></types>
 <message name="Request"><part name="parameters" element="tns:InvokeMethod"/></message>
 <message name="Response"><part name="parameters" element="tns:InvokeMethodResponse"/></message>
 <portType name="Service"><operation name="InvokeMethod"><input message="tns:Request"/><output message="tns:Response"/></operation></portType>
 <binding name="Binding" type="tns:Service"><soap:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
 <operation name="InvokeMethod"><soap:operation soapAction="http://tempuri.org/InvokeMethod"/>
 <input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation></binding>
 <service name="MES"><port name="Port" binding="tns:Binding"><soap:address location="http://127.0.0.1:{self.server.server_port}/MES"/></port></service></definitions>''')

    def do_POST(self):
        tree = ET.fromstring(self.rfile.read(int(self.headers['Content-Length'])))
        values = {node.tag.split('}')[-1]: node.text for node in tree.iter()}
        payload = json.loads(values['Data'])
        assert values['Code'] == '20260801', values
        calls.append(payload)
        result = {'Status': True, 'RackCode': payload['RackCode'], 'RackStatus': 1,
                  'IsSealed': False, 'PkgTypeCode': '3LayerRack', 'HUQty': 0,
                  'HUMaxQty': 15, 'Message': 'local SOAP fixture'}
        self.send_xml('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                      '<InvokeMethodResponse xmlns="http://tempuri.org/"><InvokeMethodResult>'
                      '<Data>' + escape(json.dumps(result)) + '</Data><ErrMsg></ErrMsg><Status>200</Status>'
                      '</InvokeMethodResult></InvokeMethodResponse></s:Body></s:Envelope>')


fixture = ThreadingHTTPServer(('127.0.0.1', 0), SoapFixture)
threading.Thread(target=fixture.serve_forever, daemon=True).start()
env = {**os.environ, 'USE_SIMULATED_DEVICES': 'true', 'RVC_CAMERA_AUTO_START': 'false',
       'DM_CAMERA_AUTO_CONNECT': 'false', 'PYTHONPATH': ''}
env.pop('PLC_LISTENER_AUTO_START', None)
env.pop('MES_GATEWAY_ENABLED', None)
sessions = []
processes = []
logs = []
for name in ('AGVControl', 'ExternalControl'):
    data = RUN / name
    data.mkdir()
    for filename in ('db.sqlite3', 'deployment.json', 'agv_gateway.json'):
        shutil.copy2(RELEASE / name / filename, data / filename)
    cfg = json.loads((data / 'agv_gateway.json').read_text())
    cfg['gateway_url'] = 'http://127.0.0.1:18108'
    (data / 'agv_gateway.json').write_text(json.dumps(cfg))
cfg = json.loads((RELEASE / 'ExternalControl/gateway.json').read_text())
cfg.update(port=18108, mes_url=f'http://127.0.0.1:{fixture.server_port}/MES?wsdl')
(RUN / 'ExternalControl/gateway.json').write_text(json.dumps(cfg))


def session():
    s = requests.Session()
    s.trust_env = False
    sessions.append(s)
    return s


http = session()


def launch(name, port):
    log = (RUN / f'{name}-{len(logs)}.log').open('wb')
    logs.append(log)
    process = subprocess.Popen([str(RELEASE / name / f'{name}.exe'), '--data-dir', str(RUN / name),
                                '--port', str(port), '--no-browser'], cwd=RUN, env=env,
                               stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    processes.append(process)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name} exited: {process.returncode}; logs: {RUN}')
        try:
            if http.get(f'http://127.0.0.1:{port}/devices/status/', timeout=2).status_code == 200:
                return process
        except requests.RequestException:
            pass
        time.sleep(.5)
    raise TimeoutError(name)


def submit(mode, rack='SMOKE-RACK-001'):
    page = http.get('http://127.0.0.1:18106/mes/gateway/', timeout=5)
    page.raise_for_status()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
    r = http.post('http://127.0.0.1:18106/mes/gateway/test/', json={'mode': mode, 'rack_code': rack},
                  headers={'X-CSRFToken': token}, timeout=10)
    r.raise_for_status()
    return r.json()


def completed(task_id):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        rows = http.get('http://127.0.0.1:18106/mes/gateway/status/', timeout=5).json()['tasks']
        row = next((r for r in rows if r['id'] == task_id), None)
        if row and row['state'] == 'succeeded':
            return json.loads(row['result'])
        if row and row['state'] in ('failed', 'unknown'):
            raise AssertionError(row)
        time.sleep(.5)
    raise TimeoutError(task_id)


try:
    external = launch('ExternalControl', 18107)
    agv = launch('AGVControl', 18106)
    for port, running in [(18106, True), (18107, False)]:
        status = http.get(f'http://127.0.0.1:{port}/devices/api/plc-status/', timeout=5).json()
        assert status['global_running'] is running, status
        for route in ('/mes/records/', '/devices/plc-config/', '/vision/rack-location/recipes/'):
            r = http.get(f'http://127.0.0.1:{port}{route}', timeout=10)
            assert r.status_code == 200, (route, r.status_code)
    assert http.get('http://127.0.0.1:18108/', timeout=5).status_code == 200
    assert submit('health')['role'] == 'mes_gateway'
    completed(submit('self_test')['id'])
    assert calls == [], 'Self test must not call MES'
    result = completed(submit('rack_query')['id'])
    assert result['pkg_type_code'] == '3LayerRack' and result['hu_max_qty'] == 15, result
    assert len(calls) == 1 and calls[0]['RackCode'] == 'SMOKE-RACK-001', calls
    external.terminate()
    external.wait(timeout=15)
    task_id = submit('rack_query', 'SMOKE-RACK-002')['id']
    time.sleep(3)
    assert len(calls) == 1
    external = launch('ExternalControl', 18107)
    assert completed(task_id)['rack_code'] == 'SMOKE-RACK-002'
    assert len(calls) == 2
    print('PASS: both full EXEs, AGV PLC autostart, external PLC off, HTTP roundtrip, SOAP query result, offline recovery.')
    print('Evidence:', RUN)
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
    for log in logs:
        log.close()
    for s in sessions:
        s.close()
    fixture.shutdown()
    fixture.server_close()

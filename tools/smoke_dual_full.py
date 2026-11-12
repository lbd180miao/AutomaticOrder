"""Exercise both frozen roles over HTTP and a local SOAP fixture, no real hardware/MES."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('release', type=Path, help='Directory containing AGVControl and ExternalControl')
RELEASE = parser.parse_args().release.resolve()
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


def free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for server in sockets:
            server.bind(('127.0.0.1', 0))
        return [server.getsockname()[1] for server in sockets]
    finally:
        for server in sockets:
            server.close()


def saved_defaults(db_path):
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('''
            SELECT foam.id, rack.id
            FROM vision_plcvisiondefaults AS defaults
            JOIN vision_visionrecipe AS foam ON foam.id = defaults.foam_recipe_id
            JOIN vision_racklocationrecipe AS rack ON rack.id = defaults.rack_recipe_id
            WHERE defaults.id = 1 AND foam.is_active AND foam.recipe_type = 'FOAM_2D' AND rack.enabled
        ''').fetchone()
    assert row is not None, f'Missing enabled PLC recipe defaults in {db_path}'
    return {'foam_recipe_id': row[0], 'rack_recipe_id': row[1]}


fixture = ThreadingHTTPServer(('127.0.0.1', 0), SoapFixture)
agv_port, external_port, gateway_port = free_ports(3)
agv_url = f'http://127.0.0.1:{agv_port}'
gateway_url = f'http://127.0.0.1:{gateway_port}'
env = {**os.environ, 'USE_SIMULATED_DEVICES': 'true', 'RVC_CAMERA_AUTO_START': 'false',
       'DM_CAMERA_AUTO_CONNECT': 'false', 'PYTHONPATH': '', 'NO_PROXY': '127.0.0.1,localhost'}
for key in ('PLC_LISTENER_AUTO_START', 'MES_GATEWAY_ENABLED', 'DJANGO_DATABASE_PATH', 'DJANGO_MEDIA_ROOT'):
    env.pop(key, None)
sessions = []
processes = []
logs = []
for name in ('AGVControl', 'ExternalControl'):
    data = RUN / name
    data.mkdir()
    for filename in ('db.sqlite3', 'deployment.json', 'agv_gateway.json'):
        shutil.copy2(RELEASE / name / filename, data / filename)
    cfg = json.loads((data / 'agv_gateway.json').read_text())
    cfg['gateway_url'] = gateway_url
    (data / 'agv_gateway.json').write_text(json.dumps(cfg))
cfg = json.loads((RELEASE / 'ExternalControl/gateway.json').read_text())
cfg.update(port=gateway_port, mes_url=f'http://127.0.0.1:{fixture.server_port}/MES?wsdl')
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
    page = http.get(f'{agv_url}/mes/gateway/', timeout=5)
    page.raise_for_status()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
    r = http.post(f'{agv_url}/mes/gateway/test/', json={'mode': mode, 'rack_code': rack},
                  headers={'X-CSRFToken': token}, timeout=10)
    r.raise_for_status()
    return r.json()


def completed(task_id):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        rows = http.get(f'{agv_url}/mes/gateway/status/', timeout=5).json()['tasks']
        row = next((r for r in rows if r['id'] == task_id), None)
        if row and row['state'] == 'succeeded':
            return json.loads(row['result'])
        if row and row['state'] in ('failed', 'unknown'):
            raise AssertionError(row)
        time.sleep(.5)
    raise TimeoutError(task_id)


def check_role(name, port, listener_on):
    base_url = f'http://127.0.0.1:{port}'
    status = http.get(f'{base_url}/devices/api/plc-status/?view=controls', timeout=5).json()
    assert status['global_running'] is listener_on and status['global_stopping'] is False, status
    for route in ('/mes/records/', '/devices/plc-config/', '/vision/rack-location/recipes/', '/vision/recipes/'):
        r = http.get(f'{base_url}{route}', timeout=10)
        assert r.status_code == 200, (route, r.status_code)
    expected = saved_defaults(RUN / name / 'db.sqlite3')
    locator = http.get(f"{base_url}/vision/rack-locator/?recipe_id={expected['rack_recipe_id']}", timeout=5)
    locator.raise_for_status()
    assert 'page-rack-locator' in locator.text and 'dp-camera-table-scroll' in locator.text
    script = http.get(f'{base_url}/static/vision/js/rack_dual_point.js?v=37', timeout=5)
    script.raise_for_status()
    r = http.get(f'{base_url}/vision/api/recipes/plc-defaults/', timeout=5)
    r.raise_for_status()
    defaults = r.json()
    assert defaults.get('success') is True and all(defaults.get(key) == value for key, value in expected.items()), defaults

    log = RUN / name / 'logs/plc-listener.log'
    if listener_on:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if log.is_file() and 'memory:102' in log.read_text(encoding='utf-8'):
                return expected
            time.sleep(.2)
        raise AssertionError(f'No simulated PLC scan in {log}')
    assert not log.exists(), f'Unexpected external PLC listener log: {log}'
    return expected


threading.Thread(target=fixture.serve_forever, daemon=True).start()
try:
    external = launch('ExternalControl', external_port)
    launch('AGVControl', agv_port)
    agv_defaults = check_role('AGVControl', agv_port, True)
    assert check_role('ExternalControl', external_port, False) == agv_defaults
    assert http.get(f'{gateway_url}/', timeout=5).status_code == 200
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
    launch('ExternalControl', external_port)
    assert completed(task_id)['rack_code'] == 'SMOKE-RACK-002'
    assert len(calls) == 2
    print('PASS: both full EXEs, AGV simulated PLC scan, external PLC off, saved 2D/3D defaults, HTTP/SOAP and offline recovery.')
    print('PLC default recipe IDs:', agv_defaults)
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

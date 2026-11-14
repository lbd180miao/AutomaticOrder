"""Verify packaged device icons through each frozen application's HTTP server."""
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
import requests
from packaging_resources import UI_ICON_NAMES

ROOT = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve()
run = ROOT / 'build' / ('icon-smoke-' + uuid.uuid4().hex[:8])
run.mkdir()

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

report = {}
for role in ('AGVControl', 'ExternalControl'):
    folder = release / role
    data = run / role
    data.mkdir()
    for filename in ('db.sqlite3', 'deployment.json', 'agv_gateway.json'):
        shutil.copy2(folder / filename, data / filename)
    cfg = json.loads((data / 'agv_gateway.json').read_text())
    cfg['gateway_url'] = f'http://127.0.0.1:{port()}'
    (data / 'agv_gateway.json').write_text(json.dumps(cfg))
    if role == 'ExternalControl':
        gateway = json.loads((folder / 'gateway.json').read_text())
        gateway.update(port=port(), mes_url=f'http://127.0.0.1:{port()}/MES')
        (data / 'gateway.json').write_text(json.dumps(gateway))
    with sqlite3.connect(data / 'db.sqlite3') as db:
        db.execute("UPDATE devices_device SET address='127.0.0.1',configuration=? WHERE device_type='PLC'",
                   (json.dumps({'rack':0,'slot':1,'tcp_port':port()}),))
    web_port = port()
    env = dict(os.environ, AUTOMATIC_ORDER_REGISTER_STARTUP='false',
               RVC_CAMERA_AUTO_START='false', DM_CAMERA_AUTO_CONNECT='false',
               USE_SIMULATED_DEVICES='false')
    for key in ('DJANGO_DATABASE_PATH','AUTOMATIC_ORDER_DATA_DIR','DJANGO_MEDIA_ROOT'):
        env.pop(key, None)
    with (data / 'console.log').open('wb') as log, requests.Session() as http:
        http.trust_env = False
        proc = subprocess.Popen([str(folder / f'{role}.exe'), '--data-dir', str(data),
                                 '--port', str(web_port), '--no-browser'], cwd=data, env=env,
                                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            base = f'http://127.0.0.1:{web_port}'
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                assert proc.poll() is None, f'{role} exited; see {data}'
                try:
                    page = http.get(base + '/devices/status/', timeout=2)
                    if page.status_code == 200: break
                except requests.RequestException: pass
                time.sleep(.5)
            else: raise TimeoutError(f'{role}: {data}')
            icons = {}
            for name in UI_ICON_NAMES:
                response = http.get(base + '/static/devices/icons/' + name, timeout=5)
                assert response.status_code == 200, (name,response.status_code)
                assert 'image/svg+xml' in response.headers['Content-Type']
                assert response.content == (ROOT / 'static/devices/icons' / name).read_bytes()
                assert ET.fromstring(response.content).tag.endswith('svg')
                icons[name] = {'status':200, 'bytes':len(response.content)}
            for name in ('server.svg','camera.svg','device-projector.svg'):
                assert '/static/devices/icons/' + name in page.text
            assert 'alarm-chip' not in page.text and 'settings-link' not in page.text
            assert 'id="system-clock"' in page.text
            mes = http.get(base + '/mes/communication/',timeout=10)
            assert mes.status_code == 200 and 'comm-send' in mes.text
            assert 'comm-config-form' in mes.text and 'comm-result-status' in mes.text
            assert 'comm-reply' not in mes.text
            health = http.get(base + '/devices/api/health/', timeout=10).json()
            assert len(health['devices']) == 4 and health['devices'][3]['name'] == '外部电脑'
            configuration = http.get(base + '/mes/communication/config/', timeout=5).json()
            assert configuration['token_configured'] and 'token' not in configuration
            assert http.get(base + '/static/mes/communication.js',timeout=5).status_code == 200
            report[role] = icons
            print(f'PASS {role}: six SVG HTTP responses, three device icons, clock-only header, communication page', flush=True)
        finally:
            proc.terminate()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
(release / 'device-icons-http-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

"""Start frozen roles with isolated data, disabled cameras and loopback-only endpoints."""
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
import requests

ROOT = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve()
scratch = ROOT / 'build' / ('release-pages-' + uuid.uuid4().hex[:8])
scratch.mkdir()


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


report = {}
for role in ('AGVControl', 'ExternalControl'):
    folder = release / role
    data = scratch / role
    data.mkdir()
    for name in ('db.sqlite3', 'deployment.json', 'agv_gateway.json'):
        shutil.copy2(folder / name, data / name)
    cfg = json.loads((data / 'agv_gateway.json').read_text())
    cfg['gateway_url'] = f'http://127.0.0.1:{port()}'
    (data / 'agv_gateway.json').write_text(json.dumps(cfg))
    if role == 'ExternalControl':
        cfg = json.loads((folder / 'gateway.json').read_text())
        cfg.update(port=port(), mes_url='http://127.0.0.1:1/MES')
        (data / 'gateway.json').write_text(json.dumps(cfg))
    db = sqlite3.connect(data / 'db.sqlite3')
    with db:
        db.execute('UPDATE devices_device SET enabled=0, address=?', ('127.0.0.1',))
    db.close()
    env = dict(os.environ, AUTOMATIC_ORDER_REGISTER_STARTUP='false', RVC_CAMERA_AUTO_START='false',
               DM_CAMERA_AUTO_CONNECT='false', FOAM_STREAM_AUTO_START='false', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    for key in ('DJANGO_DATABASE_PATH', 'AUTOMATIC_ORDER_DATA_DIR', 'DJANGO_MEDIA_ROOT'):
        env.pop(key, None)
    web = port()
    with (data / 'console.log').open('wb') as log, requests.Session() as http:
        http.trust_env = False
        proc = subprocess.Popen([str(folder / (role + '.exe')), '--data-dir', str(data), '--port', str(web), '--no-browser'],
                                env=env, cwd=data, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            base = f'http://127.0.0.1:{web}'
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                assert proc.poll() is None, f'{role} exited: {data}'
                try:
                    response = http.get(base + '/devices/status/', timeout=2)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError(f'{role} startup failed: {data}')
            assert 'device-foam-live' in response.text
            live = http.get(base + '/vision/api/foam/stream/live/', timeout=5).json()
            assert live['success'] and not live['running'], live
            assert http.get(base + '/vision/foam-inspector/', timeout=5).status_code == 200
            js = http.get(base + '/static/devices/foam_live_status.js', timeout=5)
            assert js.status_code == 200 and 'processing_error' in js.text
            assert http.get(base + '/devices/status/?section=log', timeout=5).status_code == 200
            report[role] = {'page':200, 'live_api':True, 'camera_disabled':True, 'current_js':True}
            print('PASS frozen pages:', role, flush=True)
        finally:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
(release / 'pages-smoke-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

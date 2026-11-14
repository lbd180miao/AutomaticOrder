"""Verify the deployed EXE starts its PLC listener, using an isolated, unreachable loopback PLC."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import sys
import uuid
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RELEASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'delivery/20261111-PLC-AutoStart/AGVControl'
DATA = ROOT / 'build' / ('plc-autostart-smoke-' + uuid.uuid4().hex[:8])
DATA.mkdir(parents=True, exist_ok=True)
shutil.copy2(RELEASE / 'db.sqlite3', DATA / 'db.sqlite3')
if (RELEASE / 'deployment.json').exists():
    shutil.copy2(RELEASE / 'deployment.json', DATA / 'deployment.json')
if (RELEASE / 'agv_gateway.json').exists():
    cfg = json.loads((RELEASE / 'agv_gateway.json').read_text(encoding='utf-8'))
    cfg['gateway_url'] = 'http://127.0.0.1:1'
    (DATA / 'agv_gateway.json').write_text(json.dumps(cfg), encoding='utf-8')

with sqlite3.connect(DATA / 'db.sqlite3') as db:
    db.execute("UPDATE devices_device SET enabled=0 WHERE device_type!='PLC'")
    db.execute("UPDATE devices_device SET address='127.0.0.1', configuration=? WHERE device_type='PLC'",
               (json.dumps({'rack': 0, 'slot': 1, 'tcp_port': 1}),))

env = dict(os.environ)
env['PLC_LISTENER_AUTO_START'] = 'false'  # Old inherited settings must not disable AGV listening.
env.update(RVC_CAMERA_AUTO_START='false', DM_CAMERA_AUTO_CONNECT='false',
           USE_SIMULATED_DEVICES='false', MES_GATEWAY_ENABLED='false',
           AUTOMATIC_ORDER_REGISTER_STARTUP='false', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with (DATA / 'exe.log').open('wb') as log:
    process = subprocess.Popen([str(RELEASE / 'AGVControl.exe'), '--data-dir', str(DATA),
                                '--port', '18016', '--no-browser'],
                               cwd=DATA, env=env, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'EXE exited: {process.returncode}')
            try:
                with opener.open('http://127.0.0.1:18016/devices/api/plc-status/', timeout=2) as response:
                    status = json.load(response)
                assert status['global_running'] is True, status
                assert status['global_stopping'] is False, status
                assert (DATA / 'logs/plc-listener.log').exists()
                names = {point['name'] for scene in status['scenes']
                         for point in scene['interactions'] if point['direction'] == 'IN'}
                assert names == {'product_barcode', 'rack_barcode', 'rack_barcode_2', 'position_trigger', 'foam_trigger', 'boxing_trigger', 'boxing_trigger_2', 'rack_working', 'rack_working_2'}, names
                with opener.open('http://127.0.0.1:18016/devices/api/plc-logs/', timeout=2) as response:
                    logs = json.load(response)
                assert logs['auto_start'] and logs['running'], logs
                assert logs['debug']['enabled'] is False, logs
                if not logs['inputs'].get('error'):
                    time.sleep(.5)
                    continue
                assert not logs['inputs']['values'], logs
                with opener.open('http://127.0.0.1:18016/devices/status/', timeout=2) as response:
                    page = response.read().decode('utf-8')
                for address in ('DB2.DBB0', 'DB2.DBB24', 'DB2.DBB46', 'DB2.DBX68.3', 'DB2.DBX68.4', 'DB2.DBX68.5', 'DB2.DBX68.6', 'DB2.DBX68.7', 'DB2.DBX69.0'):
                    assert address in page, address
                assert '监听未运行' not in page
                print('PASS: frozen AGV auto-listens despite disabled inherited flag; nine inputs, default debug off, offline PLC handling and UI verified')
                break
            except OSError:
                time.sleep(.5)
        else:
            raise TimeoutError('EXE did not start within 60 seconds')
    finally:
        process.terminate()
        process.wait(timeout=15)

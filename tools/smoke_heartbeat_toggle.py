"""Check a packaged AGV against a local S7 simulator, without opening a page."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from snap7.server import Server
from snap7.type import SrvArea

ROOT = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve()
data = ROOT / 'build' / ('heartbeat-smoke-' + uuid.uuid4().hex[:8])
data.mkdir()
shutil.copy2(release / 'db.sqlite3', data / 'db.sqlite3')
shutil.copy2(release / 'deployment.json', data / 'deployment.json')
cfg = json.loads((release / 'agv_gateway.json').read_text())
cfg['gateway_url'] = 'http://127.0.0.1:1'
(data / 'agv_gateway.json').write_text(json.dumps(cfg))
with sqlite3.connect(data / 'db.sqlite3') as db:
    db.execute("UPDATE devices_device SET enabled=0 WHERE device_type!='PLC'")
    db.execute("UPDATE devices_device SET address='127.0.0.1', configuration=? WHERE device_type='PLC'",
               (json.dumps({'rack': 0, 'slot': 1, 'tcp_port': 18102, 'heartbeat_interval': 10}),))
memory = bytearray(104)
memory[70] = 0xaa
server = Server(log=False)
server.register_area(SrvArea.DB, 2, memory)
server.start(tcp_port=18102)
env = dict(os.environ)
env.update(PLC_LISTENER_AUTO_START='false', RVC_CAMERA_AUTO_START='false',
           DM_CAMERA_AUTO_CONNECT='false', USE_SIMULATED_DEVICES='false',
           MES_GATEWAY_ENABLED='false', AUTOMATIC_ORDER_REGISTER_STARTUP='false',
           OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
process = None
try:
    with (data / 'exe.log').open('wb') as log:
        process = subprocess.Popen([str(release / 'AGVControl.exe'), '--data-dir', str(data),
                                    '--port', '18017', '--no-browser'], cwd=data, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        changes = []
        previous = False
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and len(changes) < 9:
            assert process.poll() is None, f'EXE exited: {process.returncode}; {data}'
            value = bool(memory[70] & 1)
            assert memory[70] & 0xfe == 0xaa, 'Adjacent bits changed'
            if value != previous:
                changes.append((time.monotonic(), value))
                previous = value
            time.sleep(0.01)
        assert len(changes) == 9, (changes, data)
        gaps = [round(b[0] - a[0], 3) for a, b in zip(changes, changes[1:])]
        assert all(0.4 <= gap <= 0.8 for gap in gaps), gaps
        print('PASS: EXE automatically toggles without browser or task; intervals:', gaps)
        print('PASS: legacy 10s setting ignored; adjacent bits preserved')
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
    server.stop()
    server.destroy()

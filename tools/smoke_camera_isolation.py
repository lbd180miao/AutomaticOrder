"""Run a frozen AGV with unreachable hardware, then crash its RVC child.

All database/config mutations are confined to a fresh test data directory.
No real PLC or MES endpoint is contacted.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('release', type=Path)
    args = parser.parse_args()
    release = args.release.resolve()
    data = ROOT / 'build' / ('camera-isolation-' + uuid.uuid4().hex[:8])
    data.mkdir(parents=True)
    for name in ('db.sqlite3', 'deployment.json', 'agv_gateway.json'):
        shutil.copy2(release / name, data / name)
    cfg = json.loads((data / 'agv_gateway.json').read_text())
    cfg['gateway_url'] = f'http://127.0.0.1:{free_port()}'
    (data / 'agv_gateway.json').write_text(json.dumps(cfg))
    with sqlite3.connect(data / 'db.sqlite3') as db:
        db.execute("UPDATE devices_device SET address='127.0.0.1', configuration=? WHERE device_type='PLC'",
                   (json.dumps({'rack': 0, 'slot': 1, 'tcp_port': free_port()}),))
        # Do not replay pending real MES work even against the loopback fixture.
    port, camera_port = free_port(), free_port()
    env = dict(os.environ, RVC_CAMERA_AUTO_START='true', DM_CAMERA_AUTO_CONNECT='false',
               PLC_LISTENER_AUTO_START='true', USE_SIMULATED_DEVICES='false',
               RVC_CAMERA_IP='192.0.2.254', RVC_CAMERA_SN='ISOLATION-TEST-NO-SUCH-CAMERA',
               RVC_CAMERA_SERVICE_PORT=str(camera_port),
               RVC_CAMERA_SERVICE_URL=f'http://127.0.0.1:{camera_port}')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(route):
        with opener.open(f'http://127.0.0.1:{port}{route}', timeout=5) as response:
            assert response.status == 200
            return response.read()

    with (data / 'console.log').open('wb') as output:
        proc = subprocess.Popen([str(release / 'AGVControl.exe'), '--data-dir', str(data),
                                 '--port', str(port), '--no-browser'], env=env, cwd=data,
                                stdout=output, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                assert proc.poll() is None, f'Application exited {proc.returncode}; {data}'
                try:
                    get('/devices/status/')
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise TimeoutError(f'Web startup failed: {data}')
            for route in ('/', '/vision/recipes/', '/devices/api/health/'):
                get(route)
            status = json.loads(get('/devices/api/plc-status/?view=controls'))
            assert status['global_running'] is True, status
            # Duplicate startup must leave diagnostics and not affect the
            # existing service or initiate a second hardware listener.
            if (data / 'logs/server.log').exists():
                duplicate = subprocess.run(
                    [str(release / 'AGVControl.exe'), '--data-dir', str(data), '--no-browser'],
                    env=env, cwd=data, capture_output=True, timeout=25,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                assert duplicate.returncode == 1
                assert (data / 'logs/startup-error.log').exists()
                get('/devices/status/')
            time.sleep(8)
            # The child PID is emitted by the application's own supervisor.
            log_path = data / 'logs/server.log'
            if not log_path.exists():
                log_path = data / 'console.log'
            log = log_path.read_text(encoding='utf-8', errors='replace')
            pids = re.findall(r'PID=(\d+)', log)
            assert pids, f'RVC child did not start: {data}'
            pid = pids[-1]
            result = subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
            assert result.returncode == 0, result.stderr
            for _ in range(16):
                assert proc.poll() is None, f'Web exited after camera crash: {data}'
                get('/devices/status/')
                time.sleep(1)
            log = log_path.read_text(encoding='utf-8', errors='replace')
            assert len(set(re.findall(r'PID=(\d+)', log))) >= 2, 'RVC was not restarted'
            health = json.loads(get('/devices/api/health/'))
            assert not any(d['state'] == 'simulated' for d in health['devices']), health
            print(f'PASS: real mode, absent hardware, camera crash/restart, web available; logs: {data}')
        finally:
            proc.terminate()
            proc.wait(timeout=15)
            # Guardian EOF stops its server; server EOF stops the SDK process.
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    get('/devices/status/')
                except OSError:
                    break
                time.sleep(.5)
            else:
                raise AssertionError('Web process survived launcher termination')


if __name__ == '__main__':
    main()

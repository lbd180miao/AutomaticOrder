"""Verify the deployed EXE starts its PLC listener, using isolated simulated IO."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'delivery/20261111-PLC-AutoStart/AGVControl'
DATA = ROOT / 'build/plc-autostart-smoke'
DATA.mkdir(parents=True, exist_ok=True)
shutil.copy2(RELEASE / 'db.sqlite3', DATA / 'db.sqlite3')
env = dict(os.environ)
env.pop('PLC_LISTENER_AUTO_START', None)
env.update(RVC_CAMERA_AUTO_START='false', DM_CAMERA_AUTO_CONNECT='false',
           USE_SIMULATED_DEVICES='true', MES_GATEWAY_ENABLED='false')
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
                print('PASS: frozen EXE starts PLC listener automatically without environment override')
                break
            except OSError:
                time.sleep(.5)
        else:
            raise TimeoutError('EXE did not start within 60 seconds')
    finally:
        process.terminate()
        process.wait(timeout=15)

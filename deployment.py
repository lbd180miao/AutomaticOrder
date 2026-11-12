"""Per-computer startup role, shared by the complete deployment executable."""
import json
import os
from urllib.parse import urlsplit


def _read_role_config(path):
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(config, dict) or config.get('role') not in ('agv', 'external'):
        raise ValueError('deployment.json role must be agv or external')
    return config


def _configure_external_camera(directory):
    gateway_path = directory / 'gateway.json'
    gateway = json.loads(gateway_path.read_text(encoding='utf-8-sig')) if gateway_path.is_file() else {}
    gateway_port = int(gateway.get('port', 8001))
    camera_port = int(os.environ.get('RVC_CAMERA_SERVICE_PORT', '8002'))
    if camera_port == gateway_port:
        camera_port = 8003 if gateway_port == 8002 else 8002
    os.environ['RVC_CAMERA_SERVICE_PORT'] = str(camera_port)
    if url := os.environ.get('RVC_CAMERA_SERVICE_URL'):
        parsed = urlsplit(url)
        if parsed.hostname in ('127.0.0.1', 'localhost', '::1') and parsed.port == gateway_port:
            del os.environ['RVC_CAMERA_SERVICE_URL']


def configure(directory, *, executable=None):
    path = directory / 'deployment.json'
    expected_role = None
    if executable is not None:
        expected_role = {'agvcontrol': 'agv', 'externalcontrol': 'external'}.get(executable.stem.lower())
        # Keep the role when a renamed distributed EXE is started with
        # --data-dir. A standalone MyApp.exe has no adjacent role file.
        adjacent = executable.parent / path.name
        if expected_role is None and adjacent != path and adjacent.is_file():
            expected_role = _read_role_config(adjacent)['role']
    if not path.is_file():
        if expected_role is not None:
            raise ValueError(f'Missing {path}; the {expected_role} deployment cannot start without its role configuration')
        return {}
    config = _read_role_config(path)
    role = config['role']
    if expected_role is not None and role != expected_role:
        raise ValueError(f'{path} role must be {expected_role} for this executable')
    if not (directory / 'agv_gateway.json').is_file():
        raise ValueError('Missing agv_gateway.json; direct MES fallback is disabled')
    # Both roles use the durable gateway protocol. AGV never falls back to MES.
    os.environ['MES_GATEWAY_ENABLED'] = 'true'
    if role == 'external':
        # This machine still supports manual hardware operations. Inherited
        # settings must not make it compete with the AGV at startup.
        for key in ('PLC_LISTENER_AUTO_START', 'RVC_CAMERA_AUTO_START', 'DM_CAMERA_AUTO_CONNECT'):
            os.environ[key] = 'false'
        _configure_external_camera(directory)
        return config
    for key, value in {
        'PLC_LISTENER_AUTO_START': config.get('plc_auto_start', True),
        'RVC_CAMERA_AUTO_START': config.get('camera_auto_start', True),
        'DM_CAMERA_AUTO_CONNECT': False,
    }.items():
        os.environ.setdefault(key, 'true' if value else 'false')
    return config


def start_gateway(directory):
    import threading
    from waitress import create_server
    from mes_gateway_project.gateway import Gateway
    app = Gateway(directory)
    # Bind synchronously: a port conflict must fail startup visibly.
    server = create_server(app, host='0.0.0.0', port=int(app.config.get('port', 8001)), threads=8)
    threading.Thread(target=app.worker, daemon=True, name='local-mes-worker').start()
    threading.Thread(target=server.run, daemon=True, name='local-mes-http').start()
    return server

"""Per-computer startup role, shared by the complete deployment executable."""
import json
import os


def configure(directory):
    path = directory / 'deployment.json'
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    role = config.get('role')
    if role not in {'agv', 'external'}:
        raise ValueError('deployment.json role must be agv or external')
    # Both roles use the durable gateway protocol. AGV never falls back to MES.
    os.environ['MES_GATEWAY_ENABLED'] = 'true'
    for key, value in {
        'PLC_LISTENER_AUTO_START': config.get('plc_auto_start', role == 'agv'),
        'RVC_CAMERA_AUTO_START': config.get('camera_auto_start', role == 'agv'),
        'DM_CAMERA_AUTO_CONNECT': False,
    }.items():
        os.environ.setdefault(key, 'true' if value else 'false')
    if not (directory / 'agv_gateway.json').is_file():
        raise ValueError('Missing agv_gateway.json; direct MES fallback is disabled')
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

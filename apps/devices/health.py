"""Per-process, single-flight heartbeat snapshots; no production writes."""
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from django.conf import settings
from .models import Device

INTERVAL = 5
STALE_AFTER = 15
_lock = threading.Lock()
_entries = {}


def _isolated(payload):
    command = ([sys.executable, '--hik-capture'] if getattr(sys, 'frozen', False)
               else [sys.executable, '-m', 'apps.devices.adapters.hik_capture_worker'])
    try:
        result = subprocess.run(command + [json.dumps(dict(payload, health_probe=True))],
                                cwd=str(settings.BASE_DIR), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=7,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        raise RuntimeError('心跳检测超时（7 秒）：设备或 SDK 未响应，请检查网络、供电和驱动')
    for line in reversed(result.stdout.splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not data.get('success'):
            raise RuntimeError(data.get('error', '设备检测失败'))
        return data
    raise RuntimeError(f'检测进程异常退出（{result.returncode}）：{result.stderr[-500:]}')


def _probe(spec):
    if spec.get('blocked'):
        return {'state': spec['blocked'], 'detail': spec['reason']}
    if spec['simulated']:
        return {'state': 'simulated', 'detail': '已启用模拟模式，未检测真实硬件'}
    if spec['kind'] == 'rvc':
        from apps.rvc_camera.client import RvcCameraClient
        client = RvcCameraClient(base_url=spec['service_url'], timeout=3)
        try:
            data = client._get('/status', timeout=3)
        finally:
            client._session.close()
        if not data.get('connected'):
            raise RuntimeError('3D 相机服务可访问，但相机未连接。' + (data.get('last_error') or '请检查供电、网络及相机连接配置'))
        return {'state': 'online', 'detail': 'RVC 服务正常，SDK 报告相机已连接'}
    return {'state': 'online', **_isolated(spec)}


def _run(key, spec):
    try:
        result = _probe(spec)
    except Exception as exc:
        result = {'state': 'offline', 'detail': str(exc)}
    now = time.monotonic()
    stamp = datetime.now(timezone.utc).isoformat()
    with _lock:
        entry = _entries[key]
        entry.update(result=result, completed=now, checked_at=stamp, running=False)
        if result['state'] == 'online':
            entry['last_online'] = stamp


def snapshot():
    conf = settings.AUTOMATIC_ORDER
    plc = Device.objects.filter(device_type='PLC').order_by('code').first()
    cfg = (plc.configuration or {}) if plc else {}
    rvc, hik = conf.get('RVC_CAMERA', {}), conf.get('HIK_CAMERA', {})
    specs = [dict(kind='plc', name='PLC', address=plc.address if plc else '',
                  connection={k: cfg.get(k, v) for k, v in [('rack', 0), ('slot', 1), ('tcp_port', 102)]}),
             dict(kind='rvc', name='RVC 3D 相机', address=rvc.get('CAMERA_IP') or rvc.get('CAMERA_SN') or '',
                  service_url=rvc.get('SERVICE_URL') or 'http://127.0.0.1:8001'),
             dict(kind='hik', name='海康 2D 相机', address=hik.get('CAMERA_IP') or '',
                  serial=hik.get('SERIAL_NUMBER') or '', sdk_lib_dir=str(hik.get('SDK_LIB_DIR') or ''))]
    if not plc or not plc.address:
        specs[0].update(blocked='unconfigured', reason='未配置 PLC IP，请在连接与点位配置中设置')
    elif not plc.enabled:
        specs[0].update(blocked='disabled', reason='PLC 已在设备配置中禁用')
    elif (plc.protocol or 'S7').upper() not in ('S7', 'S7COMM'):
        specs[0].update(blocked='unconfigured', reason=f'不支持的 PLC 协议：{plc.protocol}，需要 S7')
    rows = []
    with _lock:
        for spec in specs:
            spec['simulated'] = conf.get('USE_SIMULATED_DEVICES', False)
            key = json.dumps(spec, sort_keys=True)
            entry = _entries.setdefault(key, dict(running=False, completed=0, checked_at=None, last_online=None))
            age = time.monotonic() - entry['completed']
            if not entry['running'] and age >= INTERVAL:
                entry['running'] = True
                threading.Thread(target=_run, args=(key, spec), daemon=True).start()
            result = dict(entry.get('result') or {'state': 'checking', 'detail': '正在进行首次心跳检测…'})
            if entry['completed'] and age > STALE_AFTER:
                result.update(state='unknown', detail='心跳结果已过期，当前状态未知，正在重新检测')
            rows.append(dict(dict(name=spec['name'], kind=spec['kind'], address=spec['address'] or spec.get('serial') or '未配置',
                                  checked_at=entry['checked_at'], last_online=entry['last_online']), **result))
    return {'devices': rows, 'interval': INTERVAL}

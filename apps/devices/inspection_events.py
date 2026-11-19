"""Inspection log snapshots: local audit plus nonblocking remote audit cache."""
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone as utc

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from .models import PLCListenerLog

_lock = threading.Lock()
_remote = []
_refreshing = False
_checked = 0
_remote_error = ''


def _refresh_remote():
    global _remote, _refreshing, _checked, _remote_error
    from apps.mes.communication_views import gateway_call
    try:
        events = gateway_call('/api/communication').get('events', [])
        with _lock:
            _remote = events
            _remote_error = ''
    except Exception as exc:
        with _lock:
            _remote_error = '外部电脑事件同步失败，保留上次日志并自动重试：' + str(exc)
    finally:
        with _lock:
            _checked = time.monotonic()
            _refreshing = False


def remote_events():
    global _refreshing
    with _lock:
        if not _refreshing and time.monotonic() - _checked >= 2:
            _refreshing = True
            threading.Thread(target=_refresh_remote, daemon=True, name='inspection-remote-log').start()
        return list(_remote), _remote_error


EVENT_LABELS = {
    'queued': 'AGV 已将请求落库，开始向外部电脑发送',
    'request_received': '外部电脑收到 AGV 请求及料框码，按配置准备查询 MES 或等待人工处理',
    'mes_request': '因收到业务请求，外部电脑开始访问 MES',
    'mes_response': '外部电脑收到 MES 返回信息',
    'http_return': '因请求状态已更新，外部电脑向 AGV 返回状态和结果',
    'gateway_response': 'AGV 收到外部电脑返回的状态和结果',
    'transport_error': '因双机通信失败，请求保留并等待重试',
}


def communication_entries(events):
    entries = []
    for event in events:
        try:
            data = event.get('data') or {}
            if isinstance(data, str):
                data = json.loads(data)
            timestamp = datetime.fromtimestamp(float(event['created']), utc.utc)
            message = (EVENT_LABELS.get(event['kind'], event['kind']) +
                       ' · 请求 ' + str(event.get('task_id', '')) + ' · ' +
                       json.dumps(data, ensure_ascii=False, default=str))
            level = 'ERROR' if event['kind'] == 'transport_error' or data.get('state') in ('failed', 'unknown') else 'INFO'
            entries.append((timestamp, level, event.get('direction', '双机通信'), message))
        except (ValueError, TypeError, KeyError):
            logging.getLogger(__name__).warning('跳过格式无效的通信事件')
    return entries


def log_response(request):
    entries = []
    from apps.vision.foam_ng_log import recent
    try:
        for created, raw in recent():
            result = json.loads(raw)
            sides = ', '.join(name for name, value in result.get('sides', {}).items() if value.get('state') == 'FALLEN')
            entries.append((datetime.fromisoformat(created), 'ERROR', '2D 泡棉检测',
                            f'NG 倒伏 · 帧 {result.get("frame_id")} · {sides}'))
    except (sqlite3.Error, ValueError):
        logging.getLogger(__name__).exception('读取泡棉 NG 日志失败')
    names = {'2d': '2D 泡棉检测', '3d': '3D 料框定位', 'rack': 'AGV 料框码',
             'mes': 'MES 通信', 'connection': '设备连接'}
    for row in PLCListenerLog.objects.order_by('-created_at', '-pk')[:300]:
        level = 'ERROR' if '[报警]' in row.message or '断线' in row.message else 'INFO'
        entries.append((row.created_at, level, names.get(row.category, row.category), row.message))
    events, warning = remote_events()
    # The AGV outbox and the external gateway each retain their own event times.
    # Read only: displaying the page never submits a MES request.
    for filename in ('mes_outbox.sqlite3', 'gateway.sqlite3'):
        path = settings.DATA_DIR / filename
        if not path.is_file():
            continue
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.1)) as db:
                db.row_factory = sqlite3.Row
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='communication_events'").fetchone():
                    events.extend(dict(row) for row in db.execute(
                        'SELECT task_id,direction,kind,data,created FROM communication_events ORDER BY id DESC LIMIT 300'))
        except sqlite3.Error:
            warning = '本机通信日志暂时忙，下一次刷新自动重试。' + warning
    entries.extend(communication_entries(events))
    today = timezone.localdate()
    entries = list(dict.fromkeys(entry for entry in entries if timezone.localdate(entry[0]) == today))
    response = render(request, 'devices/inspection_live_log.html', {
        'entries': sorted(entries, key=lambda entry: entry[0], reverse=True)[:300],
        'log_warning': warning,
    })
    response['Cache-Control'] = 'no-store'
    return response
